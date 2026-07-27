from __future__ import annotations

from pathlib import Path

from practical_game_studio.issues import IssueCreateRequest, IssuePatch, IssueService
from practical_game_studio.reporting import (
    REPORT_RENDERERS,
    WARNING,
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
