from __future__ import annotations

import json
from pathlib import Path

import pytest
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
        "resolution": "Handled."
        if status in {"resolved", "accepted", "wont-fix"}
        else None,
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T00:00:00Z",
    }


def _valid_evidence(
    *,
    evidence_id: str = "EVD-0001",
    status: str = "active",
    supersedes: str | None = None,
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "title": "Observed result",
        "claim": "The prototype launched.",
        "classification": "observed",
        "source_type": "test-output",
        "source": "pytest output",
        "description": "Launch command completed.",
        "related_hypothesis": None,
        "related_issues": [],
        "confidence": "medium",
        "limitations": [],
        "captured_at": "2026-07-27T00:00:00Z",
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T00:00:00Z",
        "status": status,
        "supersedes": supersedes,
    }


def _set_path_issue(item: dict[str, object], issue_id: str) -> None:
    item.update(
        {
            "type": "issue",
            "source_id": issue_id,
            "source_key": f"issue:{issue_id}",
            "manual": False,
        }
    )


def _set_path_decision(item: dict[str, object], decision_id: str) -> None:
    item.update(
        {
            "type": "decision",
            "source_id": decision_id,
            "source_key": f"decision:{decision_id}",
            "manual": False,
        }
    )


def _valid_decision(
    *,
    decision_id: str = "DEC-0001",
    status: str = "ready",
    supersedes: str | None = None,
) -> dict[str, object]:
    resolved = status == "resolved"
    resolution = {
        "final_decision": "OPT-B — Signs",
        "final_option_id": "OPT-B",
        "decision_reason": "Preserve immersion.",
        "consequences": ["Update signage."],
        "follow_up_actions": ["Retest."],
        "revisit_condition": None,
        "recommendation_followed": True,
        "resolved_at": "2026-07-27T01:00:00Z",
    }
    return {
        "id": decision_id,
        "question": "How should the player find the room?",
        "context": "The corridor is unclear.",
        "phase": "evaluate",
        "milestone": "Clarify the game idea",
        "urgency": "high",
        "status": status,
        "options": [
            {
                "id": "OPT-A",
                "label": "Waypoint",
                "description": "Show a marker.",
                "benefits": [],
                "risks": [],
                "effort": None,
            },
            {
                "id": "OPT-B",
                "label": "Signs",
                "description": "Improve signage.",
                "benefits": [],
                "risks": [],
                "effort": None,
            },
        ],
        "recommended_option": "OPT-B",
        "recommendation_reason": "Preserves immersion.",
        "trade_offs": [],
        "affected_issues": [],
        "supporting_evidence": [],
        "decision_owner": "user",
        "decision_required_by": None,
        "final_decision": resolution["final_decision"] if resolved else None,
        "final_option_id": resolution["final_option_id"] if resolved else None,
        "decision_reason": resolution["decision_reason"] if resolved else None,
        "consequences": resolution["consequences"] if resolved else [],
        "follow_up_actions": resolution["follow_up_actions"] if resolved else [],
        "revisit_condition": None,
        "recommendation_followed": True if resolved else None,
        "resolved_at": resolution["resolved_at"] if resolved else None,
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T01:00:00Z" if resolved else "2026-07-27T00:00:00Z",
        "supersedes": supersedes,
        "resolution_history": [resolution] if resolved else [],
    }


