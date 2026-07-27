"""Deterministic Markdown generation from canonical JSON state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import OPEN_ISSUE_STATUSES, SEVERITIES, build_status_summary, load_state

WARNING = "<!-- Generated file. Do not edit manually. -->"
SIMULATED_REVIEW_DISCLAIMER = (
    "This is a simulated player-experience review based on available artifacts.\n"
    "It is not a substitute for an observed human playtest."
)


def _bullets(values: list[str], empty: str = "None recorded.") -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def _open_issues(state: dict[str, Any]) -> list[dict[str, Any]]:
    issues = [
        issue
        for issue in state["issues"]["issues"]
        if issue["status"] in OPEN_ISSUE_STATUSES
    ]
    priority = {severity: index for index, severity in enumerate(SEVERITIES)}
    return sorted(
        issues,
        key=lambda issue: (
            priority[issue["severity"]],
            not issue["on_critical_path"],
            issue["status"] != "blocked",
            issue["created_at"],
            issue["id"],
        ),
    )


def _issue_bullets(issues: list[dict[str, Any]], empty: str) -> str:
    return _bullets(
        [
            f"{item['id']} [{item['severity']}/{item['status']}]: {item['title']}"
            for item in issues
        ],
        empty,
    )


def _active_evidence(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in state["evidence"]["evidence"] if item["status"] == "active"
    ]


def _has_observed_play_evidence(evidence: list[dict[str, Any]]) -> bool:
    return any(
        item["classification"] == "observed"
        and item["source_type"] in {"runtime", "human-playtest"}
        for item in evidence
    )


def _evidence_for_issue(
    issue: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        evidence_by_id[reference]
        for reference in issue["evidence_references"]
        if reference in evidence_by_id
        and evidence_by_id[reference]["status"] == "active"
    ]


def _evidence_count_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "None recorded"
    counts = {
        classification: sum(item["classification"] == classification for item in items)
        for classification in (
            "observed",
            "user-reported",
            "inferred",
            "unknown",
        )
    }
    return "; ".join(
        f"{counts[classification]} {classification}" for classification in counts
    )


def render_current_state(state: dict[str, Any]) -> str:
    project = state["project"]
    evidence = _active_evidence(state)
    blockers = [
        f"{issue['id']}: {issue['title']}"
        for issue in _open_issues(state)
        if issue["severity"] in {"blocker", "critical"} or issue["status"] == "blocked"
    ]
    evidence_lines = [
        f"{item['id']} [{item['classification']}] {item['claim']}" for item in evidence
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
    evidence = _active_evidence(state)
    decisions = [
        decision
        for decision in state["decisions"]["decisions"]
        if decision["status"] == "pending"
    ]
    cp_items = state["critical_path"]["items"]
    active_issues = _open_issues(state)
    blockers = [
        issue
        for issue in active_issues
        if issue["severity"] == "blocker" or issue["status"] == "blocked"
    ]
    learned = [f"[{item['classification']}] {item['claim']}" for item in evidence]
    evidence_lines = [
        f"{item['id']} — {item['source'] or item['source_type']} "
        f"({item['confidence']} confidence)"
        for item in evidence
    ]
    evidence_groups = {
        classification: [
            f"{item['id']}: {item['claim']}"
            for item in evidence
            if item["classification"] == classification
        ]
        for classification in (
            "observed",
            "user-reported",
            "inferred",
            "unknown",
        )
    }
    active_evidence_ids = {item["id"] for item in evidence}
    unsupported_issues = [
        f"{item['id']}: {item['title']}"
        for item in active_issues
        if not any(
            reference in active_evidence_ids
            for reference in item["evidence_references"]
        )
    ]
    disclaimer = (
        ""
        if _has_observed_play_evidence(evidence)
        else f"\n\n{SIMULATED_REVIEW_DISCLAIMER}"
    )
    decision_lines = [
        f"{item['id']}: {item['question']} — recommendation: {item['recommended_option']}"
        for item in decisions
    ]
    decision_lines.extend(
        f"{item['id']}: {item['title']} — issue requires a user decision"
        for item in active_issues
        if item["user_decision_required"]
    )
    critical_path_lines = [
        f"{index}. {item['id']}: {item['title']} — {item['why_critical']}"
        for index, item in enumerate(cp_items, 1)
    ]
    next_workflow = (
        "/issue-map" if active_issues else project["recommended_next_playbook"]
    )
    recommendation = (
        "Review and prioritize the active issue map."
        if active_issues
        else milestone["recommendation"]
    )
    return f"""{WARNING}
