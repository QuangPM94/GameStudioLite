"""Deterministic Markdown generation from canonical JSON state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .state import OPEN_ISSUE_STATUSES, SEVERITIES, build_status_summary, load_state

WARNING = "<!-- Generated file. Do not edit manually. -->"
SIMULATED_REVIEW_DISCLAIMER = (
    "This is a simulated player-experience review based on available artifacts.\n"
    "It is not a substitute for an observed human playtest."
)


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _decision_support(
    decision: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    from .decisions import recommendation_support

    return recommendation_support(decision, evidence_by_id)


def _pending_decisions(state: dict[str, Any]) -> list[dict[str, Any]]:
    urgency = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        (
            item
            for item in state["decisions"]["decisions"]
            if item["status"] in {"open", "ready", "blocked", "deferred"}
        ),
        key=lambda item: (
            urgency[item["urgency"]],
            item["decision_required_by"] or "9999-12-31",
            item["milestone"] != state["project"]["current_milestone"],
            item["created_at"],
            item["id"],
        ),
    )


def _path_freshness(state: dict[str, Any]) -> tuple[str, list[str]]:
    critical_path = state["critical_path"]
    if not critical_path.get("calculation_snapshot"):
        if critical_path["items"]:
            return "Stale", ["The path predates freshness snapshots."]
        return "Absent", ["No calculated milestone critical path is available."]
    reasons: list[str] = (
        list(critical_path["freshness"]["reasons"])
        if critical_path["freshness"]["status"] == "stale"
        else []
    )
    if (
        critical_path["current_milestone"] != state["project"]["current_milestone"]
        and not critical_path["milestone_override"]
    ):
        reasons.append("The project milestone changed.")
    snapshot = critical_path["calculation_snapshot"]
    criteria = [
        {
            "id": item["id"],
            "result": item["result"],
            "required": item["required"],
            "evidence_references": item["evidence_references"],
            "related_issues": item["related_issues"],
            "related_decisions": item["related_decisions"],
        }
        for item in state["milestone"]["criteria_results"]
    ]
    if snapshot["criteria_fingerprint"] != _stable_digest(criteria):
        reasons.append("Milestone criterion state changed.")
    controls = {
        "pinned_sources": critical_path["pinned_sources"],
        "excluded_sources": critical_path["excluded_sources"],
    }
    if snapshot["manual_controls_fingerprint"] != _stable_digest(controls):
        reasons.append("Manual inclusion or exclusion controls changed.")
    evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
    evidence_fingerprint = _stable_digest(
        {
            reference: evidence_by_id.get(reference)
            for reference in snapshot.get("evidence_sources", [])
        }
    )
    if snapshot["evidence_fingerprint"] != evidence_fingerprint:
        reasons.append("Evidence support changed materially.")
    issue_by_id = {item["id"]: item for item in state["issues"]["issues"]}
    decision_by_id = {item["id"]: item for item in state["decisions"]["decisions"]}
    criteria_by_id = {
        item["id"]: item for item in state["milestone"]["criteria_results"]
    }
    active_sources = {item["source_key"] for item in critical_path["items"]}
    for item in critical_path["items"]:
        source_id = item["source_id"]
        if item["type"] == "issue":
            source = issue_by_id.get(source_id)
            if source is None:
                reasons.append(f"{source_id} is missing.")
            elif source["status"] != item["source_status"]:
                reasons.append(f"{source_id} status changed.")
            elif (
                source["evidence_type"].casefold().replace("_", "-")
                != item["evidence_state"]
            ):
                reasons.append(f"{source_id} evidence support changed.")
        elif item["type"] == "decision":
            source = decision_by_id.get(source_id)
            if source is None:
                reasons.append(f"{source_id} is missing.")
            elif source["status"] != item["source_status"]:
                reasons.append(f"{source_id} status changed.")
        elif source_id and source_id.startswith("MC-"):
            source = criteria_by_id.get(source_id)
            if source is None:
                reasons.append(f"{source_id} is missing.")
            elif source["result"] != item["source_status"]:
                reasons.append(f"{source_id} result changed.")
    for issue in state["issues"]["issues"]:
        if (
            issue["status"] in OPEN_ISSUE_STATUSES
            and (issue["severity"] == "blocker" or issue["status"] == "blocked")
            and f"issue:{issue['id']}" not in active_sources
            and f"issue:{issue['id']}" not in critical_path["excluded_sources"]
        ):
            reasons.append(f"{issue['id']} is a new hard milestone blocker.")
    for decision in state["decisions"]["decisions"]:
        if (
            decision["status"] in {"open", "ready", "blocked"}
            and decision["urgency"] == "blocking"
            and f"decision:{decision['id']}" not in active_sources
            and f"decision:{decision['id']}" not in critical_path["excluded_sources"]
        ):
            reasons.append(f"{decision['id']} is a new blocking decision.")
    return ("Stale", list(dict.fromkeys(reasons))) if reasons else ("Current", [])


def _recommended_path_item(state: dict[str, Any]) -> dict[str, Any] | None:
    recommended = state["critical_path"]["recommended_next_id"]
    return next(
        (item for item in state["critical_path"]["items"] if item["id"] == recommended),
        None,
    )


def _path_item_label(item: dict[str, Any] | None, empty: str = "None") -> str:
    return f"{item['id']} — {item['title']}" if item else empty


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
    decisions = _pending_decisions(state)
    decision_counts = {
        "Blocking": sum(item["urgency"] == "blocking" for item in decisions),
        "Ready": sum(item["status"] == "ready" for item in decisions),
        "Open": sum(item["status"] == "open" for item in decisions),
        "Deferred": sum(item["status"] == "deferred" for item in decisions),
    }
    decision_lines = [f"{label}: {count}" for label, count in decision_counts.items()]
    path = state["critical_path"]["items"]
    freshness, _ = _path_freshness(state)
    recommended = _recommended_path_item(state)
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

## Decisions

{_bullets(decision_lines)}

## Milestone Critical Path

- Active items: {len(path)}
- Ready items: {sum(item["status"] in {"ready", "in-progress"} for item in path)}
- Blocked items: {sum(item["status"] == "blocked" for item in path)}
- Path freshness: {freshness}
- Recommended next action: {_path_item_label(recommended)}

## Recommended Next Action

{_path_item_label(recommended, f"Run `{project['recommended_next_playbook']}`.")}
"""


