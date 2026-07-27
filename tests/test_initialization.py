from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio.initialization import (
    InitializationError,
    InitRequest,
    detect_engine,
    initialize_project,
)
from practical_game_studio.state import StateRepository
from tests.conftest import managed_bytes


def test_initialize_valid_placeholder_state(framework_repo: Path) -> None:
    result = initialize_project(framework_repo, InitRequest(name="Midnight Carrier"))
    project = StateRepository(framework_repo).load_project()
    raw_project = (framework_repo / ".studio" / "state" / "project.json").read_text(
        encoding="utf-8"
    )

    assert result.success
    assert project["project_name"] == "Midnight Carrier"
    assert project["current_phase"] == "intake"
    assert project["current_milestone"] == "Clarify the game idea"
    assert project["current_build_status"] == "not-built"
    assert project["recommended_next_playbook"] == "/start"
    assert ".studio/state/project.json" in result.changed_files
    assert raw_project.endswith("\n")
    assert list(json.loads(raw_project)) == sorted(project)


def test_initialize_with_explicit_fields(framework_repo: Path) -> None:
    initialize_project(
        framework_repo,
        InitRequest(
            name="Midnight Carrier",
            engine="unity",
            engine_version="6.1",
            platform="Windows",
            genre="Horror",
            review_mode="strict",
        ),
    )
    project = StateRepository(framework_repo).load_project()

    assert project["engine"] == "Unity"
    assert project["engine_version"] == "6.1"
    assert project["platform"] == "Windows"
    assert project["genre"] == "Horror"
    assert project["review_mode"] == "strict"


def test_default_review_mode_is_guided(framework_repo: Path) -> None:
    path = framework_repo / ".studio" / "state" / "project.json"
    project = json.loads(path.read_text(encoding="utf-8"))
    project["review_mode"] = "strict"
    path.write_text(json.dumps(project), encoding="utf-8")

    initialize_project(framework_repo, InitRequest(name="Default Review"))

    assert StateRepository(framework_repo).load_project()["review_mode"] == "guided"


@pytest.mark.parametrize(
    ("engine", "create_indicators"),
    [
        (
            "Unity",
            lambda root: [
                (root / name).mkdir() for name in ("Assets", "ProjectSettings")
            ],
        ),
        (
            "Godot",
            lambda root: (root / "project.godot").write_text("", encoding="utf-8"),
        ),
        (
            "Unreal",
            lambda root: (root / "Carrier.uproject").write_text("{}", encoding="utf-8"),
        ),
    ],
)
def test_detect_common_engine_projects(
    framework_repo: Path, engine: str, create_indicators: object
) -> None:
    create_indicators(framework_repo)

    detection = detect_engine(framework_repo)
    initialize_project(framework_repo, InitRequest(name=f"{engine} Game"))
    project = StateRepository(framework_repo).load_project()

    assert detection.engine == engine
    assert project["engine"] == engine
    assert project["current_build_status"] == "unknown"


def test_ambiguous_engine_detection_warns(framework_repo: Path) -> None:
    (framework_repo / "Assets").mkdir()
    (framework_repo / "ProjectSettings").mkdir()
    (framework_repo / "project.godot").write_text("", encoding="utf-8")

    result = initialize_project(framework_repo, InitRequest(name="Ambiguous Game"))
    project = StateRepository(framework_repo).load_project()

    assert project["engine"] is None
    assert any("Multiple engine indicators" in warning for warning in result.warnings)


def test_already_initialized_is_noop_and_preserves_state(framework_repo: Path) -> None:
    initialize_project(framework_repo, InitRequest(name="Original"))
    before = managed_bytes(framework_repo)

    result = initialize_project(framework_repo, InitRequest(name="Ignored"))

    assert result.success
    assert result.changed_files == ()
    assert result.details["already_initialized"] is True
    assert managed_bytes(framework_repo) == before


def test_force_changes_only_explicit_fields(framework_repo: Path) -> None:
    initialize_project(
        framework_repo,
        InitRequest(
            name="Original",
            engine="Godot",
            platform="Windows",
            genre="Horror",
        ),
    )
    before_other_state = {
        name: path.read_bytes()
        for name in ("issues", "decisions", "critical-path", "evidence", "milestone")
        if (path := framework_repo / ".studio" / "state" / f"{name}.json").exists()
    }

    result = initialize_project(
        framework_repo,
        InitRequest(
            platform="Linux",
            force=True,
            acknowledged=True,
        ),
    )
    project = StateRepository(framework_repo).load_project()

    assert set(result.changed_fields) == {"platform"}
    assert project["project_name"] == "Original"
    assert project["engine"] == "Godot"
    assert project["genre"] == "Horror"
    assert project["platform"] == "Linux"
    for name, content in before_other_state.items():
        assert (
            framework_repo / ".studio" / "state" / f"{name}.json"
        ).read_bytes() == content


def test_missing_name_is_actionable(framework_repo: Path) -> None:
    with pytest.raises(InitializationError, match="--name"):
        initialize_project(framework_repo, InitRequest())


def test_force_requires_acknowledgement(framework_repo: Path) -> None:
    initialize_project(framework_repo, InitRequest(name="Original"))

    with pytest.raises(InitializationError, match="--yes"):
        initialize_project(
            framework_repo,
            InitRequest(platform="Linux", force=True),
        )


def test_identical_forced_update_is_deterministic_noop(framework_repo: Path) -> None:
    initialize_project(
        framework_repo,
        InitRequest(name="Stable", engine="Godot", platform="Windows"),
    )
    before = managed_bytes(framework_repo)

    result = initialize_project(
        framework_repo,
        InitRequest(
            name="Stable",
            engine="Godot",
            platform="Windows",
            force=True,
            acknowledged=True,
        ),
    )

    assert result.changed_files == ()
    assert managed_bytes(framework_repo) == before


def test_dry_run_validates_and_writes_nothing(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)

    result = initialize_project(
        framework_repo,
        InitRequest(name="Preview", engine="Unity", dry_run=True),
    )

    assert result.success
    assert result.dry_run
    assert result.validation_summary["errors"] == 0
    assert result.changed_fields["project_name"]["new"] == "Preview"
    assert ".studio/state/project.json" in result.changed_files
    assert managed_bytes(framework_repo) == before