def test_resolved_issue_cannot_remain_on_active_path(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    state["issues"]["issues"] = [_valid_issue(status="resolved")]
    _set_path_issue(state["critical_path"]["items"][0], "ISS-001")

    result = validate_state(framework_repo, state)

    assert any("inactive issue ISS-001" in error for error in result.errors)


def test_issue_evidence_reference_must_exist(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["evidence_references"] = ["EVD-999"]
    issue["on_critical_path"] = False
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any("broken evidence reference EVD-999" in error for error in result.errors)


def test_freeform_issue_evidence_reference_is_not_canonical(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["evidence_references"] = ["screenshots/corridor.png"]
    issue["on_critical_path"] = False
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any(
        "broken evidence reference screenshots/corridor.png" in error
        for error in result.errors
    )


def test_critical_path_decision_reference_must_exist(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    _set_path_decision(state["critical_path"]["items"][0], "DEC-999")

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

    assert any(
        "Duplicate critical-path id: CP-0001" in error for error in result.errors
    )


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


def test_duplicate_issue_ids_fail_relationship_validation(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    first = _valid_issue()
    first["on_critical_path"] = False
    state["issues"]["issues"] = [first, dict(first)]

    result = validate_state(framework_repo, state)

    assert "Duplicate issue id: ISS-001" in result.errors


def test_issue_cannot_depend_on_or_block_itself(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["on_critical_path"] = False
    issue["dependencies"] = ["ISS-001"]
    issue["issues_blocked"] = ["ISS-001"]
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any("cannot depend on itself" in error for error in result.errors)
    assert any("cannot block itself" in error for error in result.errors)


def test_terminal_issue_requires_resolution(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue(status="wont-fix")
    issue["on_critical_path"] = False
    issue["resolution"] = None
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any("resolution is required" in error for error in result.errors)


def test_issue_timestamp_order_is_validated(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["on_critical_path"] = False
    issue["created_at"] = "2026-07-27T02:00:00Z"
    issue["updated_at"] = "2026-07-27T01:00:00Z"
    state["issues"]["issues"] = [issue]

    result = validate_state(framework_repo, state)

    assert any("updated_at cannot be earlier" in error for error in result.errors)


def test_issue_cannot_appear_twice_on_critical_path(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    state["issues"]["issues"] = [issue]
    first = state["critical_path"]["items"][0]
    _set_path_issue(first, "ISS-001")
    duplicate = dict(first)
    duplicate["id"] = "CP-0002"
    state["critical_path"]["items"].append(duplicate)

    result = validate_state(framework_repo, state)

    assert any("duplicate source key issue:ISS-001" in error for error in result.errors)


def test_evidence_issue_links_must_be_bidirectional(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["on_critical_path"] = False
    evidence = _valid_evidence()
    evidence["related_issues"] = ["ISS-001"]
    state["issues"]["issues"] = [issue]
    state["evidence"]["evidence"] = [evidence]

    result = validate_state(framework_repo, state)

    assert any("issue link ISS-001 is one-sided" in error for error in result.errors)


def test_issue_evidence_type_matches_active_links(framework_repo: Path) -> None:
    state = StateRepository(framework_repo).load_all()
    issue = _valid_issue()
    issue["on_critical_path"] = False
    issue["evidence_references"] = ["EVD-0001"]
    issue["evidence_type"] = "OBSERVED"
    evidence = _valid_evidence(status="retracted")
    evidence["related_issues"] = ["ISS-001"]
    state["issues"]["issues"] = [issue]
    state["evidence"]["evidence"] = [evidence]

    result = validate_state(framework_repo, state)

    assert any(
        "does not match active linked evidence" in error for error in result.errors
    )


def test_evidence_source_rule_and_timestamp_order_are_validated(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    evidence = _valid_evidence()
    evidence["source"] = None
    evidence["updated_at"] = "2026-07-26T00:00:00Z"
    state["evidence"]["evidence"] = [evidence]

    result = validate_state(framework_repo, state)

    assert any("source is required" in error for error in result.errors)
    assert any("updated_at cannot be earlier" in error for error in result.errors)


def test_evidence_self_and_circular_supersession_are_invalid(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    first = _valid_evidence(
        evidence_id="EVD-0001",
        status="superseded",
        supersedes="EVD-0002",
    )
    second = _valid_evidence(
        evidence_id="EVD-0002",
        status="superseded",
        supersedes="EVD-0001",
    )
    state["evidence"]["evidence"] = [first, second]

    result = validate_state(framework_repo, state)

    assert any("circular supersession" in error for error in result.errors)

    first["supersedes"] = "EVD-0001"
    result = validate_state(framework_repo, state)
    assert any("cannot supersede itself" in error for error in result.errors)


def test_inactive_evidence_cannot_be_current_milestone_support(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    old = _valid_evidence(evidence_id="EVD-0001", status="superseded")
    replacement = _valid_evidence(evidence_id="EVD-0002", supersedes="EVD-0001")
    state["evidence"]["evidence"] = [old, replacement]
    state["milestone"]["supporting_evidence"] = ["EVD-0001"]

    result = validate_state(framework_repo, state)

    assert any("inactive evidence EVD-0001" in error for error in result.errors)


def test_decision_option_and_reference_relationships_are_validated(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    decision = _valid_decision()
    decision["options"][1]["id"] = "OPT-A"  # type: ignore[index]
    decision["affected_issues"] = ["ISS-9999"]
    decision["supporting_evidence"] = ["EVD-9999"]
    state["decisions"]["decisions"] = [decision]

    result = validate_state(framework_repo, state)

    assert any("duplicate option ID" in error for error in result.errors)
    assert any("broken issue reference" in error for error in result.errors)
    assert any("broken evidence reference" in error for error in result.errors)


def test_resolved_decision_requires_resolution_fields_and_history(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    decision = _valid_decision(status="resolved")
    decision["decision_reason"] = None
    decision["resolution_history"] = []
    state["decisions"]["decisions"] = [decision]

    result = validate_state(framework_repo, state)

    assert any("needs a reason" in error for error in result.errors)
    assert any("needs resolution history" in error for error in result.errors)


def test_decision_supersession_self_cycle_and_multiple_replacements(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    first = _valid_decision(
        decision_id="DEC-0001", status="superseded", supersedes="DEC-0002"
    )
    second = _valid_decision(
        decision_id="DEC-0002", status="superseded", supersedes="DEC-0001"
    )
    third = _valid_decision(decision_id="DEC-0003", supersedes="DEC-0001")
    state["decisions"]["decisions"] = [first, second, third]

    result = validate_state(framework_repo, state)

    assert any("circular supersession" in error for error in result.errors)
    assert any("more than one replacement" in error for error in result.errors)

    first["supersedes"] = "DEC-0001"
    result = validate_state(framework_repo, state)
    assert any("cannot supersede itself" in error for error in result.errors)


def test_closed_decision_cannot_remain_on_critical_path(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    state["decisions"]["decisions"] = [_valid_decision(status="resolved")]
    _set_path_decision(state["critical_path"]["items"][0], "DEC-0001")

    result = validate_state(framework_repo, state)

    assert any("historical decision DEC-0001" in error for error in result.errors)


def _dependency(
    dependency_id: str,
    prerequisite: str,
    dependent: str,
    *,
    status: str = "active",
) -> dict[str, object]:
    inactive = status == "inactive"
    return {
        "id": dependency_id,
        "prerequisite": prerequisite,
        "dependent": dependent,
        "relationship": "requires",
        "reason": "Explicit test ordering.",
        "scope": "current-milestone",
        "milestone": "Clarify the game idea",
        "status": status,
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T00:00:00Z",
        "deactivated_at": "2026-07-27T00:00:00Z" if inactive else None,
        "deactivation_reason": "No longer required." if inactive else None,
    }


def _two_off_path_issues(state: dict[str, object]) -> None:
    first = _valid_issue()
    second = _valid_issue()
    first["id"] = "ISS-001"
    second["id"] = "ISS-002"
    first["on_critical_path"] = False
    second["on_critical_path"] = False
    state["issues"]["issues"] = [first, second]  # type: ignore[index]


def test_dependency_missing_duplicate_and_cycle_validation(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "ISS-001", "ISS-002"),
        _dependency("DEP-0002", "ISS-001", "ISS-002"),
        _dependency("DEP-0003", "ISS-999", "ISS-001"),
    ]
    result = validate_state(framework_repo, state)
    assert any("Duplicate active dependency edge" in error for error in result.errors)
    assert any(
        "missing prerequisite endpoint ISS-999" in error for error in result.errors
    )

    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "ISS-001", "ISS-002"),
        _dependency("DEP-0002", "ISS-002", "ISS-001"),
    ]
    result = validate_state(framework_repo, state)
    assert any(
        "Dependency cycle: ISS-001 -> ISS-002 -> ISS-001" in error
        for error in result.errors
    )


def test_inactive_dependency_requires_deactivation_metadata(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    dependency = _dependency("DEP-0001", "ISS-001", "ISS-002", status="inactive")
    dependency["deactivated_at"] = None
    dependency["deactivation_reason"] = None
    state["dependencies"]["dependencies"] = [dependency]

    result = validate_state(framework_repo, state)

    assert any(
        "inactive dependency needs deactivated_at" in error for error in result.errors
    )
    assert any(
        "inactive dependency needs a deactivation reason" in error
        for error in result.errors
    )


@pytest.mark.parametrize("status", ["deferred", "wont-fix"])
def test_active_dependency_rejects_terminal_unsatisfied_issue(
    framework_repo: Path, status: str
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    state["issues"]["issues"][0]["status"] = status
    if status == "wont-fix":
        state["issues"]["issues"][0]["resolution"] = "Not fixed."
    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "ISS-001", "ISS-002")
    ]

    result = validate_state(framework_repo, state)

    assert any(
        f"Active dependency DEP-0001 references {status} prerequisite ISS-001" in error
        for error in result.errors
    )


@pytest.mark.parametrize("status", ["deferred", "rejected", "superseded"])
def test_active_dependency_rejects_terminal_unsatisfied_decision(
    framework_repo: Path, status: str
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    state["decisions"]["decisions"] = [_valid_decision(status=status)]
    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "DEC-0001", "ISS-002")
    ]

    result = validate_state(framework_repo, state)

    assert any(
        f"Active dependency DEP-0001 references {status} prerequisite DEC-0001" in error
        for error in result.errors
    )


@pytest.mark.parametrize(
    ("lifecycle", "support", "freshness", "status"),
    [
        ("retired", "unsupported", "current", "retired"),
        ("active", "verified", "stale", "verified"),
    ],
)
def test_active_dependency_rejects_terminal_unsatisfied_criterion(
    framework_repo: Path,
    lifecycle: str,
    support: str,
    freshness: str,
    status: str,
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    criterion = state["milestone"]["criteria_results"][0]
    criterion["lifecycle_status"] = lifecycle
    criterion["support_status"] = support
    criterion["evaluation_freshness"] = {
        "status": freshness,
        "reasons": [] if freshness == "current" else ["Policy changed."],
    }
    if lifecycle == "retired":
        criterion["retired_at"] = criterion["updated_at"]
        criterion["retirement_reason"] = "No longer required."
    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "MC-001", "ISS-002")
    ]

    result = validate_state(framework_repo, state)

    assert any(
        f"Active dependency DEP-0001 references {status} prerequisite MC-001" in error
        for error in result.errors
    )


def test_active_dependency_rejects_removed_manual_action(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    _two_off_path_issues(state)
    manual = state["critical_path"]["items"].pop()
    manual["status"] = "removed"
    state["critical_path"]["history"].append(manual)
    state["dependencies"]["dependencies"] = [
        _dependency("DEP-0001", "MANUAL:guided-intake", "ISS-002")
    ]

    result = validate_state(framework_repo, state)

    assert any(
        "Active dependency DEP-0001 references removed prerequisite "
        "MANUAL:guided-intake" in error
        for error in result.errors
    )


def test_verified_and_partial_criterion_truth_is_validated(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    criterion = state["milestone"]["criteria_results"][0]
    criterion["support_status"] = "verified"
    result = validate_state(framework_repo, state)
    assert any(
        "verified criterion requires active evidence" in error
        for error in result.errors
    )

    criterion["support_status"] = "partially-supported"
    criterion["supporting_evidence"] = ["EVD-0001"]
    state["evidence"]["evidence"] = [_valid_evidence()]
    result = validate_state(framework_repo, state)
    assert any(
        "partially supported criterion needs a limitation" in error
        for error in result.errors
    )


def test_current_criterion_evaluation_must_match_latest_history(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    criterion = state["milestone"]["criteria_results"][0]
    criterion.update(
        {
            "support_status": "unsupported",
            "evaluation_reason": "Current reason.",
            "evaluated_at": "2026-07-27T01:00:00Z",
            "evaluation_history": [
                {
                    "support_status": "unsupported",
                    "reason": "Different historical reason.",
                    "evidence_snapshot": [],
                    "issue_references": [],
                    "decision_references": [],
                    "limitations": [],
                    "evaluated_at": "2026-07-27T01:00:00Z",
                }
            ],
        }
    )

    result = validate_state(framework_repo, state)

    assert any("current evaluation reason differs" in error for error in result.errors)


def test_retired_criterion_cannot_remain_active_on_path(
    framework_repo: Path,
) -> None:
    state = StateRepository(framework_repo).load_all()
    criterion = state["milestone"]["criteria_results"][0]
    criterion["lifecycle_status"] = "retired"
    criterion["retired_at"] = "2026-07-27T00:00:00Z"
    criterion["retirement_reason"] = "No longer required."
    item = state["critical_path"]["items"][0]
    item.update(
        {
            "type": "verification",
            "source_id": "MC-001",
            "source_key": "verification:MC-001:observed-support",
            "manual": False,
        }
    )

    result = validate_state(framework_repo, state)

    assert any("retired criterion MC-001" in error for error in result.errors)