# Direction Report

## Current State

- Current phase: {project["current_phase"]}
- Current milestone: {project["current_milestone"]}
- Build status: {project["current_build_status"]}
- Review mode: {project["review_mode"]}
- Prototype hypothesis: {project["prototype_hypothesis"] or "Not defined"}
- Milestone verdict: {milestone["verdict"]}

## Current Blockers

{_issue_bullets(blockers, "No active blocker issue recorded.")}

## What We Learned

{_bullets(learned, "No evidence-backed learning has been recorded yet.")}

## Evidence

{_bullets(evidence_lines, "No evidence recorded.")}

## Evidence Summary

### Observed Findings

{_bullets(evidence_groups["observed"], "No active observed evidence.")}

### User-Reported Findings

{_bullets(evidence_groups["user-reported"], "No active user-reported evidence.")}

### Inferred Risks

{_bullets(evidence_groups["inferred"], "No active inferred evidence.")}

### Important Unknowns

{_bullets(evidence_groups["unknown"], "No active unknown evidence.")}

### Issues Lacking Evidence

{_bullets(unsupported_issues, "No active issue lacks evidence.")}{disclaimer}

## Open Decisions

{_bullets(decision_lines, "No pending decisions recorded.")}

## Critical Path

{_bullets(critical_path_lines, "No valid critical-path items recorded.")}

## Recommended Next Step

{recommendation}

## Do Not Work On Yet

{_bullets(state["critical_path"]["non_critical_work"])}

## Next Command

`{next_workflow}`
"""


def render_open_issues(state: dict[str, Any]) -> str:
    issues = _open_issues(state)
    evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
    blockers = [
        item
        for item in issues
        if item["severity"] == "blocker" or item["status"] == "blocked"
    ]
    critical = [item for item in issues if item["severity"] == "critical"]
    major = [item for item in issues if item["severity"] == "major"]
    user_decisions = [item for item in issues if item["user_decision_required"]]
    path_issues = [item for item in issues if item["on_critical_path"]]
    recently_resolved = sorted(
        (
            item
            for item in state["issues"]["issues"]
            if item["status"] in {"resolved", "accepted", "wont-fix"}
        ),
        key=lambda item: (item["updated_at"], item["id"]),
        reverse=True,
    )[:5]
    rows = []
    for item in issues:
        evidence = _evidence_count_text(_evidence_for_issue(item, evidence_by_id))
        rows.append(
            f"| {item['id']} | {item['severity']} | {item['status']} | "
            f"{item['title']} | {evidence} | {item['recommended_action']} |"
        )
    table = (
        "\n".join(rows)
        if rows
        else (
            "| — | — | — | No active issues recorded | UNKNOWN | Run the next workflow |"
        )
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

## Blockers

{_issue_bullets(blockers, "No active blockers.")}

## Critical Issues

{_issue_bullets(critical, "No active critical issues.")}

## Major Issues

{_issue_bullets(major, "No active major issues.")}

## User Decisions Required

{_issue_bullets(user_decisions, "No issue requires a user decision.")}

## Critical-Path Issues

{_issue_bullets(path_issues, "No issue is on the active critical path.")}

## Recently Resolved

{_issue_bullets(recently_resolved, "No recently resolved issues.")}
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
    support_labels = {
        "pass": "verified",
        "partial": "partially-supported",
        "fail": "contradicted",
        "unknown": "unsupported",
    }
    rows = [
        f"| {item['criterion']} | {support_labels[item['result']]} | "
        f"{', '.join(item['evidence_references']) or 'None'} | {item['notes']} |"
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
    evidence = "\n".join(
        f"- {classification.replace('-', ' ').title()}: {count}"
        for classification, count in summary.active_evidence_by_classification.items()
    )
    return (
        f"Current phase: {summary.phase}\n"
        f"Current milestone: {summary.milestone}\n"
        f"Build status: {summary.build_status}\n"
        f"Open issues: {issue_counts}\n"
        "Evidence:\n"
        f"{evidence}\n"
        "Critical issues without evidence: "
        f"{summary.critical_issues_without_evidence}\n"
        "Pending user decisions:\n"
        f"{decisions}\n"
        "Critical-path items:\n"
        f"{path}\n"
        f"Recommended next playbook: {summary.recommended_next_playbook}"
    )
