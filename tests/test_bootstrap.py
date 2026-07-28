from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import practical_game_studio.bootstrap as bootstrap_module
from practical_game_studio.bootstrap import (
    BootstrapConcurrentModificationError,
    BootstrapConflictError,
    BootstrapError,
    BootstrapRequest,
    BootstrapService,
)
from practical_game_studio.criteria import CriterionCreateRequest, CriterionService
from practical_game_studio.initialization import detect_engine
from practical_game_studio.issues import IssueCreateRequest, IssueService
from practical_game_studio.scaffold import load_scaffold_files
from practical_game_studio.state import StateRepository, find_project_root
from practical_game_studio.validation import validate_project

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def _service(root: Path) -> BootstrapService:
    return BootstrapService(root, clock=lambda: NOW)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _managed_bytes(root: Path) -> dict[str, bytes]:
    resources = load_scaffold_files()
    return {
        relative: (root / relative).read_bytes()
        for relative in resources
        if (root / relative).is_file()
    }


def test_packaged_scaffold_contains_only_lightweight_project_files() -> None:
    files = load_scaffold_files()

    assert "AGENTS.md" in files
    assert ".studio/framework.json" in files
    assert ".studio/state/project.json" in files
    assert ".studio/reports/current-state.md" in files
    assert all(
        not path.startswith(("src/", "tests/", "docs/", ".github/", ".git/"))
        for path in files
    )
    assert "pyproject.toml" not in files
    assert list(files) == sorted(files)
    assert all(content.endswith(b"\n") for content in files.values())


def test_bootstrap_empty_directory_without_identity(tmp_path: Path) -> None:
    result = _service(tmp_path).bootstrap(BootstrapRequest())

    assert result.success
    assert result.operation == "project.bootstrap"
    assert result.details["initialized"] is False
    assert result.details["created_count"] == len(load_scaffold_files())
    assert (
        result.details["recommended_next_command"]
        == 'studio init --name "Project Name"'
    )
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "tests").exists()
    assert not (tmp_path / "pyproject.toml").exists()
    assert validate_project(tmp_path).ok
    manifest = json.loads(
        (tmp_path / ".studio" / "framework.json").read_text(encoding="utf-8")
    )
    assert manifest["bootstrapped_at"] == "2026-07-28T00:00:00Z"


def test_bootstrap_with_identity_is_one_validated_result(tmp_path: Path) -> None:
    result = _service(tmp_path).bootstrap(
        BootstrapRequest(
            name="Midnight Carrier",
            engine="unity",
            platform="Windows",
            review_mode="strict",
        )
    )
    project = StateRepository(tmp_path).load_project()

    assert result.details["initialized"] is True
    assert result.details["recommended_next_command"] == "studio status"
    assert project["project_name"] == "Midnight Carrier"
    assert project["engine"] == "Unity"
    assert project["platform"] == "Windows"
    assert project["review_mode"] == "strict"
    assert result.report_summary == {"rendered": 5, "validated": 5}
    assert validate_project(tmp_path).ok


def test_force_on_new_project_does_not_require_destructive_acknowledgement(
    tmp_path: Path,
) -> None:
    result = _service(tmp_path).bootstrap(
        BootstrapRequest(name="New Forced Game", force=True)
    )

    assert result.details["initialized"] is True
    assert StateRepository(tmp_path).load_project()["project_name"] == "New Forced Game"


def test_packaged_resource_failure_is_structured_and_writes_nothing(
    tmp_path: Path,
) -> None:
    def fail() -> dict[str, bytes]:
        raise RuntimeError("injected missing package data")

    with pytest.raises(BootstrapError) as exc_info:
        BootstrapService(tmp_path, scaffold_loader=fail).bootstrap(BootstrapRequest())

    assert exc_info.value.stage == "resource"
    assert "injected missing package data" in exc_info.value.message
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("engine", "setup", "expected_files"),
    [
        (
            "Unity",
            lambda root: [
                (root / directory).mkdir()
                for directory in ("Assets", "Packages", "ProjectSettings")
            ],
            ("Assets", "Packages", "ProjectSettings"),
        ),
        (
            "Godot",
            lambda root: [
                (root / "project.godot").write_text(
                    '[application]\nconfig/name="Fixture"\n', encoding="utf-8"
                ),
                (root / "scenes").mkdir(),
                (root / "scripts").mkdir(),
            ],
            ("project.godot", "scenes", "scripts"),
        ),
        (
            "Unreal",
            lambda root: [
                (root / "Game.uproject").write_text("{}\n", encoding="utf-8"),
                (root / "Content").mkdir(),
                (root / "Source").mkdir(),
            ],
            ("Game.uproject", "Content", "Source"),
        ),
    ],
)
def test_bootstrap_existing_engine_project_preserves_files_and_detects_engine(
    tmp_path: Path,
    engine: str,
    setup: object,
    expected_files: tuple[str, ...],
) -> None:
    setup(tmp_path)
    before = _tree_bytes(tmp_path)

    _service(tmp_path).bootstrap(BootstrapRequest(name=f"{engine} Game"))

    for relative, content in before.items():
        assert (tmp_path / relative).read_bytes() == content
    assert all((tmp_path / relative).exists() for relative in expected_files)
    assert detect_engine(tmp_path).engine == engine
    assert StateRepository(tmp_path).load_project()["engine"] == engine
    assert not (tmp_path / "pyproject.toml").exists()
    assert validate_project(tmp_path).ok