def render_direction_report(state: dict[str, Any]) -> str:
    project = state["project"]
    cp_items = state["critical_path"]["items"]
    critical_path_lines = [
        f"{index}. {item['id']} — {item['title']} [{item['status']}]"
        for index, item in enumerate(cp_items, 1)
    ]
    recommended = _recommended_path_item(state)
    blocking_path_item = next(
        (
            item
            for item in cp_items
            if item["type"] == "decision" and item["status"] != "completed"
        ),
        None,
    )
    pending_blocking_decision = next(
        (
            item
            for item in _pending_decisions(state)
            if item["urgency"] in {"blocking", "high"}
        ),
        None,
    )
    if blocking_path_item:
        blocking_decision_text = _path_item_label(blocking_path_item)
    elif pending_blocking_decision:
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        support = _decision_support(pending_blocking_decision, evidence_by_id)["level"]
        blocking_decision_text = (
            f"{pending_blocking_decision['id']} "
            f"[{pending_blocking_decision['urgency']}/"
            f"{pending_blocking_decision['status']}] "
            f"{pending_blocking_decision['question']} — evidence: {support}"
        )
    else:
        blocking_decision_text = "None."
    verification_gap = next(
        (item for item in cp_items if item["type"] == "verification"), None
    )
    active_evidence_ids = {
        item["id"]
        for item in state["evidence"]["evidence"]
        if item["status"] == "active"
    }
    unsupported_issue = next(
        (
            item
            for item in _open_issues(state)
            if item["severity"] in {"blocker", "critical"}
            and not any(
                reference in active_evidence_ids
                for reference in item["evidence_references"]
            )
        ),
        None,
    )
    if verification_gap:
        evidence_gap_text = _path_item_label(verification_gap)
    elif unsupported_issue:
        evidence_gap_text = (
            f"{unsupported_issue['id']}: {unsupported_issue['title']} "
            "lacks active evidence."
        )
    else:
        evidence_gap_text = "None on the active path."
    evidence = _active_evidence(state)
    disclaimer = (
        ""
        if _has_observed_play_evidence(evidence)
        else f"\n\n{SIMULATED_REVIEW_DISCLAIMER}"
    )
    return f"""{WARNING}
# Direction Report

Current phase: {project["current_phase"]}

Current milestone: {project["current_milestone"]}

## Critical Path Summary

{_bullets(critical_path_lines, "No valid critical-path items recorded.")}

## Recommended Next Item

{_path_item_label(recommended, "None identified.")}

## Blocking User Decision

{blocking_decision_text}

## Evidence Gap

{evidence_gap_text}{disclaimer}

## Do Not Work On Yet

{_bullets(state["critical_path"]["non_critical_work"])}
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
    off_path_issues = [item for item in issues if not item["on_critical_path"]]
    recently_resolved = sorted(
        (
            item
            for item in state["issues"]["issues"]
            if item["status"] in {"resolved", "accepted", "wont-fix"}
        ),
        key=lambda item: (item["updated_at"], item["id"]),
        reverse=True,
    )[:5]
    decisions_by_issue: dict[str, list[dict[str, Any]]] = {}
    for decision in state["decisions"]["decisions"]:
        for issue_id in decision["affected_issues"]:
            decisions_by_issue.setdefault(issue_id, []).append(decision)
    rows = []
    for item in issues:
        evidence = _evidence_count_text(_evidence_for_issue(item, evidence_by_id))
        rows.append(
            f"| {item['id']} | {item['severity']} | {item['status']} | "
            f"{item['title']} | {evidence} | {item['recommended_action']} |"
        )
        related = sorted(
            decisions_by_issue.get(item["id"], []),
            key=lambda decision: decision["id"],
        )
        if related:
            rows.append(
                "|  |  |  | Related decisions | "
                + "; ".join(
                    f"{decision['id']} — {decision['status'].title()}"
                    for decision in related
                )
                + " |  |"
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

## On Milestone Critical Path

{_issue_bullets(path_issues, "No issue is on the active critical path.")}

## Not On Milestone Critical Path

These issues may still matter, but they are not currently gating this milestone.

{_issue_bullets(off_path_issues, "No active off-path issues.")}

## Recently Resolved

{_issue_bullets(recently_resolved, "No recently resolved issues.")}
"""


