"""Deterministic Markdown generation from canonical JSON state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import OPEN_ISSUE_STATUSES, SEVERITIES, build_status_summary, load_state

WARNING = "<!-- Generated file. Do not edit manually. -->"


def _bullets(values: list[str], empty: str = "None recorded.") -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def _open_issues(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in state["issues"]["issues"]
        if issue["status"] in OPEN_ISSUE_STATUSES
    ]


def render_current_state(state: dict[str, Any]) -> str:
    project = state["project"]
    evidence = state["evidence"]["evidence"]
    blockers = [
        f"{issue['id']}: {issue['title']}"
        for issue in _open_issues(state)
        if issue["severity"] in {"blocker", "critical"} or issue["status"] == "blocked"
    ]
    evidence_lines = [
        f"{item['id']} [{item['type']}] {item['description']}" for item in evidence
    ]
    return f"""{WARNING}
# Current State

## Current Goal

{project["current_milestone"]}

## Project Profile

- Project: {project["project_name"]}
- Engine: {project["engine"] or "Unknown"}
- Engine version: {project["engine_version"] or "Unknown"}
- Platform: {project["platform"] or "Unknown"}
- Genre: {project["genre"] or "Unknown"}
- Phase: {project["current_phase"]}
- Review mode: {project["review_mode"]}
- Build status: {project["current_build_status"]}
- Last verified: {project["last_verified_date"] or "Never"}

## Current Evidence

{_bullets(evidence_lines, "No evidence recorded.")}

## Current Blockers

{_bullets(blockers, "No blocker or critical issue recorded.")}

## Recommended Next Action

Run `{project["recommended_next_playbook"]}`.
"""


def render_direction_report(state: dict[str, Any]) -> str:
    project = state["project"]
    milestone = state["milestone"]
    evidence = state["evidence"]["evidence"]
    decisions = [
        decision
        for decision in state["decisions"]["decisions"]
        if decision["status"] == "pending"
    ]
    cp_items = state["critical_path"]["items"]
    learned = [f"[{item['type']}] {item['description']}" for item in evidence]
    evidence_lines = [
        f"{item['id']} — {item['source']} ({item['confidence']} confidence)"
        for item in evidence
    ]
    decision_lines = [
        f"{item['id']}: {item['question']} — recommendation: {item['recommended_option']}"
        for item in decisions
    ]
    critical_path_lines = [
        f"{index}. {item['id']}: {item['title']} — {item['why_critical']}"
        for index, item in enumerate(cp_items, 1)
    ]
    return f"""{WARNING}
# Direction Report

## Current State

- Current phase: {project["current_phase"]}
- Current milestone: {project["current_milestone"]}
- Build status: {project["current_build_status"]}
- Review mode: {project["review_mode"]}
- Prototype hypothesis: {project["prototype_hypothesis"] or "Not defined"}
- Milestone verdict: {milestone["verdict"]}

## What We Learned

{_bullets(learned, "No evidence-backed learning has been recorded yet.")}

## Evidence

{_bullets(evidence_lines, "No evidence recorded.")}

## Open Decisions

{_bullets(decision_lines, "No pending decisions recorded.")}

## Critical Path

{_bullets(critical_path_lines, "No valid critical-path items recorded.")}

## Recommended Next Step

{milestone["recommendation"]}

## Do Not Work On Yet

{_bullets(state["critical_path"]["non_critical_work"])}

## Next Command

`{project["recommended_next_playbook"]}`
"""


def render_open_issues(state: dict[str, Any]) -> str:
    issues = _open_issues(state)
    rows = [
        f"| {item['id']} | {item['severity']} | {item['status']} | {item['title']} | {item['evidence_type']} | {item['recommended_action']} |"
        for item in issues
    ]
    table = (
        "\n".join(rows)
        if rows
        else "| — | — | — | No open issues recorded | — | Run the next workflow |"
    )
    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        counts[issue["severity"]] += 1
    count_line = ", ".join(f"{severity}: {counts[severity]}" for severity in SEVERITIES)
    return f"""{WARNING}