def test_second_bootstrap_is_byte_identical_noop(tmp_path: Path) -> None:
    _service(tmp_path).bootstrap(BootstrapRequest(name="Stable Game"))
    before = _managed_bytes(tmp_path)

    result = _service(tmp_path).bootstrap(BootstrapRequest())

    assert result.changed_files == ()
    assert result.details["created_count"] == 0
    assert result.details["updated_count"] == 0
    assert _managed_bytes(tmp_path) == before


@pytest.mark.parametrize("relative", ["AGENTS.md", ".studio/config.json"])
def test_conflicting_managed_file_fails_before_writing(
    tmp_path: Path, relative: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("project-owned conflict\n", encoding="utf-8")
    before = _tree_bytes(tmp_path)

    with pytest.raises(BootstrapConflictError) as exc_info:
        _service(tmp_path).bootstrap(BootstrapRequest())

    assert exc_info.value.conflicts == (relative,)
    assert _tree_bytes(tmp_path) == before


def test_force_requires_acknowledgement_and_preserves_state(tmp_path: Path) -> None:
    _service(tmp_path).bootstrap(BootstrapRequest(name="Protected State"))
    IssueService(tmp_path, clock=lambda: NOW).create_issue(
        IssueCreateRequest(
            "Preserved issue",
            "major",
            description="Project-specific state must survive scaffold refresh.",
        )
    )
    agents = tmp_path / "AGENTS.md"
    agents.write_text("outdated managed instructions\n", encoding="utf-8")
    protected_before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for directory in ("state", "reports")
        for path in (tmp_path / ".studio" / directory).glob("*")
        if path.is_file()
    }

    with pytest.raises(BootstrapError, match="--force --yes"):
        _service(tmp_path).bootstrap(BootstrapRequest(force=True))

    result = _service(tmp_path).bootstrap(
        BootstrapRequest(force=True, acknowledged=True)
    )

    assert result.details["updated_count"] == 1
    assert agents.read_bytes() == load_scaffold_files()["AGENTS.md"]
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for directory in ("state", "reports")
        for path in (tmp_path / ".studio" / directory).glob("*")
        if path.is_file()
    } == protected_before


def test_missing_managed_file_is_recreated(tmp_path: Path) -> None:
    _service(tmp_path).bootstrap(BootstrapRequest())
    missing = tmp_path / ".studio" / "roles" / "developer.md"
    missing.unlink()

    result = _service(tmp_path).bootstrap(BootstrapRequest())

    assert ".studio/roles/developer.md" in result.changed_files
    assert missing.read_bytes() == load_scaffold_files()[".studio/roles/developer.md"]


def test_dry_run_with_identity_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Existing game\n", encoding="utf-8")
    before = _tree_bytes(tmp_path)

    result = _service(tmp_path).bootstrap(
        BootstrapRequest(name="Preview", engine="Godot", dry_run=True)
    )

    assert result.dry_run
    assert result.details["initialized"] is True
    assert _tree_bytes(tmp_path) == before


def test_unrelated_files_and_git_metadata_are_preserved(tmp_path: Path) -> None:
    unrelated = {
        "README.md": b"Game readme\n",
        ".gitignore": b"Library/\n",
        ".git/config": b"[core]\n",
        ".github/workflows/game.yml": b"name: Game\n",
        "Assets/player.bin": b"\x00\x01\x02",
    }
    for relative, content in unrelated.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    _service(tmp_path).bootstrap(BootstrapRequest())

    for relative, content in unrelated.items():
        assert (tmp_path / relative).read_bytes() == content


def test_replace_failure_rolls_back_and_cleans_temporaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "keep.txt"
    marker.write_bytes(b"keep\n")
    real_replace = bootstrap_module._replace_file
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected bootstrap replace failure")
        real_replace(source, target)

    monkeypatch.setattr(bootstrap_module, "_replace_file", fail_second)

    with pytest.raises(BootstrapError, match="newly created files were removed"):
        _service(tmp_path).bootstrap(BootstrapRequest())

    assert _tree_bytes(tmp_path) == {"keep.txt": b"keep\n"}
    assert not list(tmp_path.rglob("*.pgs-bootstrap-*.tmp"))
    assert not list(tmp_path.parent.glob(f".{tmp_path.name}.pgs-bootstrap-*"))


