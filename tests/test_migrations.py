"""Behaviour of the scaffold migration chain and `studio upgrade`.

The point of a migration system is that a project written for an older scaffold
survives the upgrade with its own data intact. These tests build a project at
scaffold 1.0, run the real chain, and check both halves of that promise: the
shape changes, and nothing the project recorded is lost.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.migrations import (
    Migration,
    MigrationError,
    apply_migration,
    engine,
    get_current_version,
    get_target_version,
    known_versions,
    list_available_migrations,
    migration_001,
    migration_002,
    plan_migration,
    resolve_migration_chain,
)
from practical_game_studio.scaffold import FRAMEWORK_MANIFEST_PATH
from practical_game_studio.state import STATE_FILES, StateRepository
from practical_game_studio.transaction import deterministic_json
from practical_game_studio.validation import validate_project

#: The pre-migration shape of the two fields Sprint 1 changed.
LEGACY_PROJECT_FIELDS = {
    "schema_version": "1.0",
    "recommended_next_playbook": "/start",
}


def _bootstrap(root: Path, **identity: str) -> None:
    BootstrapService(root).bootstrap(BootstrapRequest(**identity))


#: State documents that did not exist at scaffold 1.0. Migration 003 creates
#: them, so the fixture must delete them to reproduce a genuinely older project.
DOCUMENTS_ADDED_AFTER_10 = ("runs", "artifacts", "work")


def _downgrade_to_scaffold_10(root: Path) -> None:
    """Rewrite a freshly bootstrapped project back into its scaffold-1.0 shape.

    Building the old project by hand would drift from what 1.0 actually shipped.
    Reversing the registered migrations is the definition of that shape, so the
    fixture stays correct as long as the migrations are.
    """

    state_dir = root / ".studio" / "state"
    for name in DOCUMENTS_ADDED_AFTER_10:
        (state_dir / STATE_FILES[name]).unlink(missing_ok=True)

    for name, filename in STATE_FILES.items():
        path = state_dir / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if name == "project":
            document.pop("current_milestone_id", None)
            document["recommended_next_playbook"] = "/" + document.pop(
                "recommended_next_workflow"
            )
            document["schema_version"] = "1.0"
        elif name == "milestone":
            document.pop("milestones", None)
            document.pop("milestone_id", None)
            document.pop("next_milestone_id", None)
            for criterion in document["criteria_results"]:
                criterion.pop("milestone_id", None)
            document["schema_version"] = "3.1"
        elif name == "critical_path":
            document.pop("current_milestone_id", None)
            document["schema_version"] = "3.0"
        elif name == "evidence":
            for record in document["evidence"]:
                record.pop("related_runs", None)
                record.pop("related_artifacts", None)
            document["schema_version"] = "2.0"
        else:
            continue
        path.write_bytes(deterministic_json(document))

    manifest_path = root / FRAMEWORK_MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scaffold_version"] = "1.0"
    manifest_path.write_bytes(deterministic_json(manifest))


@pytest.fixture
def legacy_project(tmp_path: Path) -> Path:
    """A bootstrapped project rolled back to scaffold 1.0."""

    _bootstrap(tmp_path, name="Legacy Game", engine="Godot")
    _downgrade_to_scaffold_10(tmp_path)
    return tmp_path


def _project(root: Path) -> dict:
    return StateRepository(root).load_project()


def test_registered_chain_is_contiguous_and_ordered() -> None:
    migrations = list_available_migrations()

    assert [step.id for step in migrations] == ["001", "002", "003", "004", "005"]
    assert known_versions() == ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5")
    assert migrations[-1].to_version == get_target_version()


def test_resolve_returns_only_the_steps_between_two_versions() -> None:
    assert [step.id for step in resolve_migration_chain("1.0", "1.5")] == [
        "001",
        "002",
        "003",
        "004",
        "005",
    ]
    assert [step.id for step in resolve_migration_chain("1.1", "1.2")] == ["002"]
    assert resolve_migration_chain("1.5", "1.5") == ()


def test_unknown_and_newer_versions_are_refused_rather_than_guessed() -> None:
    with pytest.raises(MigrationError, match="unknown scaffold version"):
        resolve_migration_chain("0.9", "1.5")
    with pytest.raises(MigrationError, match="newer than the installed package"):
        resolve_migration_chain("1.5", "1.1")


def test_plan_reports_every_reviewable_fact(legacy_project: Path) -> None:
    plan = plan_migration(legacy_project)

    assert plan.source_version == "1.0"
    assert plan.target_version == "1.5"
    assert not plan.up_to_date
    assert [step.id for step in plan.migrations] == ["001", "002", "003", "004", "005"]
    assert ".studio/state/project.json" in plan.affected_files
    assert ".studio/schemas/milestone.schema.json" in plan.affected_files
    assert plan.destructive_changes == ()
    assert plan.manual_actions
    assert len(plan.compatibility_impact) == 5


def test_dry_run_validates_without_writing_anything(legacy_project: Path) -> None:
    before = {
        path: path.read_bytes() for path in legacy_project.rglob("*") if path.is_file()
    }

    result = apply_migration(legacy_project, dry_run=True)

    assert result.success
    assert result.dry_run
    assert result.changed_files
    after = {
        path: path.read_bytes() for path in legacy_project.rglob("*") if path.is_file()
    }
    assert after == before


def test_apply_upgrades_state_and_scaffold_together(legacy_project: Path) -> None:
    assert get_current_version(legacy_project) == "1.0"

    result = apply_migration(legacy_project)

    assert result.success
    assert get_current_version(legacy_project) == "1.5"
    project = _project(legacy_project)
    assert project["recommended_next_workflow"] == "start"
    assert "recommended_next_playbook" not in project
    assert project["schema_version"] == "1.2"
    assert validate_project(legacy_project).ok


def test_apply_preserves_project_identity_and_history(legacy_project: Path) -> None:
    before = _project(legacy_project)

    apply_migration(legacy_project)

    after = _project(legacy_project)
    for field in ("project_name", "engine", "current_phase", "current_milestone"):
        assert after[field] == before[field], field


def test_milestone_ids_are_registered_and_referenced(legacy_project: Path) -> None:
    apply_migration(legacy_project)

    milestone = StateRepository(legacy_project).load_milestone()
    registry = {record["id"]: record for record in milestone["milestones"]}

    assert milestone["milestone_id"] in registry
    assert registry[milestone["milestone_id"]]["title"] == milestone["milestone"]
    assert registry[milestone["milestone_id"]]["status"] == "current"
    for criterion in milestone["criteria_results"]:
        assert registry[criterion["milestone_id"]]["title"] == criterion["milestone"]


def test_migration_is_idempotent_once_applied(legacy_project: Path) -> None:
    apply_migration(legacy_project)
    snapshot = {
        path: path.read_bytes() for path in legacy_project.rglob("*") if path.is_file()
    }

    second = apply_migration(legacy_project)

    assert second.success
    assert second.changed_files == ()
    assert {
        path: path.read_bytes() for path in legacy_project.rglob("*") if path.is_file()
    } == snapshot


def test_id_assignment_does_not_depend_on_iteration_order() -> None:
    """The same project must produce the same ids on every machine."""

    state = {
        "project": {"current_milestone": "Beta"},
        "critical_path": {"current_milestone": "Beta"},
        "milestone": {
            "milestone": "Beta",
            "next_milestone": "Gamma",
            "criteria_results": [
                {
                    "milestone": "Zeta",
                    "milestone_history": [],
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "milestone": "Alpha",
                    "milestone_history": [],
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
        },
    }

    ids = migration_002.assign_milestone_ids(state)

    assert ids["Beta"] == "MS-0001"
    assert ids["Gamma"] == "MS-0002"
    assert ids["Alpha"] == "MS-0003"
    assert ids["Zeta"] == "MS-0004"


def test_workflow_id_extraction_accepts_every_spelling() -> None:
    for value in ("start", "/start", "GS:start", "  GS:start  "):
        assert migration_001._workflow_id(value) == "start"


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _chain_producing(migrate: object) -> object:
    """Build a one-step chain so a test can control what the upgrade produces."""

    step = Migration(
        id="test",
        from_version="1.0",
        to_version="1.5",
        summary="test-only migration",
        migrate=migrate,
    )
    return lambda current, target: (step,)


def test_a_migration_that_would_produce_invalid_state_writes_nothing(
    legacy_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation happens before the first byte is written, not after."""

    before = _snapshot(legacy_project)
    real_chain = resolve_migration_chain("1.0", get_target_version())

    def drop_required_field(state: dict) -> dict:
        # Run the real chain first so the failure under test is the schema
        # violation, not the unrelated "a document is missing" guard.
        broken = copy.deepcopy(engine._apply_chain(state, real_chain))
        broken["project"].pop("current_phase")
        return broken

    monkeypatch.setattr(
        engine, "resolve_migration_chain", _chain_producing(drop_required_field)
    )
    with pytest.raises(MigrationError, match="does not satisfy the upgraded schemas"):
        apply_migration(legacy_project)

    assert _snapshot(legacy_project) == before


