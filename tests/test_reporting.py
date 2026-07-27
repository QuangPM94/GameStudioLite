from __future__ import annotations

from pathlib import Path

from practical_game_studio.decisions import (
    DecisionCreateRequest,
    DecisionOption,
    DecisionPatch,
    DecisionResolution,
    DecisionService,
)
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidencePatch,
    EvidenceService,
)
from practical_game_studio.issues import IssueCreateRequest, IssuePatch, IssueService
from practical_game_studio.reporting import (
    REPORT_RENDERERS,
    WARNING,
    format_status,
    generate_reports,
    render_report_contents,
)
from practical_game_studio.state import StateRepository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_report_generation_includes_warning_and_direction_sections() -> None:
    generated = generate_reports(REPOSITORY_ROOT)

    assert len(generated) == len(REPORT_RENDERERS)
    for path in generated:
        assert path.read_text(encoding="utf-8").startswith(WARNING)
    direction = (
        REPOSITORY_ROOT / ".studio" / "reports" / "direction-report.md"
    ).read_text(encoding="utf-8")
    for heading in (
        "## Required Criteria Remaining",
        "## Recommended Next Path Item",
        "## Blocking User Decision",
        "## Evidence Gap",
        "## Do Not Work On Yet",
    ):
        assert heading in direction


def test_issue_reports_prioritize_actionable_and_recent_history(
    framework_repo: Path,
) -> None:
    service = IssueService(framework_repo)
    service.create_issue(
        IssueCreateRequest(
            title="Build fails",
            severity="blocker",
            milestone_impact="No runnable prototype.",
            user_decision_required=True,
            on_critical_path=True,
        )
    )
    service.create_issue(
        IssueCreateRequest(
            title="Pacing dip",
            severity="major",
            player_impact="The corridor drags.",
        )
    )
    service.update_issue(
        "ISS-0002",
        IssuePatch(values={"status": "resolved", "resolution": "Shortened corridor."}),
    )
    reports = render_report_contents(StateRepository(framework_repo).load_all())

    open_issues = reports["open-issues.md"]
    assert "## Blockers" in open_issues
    assert "## Major Issues" in open_issues
    assert "## User Decisions Required" in open_issues
    assert "## On Milestone Critical Path" in open_issues
    assert "## Not On Milestone Critical Path" in open_issues
    assert "## Recently Resolved" in open_issues
    assert "ISS-0002 [major/resolved]" in open_issues
    direction = reports["direction-report.md"]
    assert "## Required Criteria Remaining" in direction
    assert "## Recommended Next Path Item" in direction


def test_evidence_reports_count_only_active_support(
    framework_repo: Path,
) -> None:
    issue_service = IssueService(framework_repo)
    issue_service.create_issue(
        IssueCreateRequest(
            title="Player cannot find room",
            severity="critical",
            player_impact="Progress stops.",
        )
    )
    evidence_service = EvidenceService(framework_repo)
    evidence_service.create_evidence(
        EvidenceCreateRequest(
            title="Observed corridor stop",
            claim="Player stopped in corridor.",
            classification="observed",
            source_type="runtime",
            description="Observed in accessible runtime.",
            related_issues=("ISS-0001",),
        )
    )
    evidence_service.create_evidence(
        EvidenceCreateRequest(
            title="Source review risk",
            claim="Door feedback may be unclear.",
            classification="inferred",
            source_type="source-review",
            description="Feedback path has no distinct state.",
            related_issues=("ISS-0001",),
        )
    )
    evidence_service.update_evidence(
        "EVD-0002", EvidencePatch(values={"status": "retracted"})
    )
    reports = render_report_contents(StateRepository(framework_repo).load_all())

    open_issues = reports["open-issues.md"]
    assert "1 observed; 0 user-reported; 0 inferred; 0 unknown" in open_issues
    current = reports["current-state.md"]
    assert "EVD-0001 [observed] Player stopped in corridor." in current
    assert "EVD-0002" not in current


def test_reports_identify_unsupported_issues_and_simulated_review(
    framework_repo: Path,
) -> None:
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Unsupported clarity risk",
            severity="critical",
            player_impact="Unknown.",
        )
    )
    EvidenceService(framework_repo).create_evidence(
        EvidenceCreateRequest(
            title="Source inference",
            claim="Door feedback may be unclear.",
            classification="inferred",
            source_type="source-review",
            description="Inferred from state transitions.",
        )
    )
    reports = render_report_contents(StateRepository(framework_repo).load_all())

    direction = reports["direction-report.md"]
    assert "## Evidence Gap" in direction
    assert "ISS-0001: Unsupported clarity risk" in direction
    assert (
        "This is a simulated player-experience review based on available artifacts."
        in direction
    )
    assert "It is not a substitute for an observed human playtest." in direction


