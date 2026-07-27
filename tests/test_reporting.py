from __future__ import annotations

from pathlib import Path

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
        "## Current State",
        "## What We Learned",
        "## Evidence",
        "## Evidence Summary",
        "## Open Decisions",
        "## Critical Path",
        "## Recommended Next Step",
        "## Do Not Work On Yet",
        "## Next Command",
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
    assert "## Critical-Path Issues" in open_issues
    assert "## Recently Resolved" in open_issues
    assert "ISS-0002 [major/resolved]" in open_issues
    direction = reports["direction-report.md"]
    assert "## Current Blockers" in direction
    assert "`/issue-map`" in direction


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
    direction = reports["direction-report.md"]
    assert "EVD-0001: Player stopped in corridor." in direction
    assert "EVD-0002" not in direction
    assert "This is a simulated player-experience review" not in direction


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
    assert "### Issues Lacking Evidence" in direction
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
    assert "| unsupported |" in reports["milestone-review.md"]


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
