from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.critical_path import (
    CriticalPathCycleError,
    CriticalPathInputError,
    CriticalPathNotFoundError,
    CriticalPathService,
    PathCalculationRequest,
)
from practical_game_studio.decisions import (
    DecisionCreateRequest,
    DecisionOption,
    DecisionPatch,
    DecisionService,
)
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidencePatch,
    EvidenceService,
)
from practical_game_studio.issues import (
    IssueCreateRequest,
    IssuePatch,
    IssueService,
)
from practical_game_studio.reporting import render_report_contents
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import TransactionError
from tests.conftest import managed_bytes

FIXED_NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _empty_path(root: Path, *, criterion_result: str = "pass") -> None:
    repository = StateRepository(root)
    path = repository.load_critical_path()
    path.update(
        {
            "items": [],
            "history": [],
            "recommended_next_id": None,
            "pinned_sources": [],
            "excluded_sources": [],
            "exclusion_reasons": {},
            "calculated_at": None,
            "calculation_snapshot": None,
            "freshness": {"status": "absent", "reasons": ["Not calculated."]},
            "warnings": [],
        }
    )
    milestone = repository.load_milestone()
    milestone["criteria_results"][0]["result"] = criterion_result
    _write_json(root / ".studio/state/critical-path.json", path)
    _write_json(root / ".studio/state/milestone.json", milestone)


def _issue(
    root: Path,
    title: str,
    severity: str,
    *,
    milestone_impact: str = "",
    player_impact: str = "",
    decision_required: bool = False,
) -> str:
    result = IssueService(root).create_issue(
        IssueCreateRequest(
            title=title,
            severity=severity,
            description=f"{title} description.",
            milestone_impact=milestone_impact,
            player_impact=player_impact,
            recommended_action=f"Complete {title}.",
            user_decision_required=decision_required,
        )
    )
    return result.details["issue"]["id"]


def _decision(
    root: Path,
    *,
    urgency: str = "blocking",
    status: str = "ready",
    issue_ids: tuple[str, ...] = (),
    context: str = "This choice gates implementation.",
    required_by: str | None = None,
) -> str:
    result = DecisionService(root).create_decision(
        DecisionCreateRequest(
            question="Choose the guidance approach",
            context=context,
            urgency=urgency,
            decision_owner="user",
            options=(
                DecisionOption(
                    id="OPT-A",
                    label="Lighting",
                    description="Guide with lighting.",
                    benefits=("Diegetic",),
                    risks=("Subtle",),
                ),
                DecisionOption(
                    id="OPT-B",
                    label="Markers",
                    description="Guide with markers.",
                    benefits=("Clear",),
                    risks=("Less immersive",),
                ),
            ),
            recommended_option="OPT-A",
            recommendation_reason="It preserves the intended tone.",
            affected_issues=issue_ids,
            decision_required_by=required_by,
            status=status,
        )
    )
    return result.details["decision"]["id"]


def _service(root: Path) -> CriticalPathService:
    return CriticalPathService(root, clock=lambda: FIXED_NOW)


@pytest.mark.parametrize(
    ("severity", "milestone_impact", "selected", "tier"),
    [
        ("blocker", "Build cannot run.", True, 1),
        ("critical", "", True, 2),
        ("major", "Directly blocks the milestone.", True, 5),
        ("minor", "Cosmetic.", False, 5),
        ("later", "Future work.", False, 5),
    ],
)
def test_issue_candidate_tiers(
    framework_repo: Path,
    severity: str,
    milestone_impact: str,
    selected: bool,
    tier: int,
) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(
        framework_repo,
        f"{severity} issue",
        severity,
        milestone_impact=milestone_impact,
        player_impact="Core loop impact." if severity == "critical" else "",
    )

    candidate = next(
        item
        for item in _service(framework_repo).collect_candidates()
        if item.source_key == f"issue:{issue_id}"
    )

    assert candidate.default_selected is selected
    assert candidate.priority_tier == tier


