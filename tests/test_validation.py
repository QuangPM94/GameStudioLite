from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from practical_game_studio.state import StateRepository
from practical_game_studio.validation import validate_project, validate_state

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_validates() -> None:
    result = validate_project(REPOSITORY_ROOT)
    assert result.ok, "\n".join(result.errors)


def test_invalid_severity_fails_schema_validation() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / ".studio" / "schemas" / "issues.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {"schema_version": "1.0", "issues": []}
    payload["issues"].append(
        {
            "id": "ISS-001",
            "title": "Invalid severity",
            "description": "Fixture exercises schema validation.",
            "severity": "catastrophic",
            "category": "other",
            "status": "open",
            "phase_discovered": "intake",
            "evidence_type": "UNKNOWN",
            "evidence_references": [],
            "player_impact": "Unknown",
            "milestone_impact": "Unknown",
            "recommended_action": "Classify correctly",
            "alternative_actions": [],
            "effort": "unknown",
            "dependencies": [],
            "issues_blocked": [],
            "on_critical_path": False,
            "user_decision_required": False,
            "owner": "unassigned",
            "resolution": None,
            "created_at": "2026-07-27T00:00:00Z",
            "updated_at": "2026-07-27T00:00:00Z",
        }
    )
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors
    assert any("catastrophic" in error.message for error in errors)


def _valid_issue(*, status: str = "open") -> dict[str, object]:
    return {
        "id": "ISS-001",
        "title": "Build blocker",
        "description": "A valid relationship test issue.",
        "severity": "blocker",
        "category": "build",
        "status": status,
        "phase_discovered": "intake",
        "evidence_type": "UNKNOWN",
        "evidence_references": [],
        "player_impact": "Testing is blocked.",
        "milestone_impact": "The milestone cannot be verified.",
        "recommended_action": "Resolve the blocker.",
        "alternative_actions": [],
        "effort": "small",
        "dependencies": [],
        "issues_blocked": [],
        "on_critical_path": True,
        "user_decision_required": False,
        "owner": "developer",
        "resolution": None,
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T00:00:00Z",
    }


def test_resolved_issue_cannot_remain_on_active_path(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["issues"]["issues"] = [_valid_issue(status="resolved")]
    state["critical_path"]["items"][0]["source_issue_id"] = "ISS-001"

    result = validate_state(framework_repo, state)

    assert any("closed issue ISS-001" in error for error in result.errors)


def test_issue_evidence_reference_must_exist(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["evidence_references"] = ["EVD-999"]
    issue["on_critical_path"] = False
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any("broken evidence reference EVD-999" in error for error in result.errors)


def test_critical_path_decision_reference_must_exist(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["critical_path"]["items"][0]["source_decision_id"] = "DEC-999"

    result = validate_state(framework_repo, state)

    assert any("broken source decision DEC-999" in error for error in result.errors)


def test_project_phase_must_exist_in_catalog(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["project"]["current_phase"] = "vertical-slice"

    result = validate_state(framework_repo, state)

    assert any(
        "not present in the workflow catalog" in error for error in result.errors
    )


def test_duplicate_critical_path_item_ids_fail(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["critical_path"]["items"].append(dict(state["critical_path"]["items"][0]))

    result = validate_state(framework_repo, state)

    assert any("Duplicate critical-path id: CP-001" in error for error in result.errors)


def test_recommended_workflow_must_exist(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["project"]["recommended_next_playbook"] = "/not-a-workflow"

    result = validate_state(framework_repo, state)

    assert any("recommended next playbook" in error for error in result.errors)


def test_milestone_verdict_must_be_allowed(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["milestone"]["verdict"] = "MAYBE"

    result = validate_state(framework_repo, state)

    assert any("MAYBE" in error for error in result.errors)


def test_stale_generated_report_is_detected(framework_repo: Path) -> None:
    path = framework_repo / ".studio" / "reports" / "current-state.md"
    path.write_text("stale\n", encoding="utf-8")

    result = validate_project(framework_repo)

    assert any(
        "current-state.md: generated report is stale" in error
        for error in result.errors
    )