def test_a_failure_after_managed_files_are_written_is_rolled_back(
    legacy_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refreshed schemas must not survive a state write that never happened."""

    before = _snapshot(legacy_project)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("state commit exploded")

    monkeypatch.setattr(engine, "_commit_state", explode)
    with pytest.raises(RuntimeError, match="state commit exploded"):
        apply_migration(legacy_project)

    assert _snapshot(legacy_project) == before
    assert get_current_version(legacy_project) == "1.0"


def test_upgrade_check_reports_a_pending_upgrade(
    legacy_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["upgrade", "check", "--root", str(legacy_project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"]
    assert payload["data"]["current_version"] == "1.0"
    assert payload["data"]["target_version"] == "1.5"
    assert payload["data"]["pending_migrations"] == ["001", "002", "003", "004", "005"]


def test_upgrade_plan_names_every_required_section(
    legacy_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["upgrade", "plan", "--root", str(legacy_project)])
    output = capsys.readouterr().out

    assert exit_code == 0
    for heading in (
        "Source version:",
        "Target version:",
        "Migrations (5):",
        "Affected files",
        "Destructive changes:",
        "Manual actions:",
        "Expected compatibility impact:",
    ):
        assert heading in output, heading


def test_upgrade_apply_requires_acknowledgement_when_non_interactive(
    legacy_project: Path,
) -> None:
    exit_code = cli.main(["upgrade", "apply", "--root", str(legacy_project)])

    assert exit_code == 2
    assert get_current_version(legacy_project) == "1.0"


def test_upgrade_apply_json_is_one_envelope(
    legacy_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        ["upgrade", "apply", "--root", str(legacy_project), "--yes", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"]
    assert payload["operation"] == "framework.upgrade"
    assert payload["data"]["source_version"] == "1.0"
    assert payload["data"]["target_version"] == "1.5"
    assert get_current_version(legacy_project) == "1.5"