def test_superseded_evidence_is_not_counted_as_current_support(
    framework_repo: Path,
) -> None:
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Clarity issue",
            severity="critical",
            player_impact="Progress stops.",
        )
    )
    service = EvidenceService(framework_repo)
    service.create_evidence(
        EvidenceCreateRequest(
            title="Old observation",
            claim="Old claim.",
            classification="observed",
            source_type="runtime",
            description="Old build.",
            related_issues=("ISS-0001",),
        )
    )
    service.create_evidence(
        EvidenceCreateRequest(
            title="Replacement report",
            claim="Replacement claim.",
            classification="user-reported",
            source_type="human-playtest",
            description="New build.",
            related_issues=("ISS-0001",),
        )
    )
    service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-0001"))
    reports = render_report_contents(StateRepository(framework_repo).load_all())

    assert (
        "0 observed; 1 user-reported; 0 inferred; 0 unknown"
        in reports["open-issues.md"]
    )
    assert "EVD-0001" not in reports["direction-report.md"]


def test_milestone_result_labels_are_evidence_support_labels(
    framework_repo: Path,
) -> None:
    reports = render_report_contents(StateRepository(framework_repo).load_all())
    assert "- Support status: unsupported" in reports["milestone-review.md"]


def test_status_includes_evidence_counts_and_unsupported_critical_issues(
    framework_repo: Path,
) -> None:
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Unsupported issue",
            severity="critical",
            player_impact="Progress may stop.",
        )
    )
    EvidenceService(framework_repo).create_evidence(
        EvidenceCreateRequest(
            title="Source inference",
            claim="Feedback may be unclear.",
            classification="inferred",
            source_type="source-review",
            description="Read from implementation.",
        )
    )
    output = format_status(StateRepository(framework_repo).load_all())
    assert "- Inferred: 1" in output
    assert "Critical issues without evidence: 1" in output


def _decision_request(**changes: object) -> DecisionCreateRequest:
    values: dict[str, object] = {
        "question": "How should the player find the room?",
        "context": "The current corridor is unclear.",
        "options": (
            DecisionOption("OPT-A", "Waypoint", "Show an explicit marker."),
            DecisionOption("OPT-B", "Signs", "Improve environmental guidance."),
        ),
        "recommended_option": "OPT-B",
        "recommendation_reason": "Signs preserve immersion.",
        "urgency": "blocking",
        "status": "ready",
    }
    values.update(changes)
    return DecisionCreateRequest(**values)  # type: ignore[arg-type]


def test_decision_reports_show_priority_support_and_related_issue(
    framework_repo: Path,
) -> None:
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Room is unclear",
            severity="critical",
            player_impact="Progress stops.",
        )
    )
    EvidenceService(framework_repo).create_evidence(
        EvidenceCreateRequest(
            title="Observed stop",
            claim="A player stopped in the corridor.",
            classification="observed",
            source_type="runtime",
            description="Observed in an accessible build.",
        )
    )
    DecisionService(framework_repo).create_decision(
        _decision_request(
            affected_issues=("ISS-0001",),
            supporting_evidence=("EVD-0001",),
        )
    )
    reports = render_report_contents(StateRepository(framework_repo).load_all())

    assert "DEC-0001 [blocking/ready]" in reports["direction-report.md"]
    assert "evidence: strong" in reports["direction-report.md"]
    assert "DEC-0001 — Ready" in reports["open-issues.md"]
    assert "## Relevant Decisions" in reports["milestone-review.md"]
    assert "evidence strong" in reports["milestone-review.md"]
    assert "Blocking: 1" in reports["current-state.md"]


def test_resolved_and_reopened_decisions_leave_and_return_to_pending_reports(
    framework_repo: Path,
) -> None:
    service = DecisionService(framework_repo)
    service.create_decision(_decision_request())
    service.resolve_decision(
        "DEC-0001",
        DecisionResolution(option_id="OPT-B", reason="Preserve immersion."),
    )
    resolved = render_report_contents(StateRepository(framework_repo).load_all())
    assert "DEC-0001 [blocking/ready]" not in resolved["direction-report.md"]

    service.update_decision("DEC-0001", DecisionPatch(values={"status": "open"}))
    reopened = render_report_contents(StateRepository(framework_repo).load_all())
    assert "DEC-0001 [blocking/open]" in reopened["direction-report.md"]


def test_status_shows_pending_decision_counts_and_next_required(
    framework_repo: Path,
) -> None:
    service = DecisionService(framework_repo)
    service.create_decision(_decision_request())
    service.create_decision(
        _decision_request(question="Second decision?", urgency="high")
    )
    output = format_status(StateRepository(framework_repo).load_all())
    assert "- Blocking: 1" in output
    assert "- High: 1" in output
    assert (
        "Next required decision:\nDEC-0001 — How should the player find the room?"
        in output
    )


def test_inactive_evidence_is_ignored_for_decision_support(
    framework_repo: Path,
) -> None:
    EvidenceService(framework_repo).create_evidence(
        EvidenceCreateRequest(
            title="Old observation",
            claim="An old build was unclear.",
            classification="observed",
            source_type="runtime",
            description="Old build.",
        )
    )
    EvidenceService(framework_repo).update_evidence(
        "EVD-0001", EvidencePatch(values={"status": "retracted"})
    )
    DecisionService(framework_repo).create_decision(
        _decision_request(supporting_evidence=("EVD-0001",))
    )
    reports = render_report_contents(StateRepository(framework_repo).load_all())
    assert "evidence: unsupported" in reports["direction-report.md"]