def render_critical_path(state: dict[str, Any]) -> str:
    critical_path = state["critical_path"]
    freshness, freshness_reasons = _path_freshness(state)
    recommended = _recommended_path_item(state)
    sections = []
    for index, item in enumerate(critical_path["items"], 1):
        dependencies = ", ".join(item["dependencies"]) or "None"
        sections.append(
            f"### {index}. {item['id']} — {item['title']}\n\n"
            f"- Type: {item['type']}\n"
            f"- Source: {item['source_id'] or item['source_key']}\n"
            f"- Status: {item['status']}\n"
            f"- Priority tier: {item['priority_tier']}\n"
            f"- Dependencies: {dependencies}\n"
            f"- Why critical: {item['reason']}\n"
            f"- Milestone impact: {item['milestone_impact']}\n"
            f"- Completion condition: {item['completion_condition']}"
        )
    body = "\n\n".join(sections) or "No valid critical-path items recorded."
    blocked = [
        f"{item['id']} — {item['title']}"
        for item in critical_path["items"]
        if item["status"] == "blocked"
    ]
    manual_lines = [
        *(f"Pinned: {item}" for item in critical_path["pinned_sources"]),
        *(
            f"Excluded: {item} — {critical_path['exclusion_reasons'][item]}"
            for item in critical_path["excluded_sources"]
        ),
    ]
    history = [
        f"{item['id']} [{item['status']}] — {item['title']}"
        for item in critical_path["history"]
    ]
    return f"""{WARNING}
# Milestone Critical Path

## Current Milestone

{critical_path["current_milestone"]}

## Milestone Success Criteria

{_bullets(critical_path["milestone_success_criteria"])}

## Active Critical Path

{body}

## Recommended Next Action

{_path_item_label(recommended, "No actionable item identified.")}

## Blocked Items

{_bullets(blocked, "No blocked active items.")}

## Manual Inclusions and Exclusions

{_bullets(manual_lines, "No manual controls.")}

## Non-Critical Work

{_bullets(critical_path["non_critical_work"])}

## Completed Path History

{_bullets(history, "No completed or removed path history.")}

## Freshness

Status: {freshness}

{_bullets(freshness_reasons, "No stale-path reasons.")}
"""