# Open Issues

Open counts — {count_line}.

| ID | Severity | Status | Title | Evidence | Recommended action |
|---|---|---|---|---|---|
{table}
"""


def render_critical_path(state: dict[str, Any]) -> str:
    critical_path = state["critical_path"]
    sections = []
    for index, item in enumerate(critical_path["items"], 1):
        dependencies = ", ".join(item["dependencies"]) or "None"
        sections.append(
            f"### {index}. {item['id']}: {item['title']}\n\n"
            f"- Type: {item['type']}\n"
            f"- Blocked: {'yes' if item['blocked'] else 'no'}\n"
            f"- Dependencies: {dependencies}\n"
            f"- Why critical: {item['why_critical']}\n"
            f"- Exit condition: {item['exit_condition']}"
        )
    body = "\n\n".join(sections) or "No valid critical-path items recorded."
    return f"""{WARNING}
# Critical Path

## Current Milestone

{critical_path["current_milestone"]}

## Milestone Success Criteria

{_bullets(critical_path["milestone_success_criteria"])}

## Ordered Active Items

{body}

## Path Exit Condition

{critical_path["exit_condition"]}

## Non-Critical Work

{_bullets(critical_path["non_critical_work"])}
"""


def render_milestone_review(state: dict[str, Any]) -> str:
    milestone = state["milestone"]
    rows = [
        f"| {item['criterion']} | {item['result']} | {', '.join(item['evidence_references']) or 'None'} | {item['notes']} |"
        for item in milestone["criteria_results"]
    ]
    return f"""{WARNING}
# Milestone Review

## Milestone

{milestone["milestone"]}

## Success Criteria and Results

| Criterion | Result | Evidence | Notes |
|---|---|---|---|
{chr(10).join(rows) if rows else "| — | unknown | None | No criteria recorded |"}

## Supporting Evidence

{_bullets(milestone["supporting_evidence"], "No supporting evidence recorded.")}

## Blocking Issues

{_bullets(milestone["blocking_issues"], "No blocking issues recorded.")}

## Verdict

`{milestone["verdict"]}`

## Recommendation

{milestone["recommendation"]}

## Next Milestone

{milestone["next_milestone"] or "Not selected"}
"""


REPORT_RENDERERS = {
    "current-state.md": render_current_state,
    "direction-report.md": render_direction_report,
    "open-issues.md": render_open_issues,
    "critical-path.md": render_critical_path,
    "milestone-review.md": render_milestone_review,
}


def render_report_contents(state: dict[str, Any]) -> dict[str, str]:
    """Render every report deterministically without touching the filesystem."""

    return {
        filename: renderer(state).rstrip() + "\n"
        for filename, renderer in REPORT_RENDERERS.items()
    }


def generate_reports(root: Path) -> list[Path]:
    """Generate all human-facing reports and return their paths."""

    state = load_state(root)
    report_dir = root / ".studio" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for filename, content in render_report_contents(state).items():
        path = report_dir / filename
        path.write_text(content, encoding="utf-8")
        generated.append(path)
    return generated


def format_status(state: dict[str, Any]) -> str:
    """Render canonical project state for terminal use."""

    summary = build_status_summary(state)
    issue_counts = ", ".join(
        f"{severity}={count}"
        for severity, count in summary.open_issues_by_severity.items()
    )
    decisions = _bullets(summary.pending_decisions, "No pending user decisions.")
    path = _bullets(summary.critical_path_items, "No critical-path items.")
    return (
        f"Current phase: {summary.phase}\n"
        f"Current milestone: {summary.milestone}\n"
        f"Build status: {summary.build_status}\n"
        f"Open issues: {issue_counts}\n"
        "Pending user decisions:\n"
        f"{decisions}\n"
        "Critical-path items:\n"
        f"{path}\n"
        f"Recommended next playbook: {summary.recommended_next_playbook}"
    )