def test_decision_candidates_include_blocking_and_current_milestone_high(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    first = _decision(framework_repo, urgency="blocking")
    second = _decision(framework_repo, urgency="high")

    candidates = {
        item.source_key: item for item in _service(framework_repo).collect_candidates()
    }

    assert candidates[f"decision:{first}"].priority_tier == 1
    assert candidates[f"decision:{first}"].default_selected
    assert candidates[f"decision:{second}"].priority_tier == 3
    assert candidates[f"decision:{second}"].default_selected


def test_resolved_decision_is_not_a_candidate(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    decision_id = _decision(framework_repo)
    decisions = StateRepository(framework_repo).load_decisions()
    record = decisions["decisions"][0]
    record.update(
        {
            "status": "rejected",
            "updated_at": "2026-07-27T00:00:00Z",
        }
    )
    _write_json(framework_repo / ".studio/state/decisions.json", decisions)

    keys = {item.source_key for item in _service(framework_repo).collect_candidates()}

    assert f"decision:{decision_id}" not in keys


def test_near_required_by_decision_is_selected_deterministically(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    decision_id = _decision(
        framework_repo,
        urgency="medium",
        required_by="2026-07-30",
    )

    candidate = next(
        item
        for item in _service(framework_repo).collect_candidates()
        if item.source_key == f"decision:{decision_id}"
    )

    assert candidate.default_selected
    assert candidate.priority_tier == 5


def test_deferred_decision_returns_when_required_criterion_depends_on_it(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    decision_id = _decision(
        framework_repo,
        urgency="medium",
    )
    DecisionService(framework_repo).update_decision(
        decision_id, DecisionPatch(values={"status": "deferred"})
    )
    milestone = StateRepository(framework_repo).load_milestone()
    criterion = milestone["criteria_results"][0]
    criterion["result"] = "unknown"
    criterion["related_decisions"] = [decision_id]
    _write_json(framework_repo / ".studio/state/milestone.json", milestone)

    candidate = next(
        item
        for item in _service(framework_repo).collect_candidates()
        if item.source_key == f"decision:{decision_id}"
    )

    assert candidate.default_selected
    assert candidate.priority_tier == 3


def test_required_unsupported_criterion_generates_concrete_verification(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo, criterion_result="unknown")

    candidate = next(
        item
        for item in _service(framework_repo).collect_candidates()
        if item.source_key == "verification:MC-001:observed-support"
    )

    assert candidate.type == "verification"
    assert "Test whether" in candidate.description
    assert "Attach active observed evidence" in candidate.completion_condition
    assert candidate.priority_tier == 4


def test_blocked_unsupported_decision_gets_verification_prerequisite(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    decision_id = _decision(
        framework_repo,
        status="blocked",
        context="Observed evidence is required before choosing.",
    )

    result = _service(framework_repo).calculate_path(PathCalculationRequest())
    keys = [item.source_key for item in result.active_items]

    verification = f"verification:{decision_id}:observed-support"
    assert keys.index(verification) < keys.index(f"decision:{decision_id}")


def test_user_reported_critical_issue_generates_explicit_reproduction(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(framework_repo, "Reported crash", "critical")
    issues = StateRepository(framework_repo).load_issues()
    record = issues["issues"][0]
    record["evidence_type"] = "USER_REPORTED"
    record["description"] = "Reproduce the reported crash before implementing."
    _write_json(framework_repo / ".studio/state/issues.json", issues)

    candidates = _service(framework_repo).collect_candidates()

    verification = next(
        item
        for item in candidates
        if item.source_key == f"verification:{issue_id}:reproduction"
    )
    issue = next(item for item in candidates if item.source_key == f"issue:{issue_id}")
    assert verification.source_key in issue.dependency_keys
    assert "Capture active observed" in verification.completion_condition


def test_optional_unsupported_criterion_is_excluded(framework_repo: Path) -> None:
    _empty_path(framework_repo, criterion_result="unknown")
    milestone = StateRepository(framework_repo).load_milestone()
    milestone["criteria_results"][0]["required"] = False
    _write_json(framework_repo / ".studio/state/milestone.json", milestone)

    candidates = _service(framework_repo).collect_candidates()

    assert not any(item.source_id == "MC-001" for item in candidates)


def test_manual_action_is_preserved(framework_repo: Path) -> None:
    candidates = _service(framework_repo).collect_candidates()

    manual = next(
        item for item in candidates if item.source_key == "manual:guided-intake"
    )

    assert manual.manual
    assert manual.default_selected


def test_decision_orders_before_dependent_issue(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(
        framework_repo,
        "Implement guidance",
        "critical",
        decision_required=True,
    )
    decision_id = _decision(framework_repo, issue_ids=(issue_id,))

    result = _service(framework_repo).calculate_path(PathCalculationRequest())
    keys = [item.source_key for item in result.active_items]

    assert keys.index(f"decision:{decision_id}") < keys.index(f"issue:{issue_id}")


def test_blocker_then_decision_then_dependent_issue_scenario(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    launch = _issue(framework_repo, "Fix launch", "blocker")
    implementation = _issue(
        framework_repo,
        "Implement guidance",
        "critical",
        decision_required=True,
    )
    decision = _decision(framework_repo, issue_ids=(implementation,))
    IssueService(framework_repo).update_issue(
        implementation,
        IssuePatch(add_dependencies=(launch,)),
    )

    result = _service(framework_repo).calculate_path(PathCalculationRequest())
    keys = [item.source_key for item in result.active_items]

    assert len(keys) == 3
    assert keys[-1] == f"issue:{implementation}"
    assert set(keys[:2]) == {f"issue:{launch}", f"decision:{decision}"}


def test_dependency_chain_is_topological_even_when_prerequisite_is_minor(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    prerequisite = _issue(framework_repo, "Prepare fixture", "minor")
    blocker = _issue(
        framework_repo,
        "Fix launch",
        "blocker",
        milestone_impact="No build can launch.",
    )
    IssueService(framework_repo).update_issue(
        blocker, IssuePatch(add_dependencies=(prerequisite,))
    )

    result = _service(framework_repo).calculate_path(PathCalculationRequest())
    keys = [item.source_key for item in result.active_items]

    assert keys == [f"issue:{prerequisite}", f"issue:{blocker}"]


def test_shared_prerequisite_appears_once(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    shared = _issue(framework_repo, "Shared setup", "minor")
    first = _issue(framework_repo, "First blocker", "blocker")
    second = _issue(framework_repo, "Second blocker", "blocker")
    service = IssueService(framework_repo)
    service.update_issue(first, IssuePatch(add_dependencies=(shared,)))
    service.update_issue(second, IssuePatch(add_dependencies=(shared,)))

    result = _service(framework_repo).calculate_path(PathCalculationRequest())
    keys = [item.source_key for item in result.active_items]

    assert keys.count(f"issue:{shared}") == 1
    assert keys.index(f"issue:{shared}") < keys.index(f"issue:{first}")
    assert keys.index(f"issue:{shared}") < keys.index(f"issue:{second}")


def test_dependency_cycle_reports_exact_cycle(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    first = _issue(framework_repo, "First", "blocker")
    second = _issue(framework_repo, "Second", "critical")
    service = IssueService(framework_repo)
    service.update_issue(first, IssuePatch(add_dependencies=(second,)))
    service.update_issue(second, IssuePatch(add_dependencies=(first,)))

    with pytest.raises(CriticalPathCycleError, match=r"issue:ISS-000[12].*issue"):
        _service(framework_repo).calculate_path(PathCalculationRequest())


def test_fewer_than_three_is_valid_and_not_padded(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Only blocker", "blocker")

    result = _service(framework_repo).calculate_path(PathCalculationRequest())

    assert len(result.active_items) == 1
    assert any("Fewer than three" in warning for warning in result.warnings)


def test_empty_calculated_path_is_current_when_milestone_has_no_gates(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    service = _service(framework_repo)

    result = service.apply_path(PathCalculationRequest())

    assert result.details["active_count"] == 0
    assert service.check_freshness().current


def test_more_than_max_independent_candidates_is_reduced(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    for index in range(9):
        _issue(framework_repo, f"Blocker {index}", "blocker")

    result = _service(framework_repo).calculate_path(
        PathCalculationRequest(max_items=7)
    )

    assert len(result.active_items) == 7
    assert not any("could not be reduced" in warning for warning in result.warnings)


def test_mandatory_dependency_chain_can_exceed_max_with_warning(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    ids = [
        _issue(
            framework_repo,
            f"Chain {index}",
            "blocker" if index == 7 else "minor",
        )
        for index in range(8)
    ]
    service = IssueService(framework_repo)
    for index in range(1, len(ids)):
        service.update_issue(ids[index], IssuePatch(add_dependencies=(ids[index - 1],)))

    result = _service(framework_repo).calculate_path(
        PathCalculationRequest(max_items=7)
    )

    assert len(result.active_items) == 8
    assert any("could not be reduced safely" in warning for warning in result.warnings)


@pytest.mark.parametrize("maximum", [2, 11])
def test_invalid_custom_maximum_is_rejected(framework_repo: Path, maximum: int) -> None:
    with pytest.raises(CriticalPathInputError, match="between 3 and 10"):
        _service(framework_repo).calculate_path(
            PathCalculationRequest(max_items=maximum)
        )


def test_stable_ids_survive_reordering_and_title_change(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    first = _issue(framework_repo, "First", "critical")
    second = _issue(framework_repo, "Second", "major", milestone_impact="Direct.")
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())
    before = StateRepository(framework_repo).load_critical_path()
    ids = {item["source_key"]: item["id"] for item in before["items"]}

    IssueService(framework_repo).update_issue(
        second,
        IssuePatch(values={"severity": "blocker", "title": "Renamed blocker"}),
    )
    service.apply_path(PathCalculationRequest())
    after = StateRepository(framework_repo).load_critical_path()

    assert {item["source_key"]: item["id"] for item in after["items"]} == ids
    assert after["items"][0]["source_id"] == second
    assert first != second


def test_resolved_source_moves_to_history_and_reopen_reuses_id(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(framework_repo, "Resolve me", "blocker")
    path_service = _service(framework_repo)
    path_service.apply_path(PathCalculationRequest())
    original_id = StateRepository(framework_repo).load_critical_path()["items"][0]["id"]
    issue_service = IssueService(framework_repo)
    issue_service.update_issue(
        issue_id,
        IssuePatch(values={"status": "resolved", "resolution": "Fixed."}),
    )
    path_service.apply_path(PathCalculationRequest())
    resolved = StateRepository(framework_repo).load_critical_path()
    assert resolved["history"][0]["id"] == original_id
    assert resolved["history"][0]["status"] == "completed"

    issue_service.update_issue(issue_id, IssuePatch(values={"status": "open"}))
    path_service.apply_path(PathCalculationRequest())
    reopened = StateRepository(framework_repo).load_critical_path()
    assert reopened["items"][0]["id"] == original_id


def test_dry_run_preserves_bytes_and_next_real_ids(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Dry-run blocker", "blocker")
    before = managed_bytes(framework_repo)
    service = _service(framework_repo)

    preview = service.apply_path(PathCalculationRequest(), dry_run=True)
    preview_id = preview.details["items"][0]["id"]

    assert managed_bytes(framework_repo) == before
    actual = service.apply_path(PathCalculationRequest())
    assert actual.details["items"][0]["id"] == preview_id


def test_noop_recalculation_preserves_all_bytes(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Stable blocker", "blocker")
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())
    before = managed_bytes(framework_repo)

    result = service.apply_path(PathCalculationRequest())

    assert result.details["no_op"]
    assert managed_bytes(framework_repo) == before


def test_manual_include_and_exclude_persist(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    included = _issue(framework_repo, "Pinned minor", "minor")
    excluded = _issue(framework_repo, "Excluded blocker", "blocker")

    _service(framework_repo).apply_path(
        PathCalculationRequest(
            include=(included,),
            exclude=(excluded,),
            exclude_reason="Blocked by external timing.",
        )
    )
    path = StateRepository(framework_repo).load_critical_path()

    assert f"issue:{included}" in path["pinned_sources"]
    assert f"issue:{excluded}" in path["excluded_sources"]
    assert path["exclusion_reasons"][f"issue:{excluded}"] == (
        "Blocked by external timing."
    )
    assert any(item["source_id"] == included for item in path["items"])
    assert not any(item["source_id"] == excluded for item in path["items"])


def test_pinned_source_that_becomes_completed_warns_and_is_removed(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(framework_repo, "Pinned blocker", "blocker")
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest(include=(issue_id,)))
    IssueService(framework_repo).update_issue(
        issue_id,
        IssuePatch(values={"status": "resolved", "resolution": "Done."}),
    )
    path = StateRepository(framework_repo).load_critical_path()
    path["pinned_sources"] = [f"issue:{issue_id}"]
    _write_json(framework_repo / ".studio/state/critical-path.json", path)

    result = service.apply_path(PathCalculationRequest())

    assert any("Pinned source" in warning for warning in result.warnings)
    assert not StateRepository(framework_repo).load_critical_path()["pinned_sources"]


def test_excluding_required_prerequisite_is_rejected(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    prerequisite = _issue(framework_repo, "Required minor", "minor")
    blocker = _issue(framework_repo, "Dependent blocker", "blocker")
    IssueService(framework_repo).update_issue(
        blocker, IssuePatch(add_dependencies=(prerequisite,))
    )

    with pytest.raises(CriticalPathInputError, match="is required by"):
        _service(framework_repo).calculate_path(
            PathCalculationRequest(
                exclude=(prerequisite,),
                exclude_reason="Try to skip it.",
            )
        )


def test_freshness_detects_status_change_and_new_blocker(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(framework_repo, "Original blocker", "blocker")
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())
    assert service.check_freshness().current

    IssueService(framework_repo).update_issue(
        issue_id,
        IssuePatch(values={"status": "resolved", "resolution": "Done."}),
    )
    _issue(framework_repo, "New blocker", "blocker")
    freshness = service.check_freshness()

    assert freshness.status == "stale"
    assert any("is now resolved" in reason for reason in freshness.reasons)
    assert any("new hard milestone blocker" in reason for reason in freshness.reasons)


def test_freshness_detects_decision_status_change(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    decision_id = _decision(framework_repo)
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())

    DecisionService(framework_repo).update_decision(
        decision_id, DecisionPatch(values={"status": "blocked"})
    )

    freshness = service.check_freshness()
    assert freshness.status == "stale"
    assert any(decision_id in reason for reason in freshness.reasons)


def test_freshness_detects_evidence_support_change(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    issue_id = _issue(framework_repo, "Evidence-backed blocker", "blocker")
    evidence = (
        EvidenceService(framework_repo)
        .create_evidence(
            EvidenceCreateRequest(
                title="Launch observation",
                claim="The prototype does not launch.",
                classification="observed",
                source_type="test-output",
                source="launch-test.log",
                related_issues=(issue_id,),
            )
        )
        .details["evidence"]["id"]
    )
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())

    EvidenceService(framework_repo).update_evidence(
        evidence, EvidencePatch(values={"status": "retracted"})
    )

    freshness = service.check_freshness()
    assert freshness.status == "stale"
    assert any("evidence" in reason.casefold() for reason in freshness.reasons)


def test_freshness_detects_milestone_and_criterion_changes(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Milestone blocker", "blocker")
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())
    project = StateRepository(framework_repo).load_project()
    project["current_milestone"] = "A changed milestone"
    _write_json(framework_repo / ".studio/state/project.json", project)
    milestone = StateRepository(framework_repo).load_milestone()
    milestone["criteria_results"][0]["result"] = "unknown"
    _write_json(framework_repo / ".studio/state/milestone.json", milestone)

    freshness = service.check_freshness()

    assert freshness.status == "stale"
    assert any("Milestone changed" in reason for reason in freshness.reasons)
    assert any("criterion state changed" in reason for reason in freshness.reasons)


def test_explanation_has_source_dependencies_and_downstream(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    prerequisite = _issue(
        framework_repo, "Prerequisite", "major", milestone_impact="Gates."
    )
    blocker = _issue(framework_repo, "Blocker", "blocker")
    IssueService(framework_repo).update_issue(
        blocker, IssuePatch(add_dependencies=(prerequisite,))
    )
    service = _service(framework_repo)
    service.apply_path(PathCalculationRequest())
    path = StateRepository(framework_repo).load_critical_path()
    item_id = next(
        item["id"] for item in path["items"] if item["source_id"] == prerequisite
    )

    explanation = service.explain_item(item_id)

    assert explanation.source["id"] == prerequisite
    assert explanation.downstream_items
    assert explanation.item["completion_condition"]


def test_missing_explanation_item_is_actionable(framework_repo: Path) -> None:
    with pytest.raises(CriticalPathNotFoundError, match="studio path show --all"):
        _service(framework_repo).explain_item("CP-9999")


def test_calculation_result_is_independent_of_input_copy(
    framework_repo: Path,
) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Copy-safe blocker", "blocker")
    state = StateRepository(framework_repo).load_all()
    untouched = copy.deepcopy(state)

    _service(framework_repo).calculate_path(PathCalculationRequest(), state=state)

    assert state == untouched


def test_path_report_render_failure_writes_nothing(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Transactional blocker", "blocker")
    before = managed_bytes(framework_repo)

    def fail(_: object) -> dict[str, str]:
        raise RuntimeError("injected path renderer failure")

    with pytest.raises(TransactionError, match="report-render"):
        CriticalPathService(
            framework_repo,
            clock=lambda: FIXED_NOW,
            report_renderer=fail,
        ).apply_path(PathCalculationRequest())

    assert managed_bytes(framework_repo) == before


def test_path_concurrent_modification_aborts(framework_repo: Path) -> None:
    _empty_path(framework_repo)
    _issue(framework_repo, "Concurrent blocker", "blocker")
    project_path = framework_repo / ".studio/state/project.json"
    original_renderer = render_report_contents

    def mutate_during_render(state: object) -> dict[str, str]:
        project_path.write_bytes(project_path.read_bytes() + b" ")
        return original_renderer(state)  # type: ignore[arg-type]

    with pytest.raises(TransactionError, match="concurrent-modification"):
        CriticalPathService(
            framework_repo,
            clock=lambda: FIXED_NOW,
            report_renderer=mutate_during_render,
        ).apply_path(PathCalculationRequest())