def render_milestone_review(state: dict[str, Any]) -> str:
    milestone = state["milestone"]
    evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
    relevant_decisions = [
        item
        for item in state["decisions"]["decisions"]
        if item["milestone"] == milestone["milestone"]
        and (
            item["urgency"] == "blocking"
            or item["status"] == "resolved"
            or _decision_support(item, evidence_by_id)["level"]
            in {"weak", "unsupported", "conflicted"}
            or item["revisit_condition"]
        )
    ]
    decision_lines = [
        f"{item['id']} [{item['status']}/{item['urgency']}]: "
        f"{item['question']} — evidence "
        f"{_decision_support(item, evidence_by_id)['level']}"
        + (
            f"; revisit: {item['revisit_condition']}"
            if item["revisit_condition"]
            else ""
        )
        for item in relevant_decisions
    ]
    support_labels = {
        "pass": "verified",
        "partial": "partially-supported",
        "fail": "contradicted",
        "unknown": "unsupported",
    }
    rows = [
        f"| {item['id']} | {item['criterion']} | "
        f"{'yes' if item['required'] else 'no'} | "
        f"{support_labels[item['result']]} | "
        f"{', '.join(item['evidence_references']) or 'None'} | {item['notes']} |"
        for item in milestone["criteria_results"]
    ]
    path = state["critical_path"]["items"]
    freshness, _ = _path_freshness(state)
    required_decisions = [
        item
        for item in path
        if item["type"] == "decision"
        and item["status"] in {"ready", "blocked", "in-progress", "pending"}
    ]
    verification = [item for item in path if item["type"] == "verification"]
    return f"""{WARNING}
# Milestone Review

## Milestone

{milestone["milestone"]}

## Success Criteria and Results

| ID | Criterion | Required | Result | Evidence | Notes |
|---|---|---|---|---|---|
{chr(10).join(rows) if rows else "| — | — | — | unknown | None | No criteria recorded |"}

## Supporting Evidence

{_bullets(milestone["supporting_evidence"], "No supporting evidence recorded.")}

## Blocking Issues

{_bullets(milestone["blocking_issues"], "No blocking issues recorded.")}

## Relevant Decisions

{_bullets(decision_lines, "No milestone-relevant decisions recorded.")}

## Critical Path Readiness

- Active blockers remain: {"yes" if path else "no"}
- Required decisions remain: {"yes" if required_decisions else "no"}
- Verification is incomplete: {"yes" if verification else "no"}
- Path freshness: {freshness}
- Path empty because milestone is complete: {"yes" if not path and all(item["result"] == "pass" for item in milestone["criteria_results"]) else "no"}

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
    decisions = _bullets(summary.pending_decisions, "No pending decisions.")
    path_items = state["critical_path"]["items"]
    freshness, _ = _path_freshness(state)
    recommended = _recommended_path_item(state)
    evidence = "\n".join(
        f"- {classification.replace('-', ' ').title()}: {count}"
        for classification, count in summary.active_evidence_by_classification.items()
    )
    decision_counts = "\n".join(
        f"- {urgency.title()}: {count}"
        for urgency, count in summary.pending_decisions_by_urgency.items()
    )
    stale_instruction = "Run:\nstudio path calculate\n" if freshness == "Stale" else ""
    return (
        f"Current phase: {summary.phase}\n"
        f"Current milestone: {summary.milestone}\n"
        f"Build status: {summary.build_status}\n"
        f"Open issues: {issue_counts}\n"
        "Evidence:\n"
        f"{evidence}\n"
        "Critical issues without evidence: "
        f"{summary.critical_issues_without_evidence}\n"
        "Pending decisions:\n"
        f"{decision_counts}\n"
        "Next required decision:\n"
        f"{summary.next_required_decision or 'None'}\n"
        "Decision queue:\n"
        f"{decisions}\n"
        "Milestone critical path:\n"
        f"- Active: {len(path_items)}\n"
        f"- Ready: {sum(item['status'] in {'ready', 'in-progress'} for item in path_items)}\n"
        f"- Blocked: {sum(item['status'] == 'blocked' for item in path_items)}\n"
        f"- Freshness: {freshness}\n"
        "Recommended next action:\n"
        f"{_path_item_label(recommended)}\n"
        f"{stale_instruction}"
        f"Recommended next playbook: {summary.recommended_next_playbook}"
    )