def test_staged_validation_failure_writes_nothing(tmp_path: Path) -> None:
    files = load_scaffold_files()
    project = json.loads(files[".studio/state/project.json"].decode("utf-8"))
    project["review_mode"] = "invalid"
    files[".studio/state/project.json"] = (
        json.dumps(project, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    service = BootstrapService(
        tmp_path,
        clock=lambda: NOW,
        scaffold_loader=lambda: files,
    )

    with pytest.raises(BootstrapError, match="staged scaffold is invalid"):
        service.bootstrap(BootstrapRequest())

    assert not any(tmp_path.iterdir())
    assert not list(tmp_path.parent.glob(f".{tmp_path.name}.pgs-bootstrap-*"))


def test_forced_replacement_failure_restores_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _service(tmp_path).bootstrap(BootstrapRequest(name="Rollback"))
    agents = tmp_path / "AGENTS.md"
    config = tmp_path / ".studio" / "config.json"
    agents.write_text("old agents\n", encoding="utf-8")
    config.write_text('{"old": true}\n', encoding="utf-8")
    before = _tree_bytes(tmp_path)
    real_replace = bootstrap_module._replace_file
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected forced refresh failure")
        real_replace(source, target)

    monkeypatch.setattr(bootstrap_module, "_replace_file", fail_second)

    with pytest.raises(BootstrapError):
        _service(tmp_path).bootstrap(BootstrapRequest(force=True, acknowledged=True))

    assert _tree_bytes(tmp_path) == before


def test_concurrent_target_change_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    original = service._build_staged_tree

    def change_after_plan(
        stage: Path, proposed: dict[str, bytes], plan: object
    ) -> None:
        original(stage, proposed, plan)
        (tmp_path / "AGENTS.md").write_text("external change\n", encoding="utf-8")

    monkeypatch.setattr(service, "_build_staged_tree", change_after_plan)

    with pytest.raises(BootstrapConcurrentModificationError):
        service.bootstrap(BootstrapRequest())

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "external change\n"
    assert not (tmp_path / ".studio").exists()


def test_bootstrapped_root_discovery_without_pyproject(tmp_path: Path) -> None:
    _service(tmp_path).bootstrap(BootstrapRequest())
    nested = tmp_path / "game" / "scripts"
    nested.mkdir(parents=True)

    assert find_project_root(start=nested) == tmp_path.resolve()
    assert find_project_root(explicit=tmp_path) == tmp_path.resolve()


def test_random_studio_directory_without_valid_markers_is_rejected(
    tmp_path: Path,
) -> None:
    (tmp_path / ".studio" / "state").mkdir(parents=True)
    (tmp_path / ".studio" / "config.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="studio bootstrap"):
        find_project_root(explicit=tmp_path)


def test_multiple_projects_keep_identity_issues_criteria_and_reports_isolated(
    tmp_path: Path,
) -> None:
    game_a = tmp_path / "GameA"
    game_b = tmp_path / "GameB"
    game_a.mkdir()
    game_b.mkdir()
    _service(game_a).bootstrap(BootstrapRequest(name="Game A"))
    _service(game_b).bootstrap(BootstrapRequest(name="Game B"))

    issue_a = IssueService(game_a, clock=lambda: NOW).create_issue(
        IssueCreateRequest("A-only issue", "major", description="Only in Game A.")
    )
    issue_b = IssueService(game_b, clock=lambda: NOW).create_issue(
        IssueCreateRequest("B-only issue", "minor", description="Only in Game B.")
    )
    criterion_a = CriterionService(game_a, clock=lambda: NOW).create_criterion(
        CriterionCreateRequest(
            description="A-only criterion",
            required=False,
            completion_condition="Review A.",
            verification_policy="document-review",
        )
    )
    criterion_b = CriterionService(game_b, clock=lambda: NOW).create_criterion(
        CriterionCreateRequest(
            description="B-only criterion",
            required=False,
            completion_condition="Review B.",
            verification_policy="document-review",
        )
    )

    assert issue_a.details["issue"]["id"] == "ISS-0001"
    assert issue_b.details["issue"]["id"] == "ISS-0001"
    assert criterion_a.details["criterion"]["id"] == "MC-002"
    assert criterion_b.details["criterion"]["id"] == "MC-002"
    assert StateRepository(game_a).load_project()["project_name"] == "Game A"
    assert StateRepository(game_b).load_project()["project_name"] == "Game B"
    assert StateRepository(game_a).load_issues()["issues"][0]["title"] == "A-only issue"
    assert StateRepository(game_b).load_issues()["issues"][0]["title"] == "B-only issue"
    report_a = (game_a / ".studio/reports/current-state.md").read_text(encoding="utf-8")
    report_b = (game_b / ".studio/reports/current-state.md").read_text(encoding="utf-8")
    assert "Game A" in report_a and "Game B" not in report_a
    assert "Game B" in report_b and "Game A" not in report_b
