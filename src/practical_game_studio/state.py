"""Canonical state loading and status projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import StatusSummary

STATE_FILES = {
    "project": "project.json",
    "issues": "issues.json",
    "decisions": "decisions.json",
    "critical_path": "critical-path.json",
    "evidence": "evidence.json",
    "milestone": "milestone.json",
}

SEVERITIES = ("blocker", "critical", "major", "minor", "later")
OPEN_ISSUE_STATUSES = {"open", "in-progress", "blocked"}


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest parent containing the PGS configuration."""

    candidate = (start or Path.cwd()).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / ".studio" / "config.json").is_file():
            return directory
    raise FileNotFoundError(
        "No Practical Game Studio project found. "
        "Run this command from a repository containing .studio/config.json."
    )


def load_json(path: Path) -> Any:
    """Load UTF-8 JSON, preserving a useful filename in parse errors."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def load_state(root: Path) -> dict[str, Any]:
    """Load every canonical state object."""

    state_dir = root / ".studio" / "state"
    return {
        name: load_json(state_dir / filename) for name, filename in STATE_FILES.items()
    }


def build_status_summary(state: dict[str, Any]) -> StatusSummary:
    """Project canonical state into the fields printed by ``studio status``."""

    counts = {severity: 0 for severity in SEVERITIES}
    for issue in state["issues"]["issues"]:
        if issue["status"] in OPEN_ISSUE_STATUSES:
            counts[issue["severity"]] += 1

    pending = [
        f"{decision['id']}: {decision['question']}"
        for decision in state["decisions"]["decisions"]
        if decision["status"] == "pending" and decision["decision_owner"] == "user"
    ]
    path_items = [
        f"{item['id']}: {item['title']}" for item in state["critical_path"]["items"]
    ]
    project = state["project"]
    return StatusSummary(
        phase=project["current_phase"],
        milestone=project["current_milestone"],
        build_status=project["current_build_status"],
        open_issues_by_severity=counts,
        pending_decisions=pending,
        critical_path_items=path_items,
        recommended_next_playbook=project["recommended_next_playbook"],
    )
