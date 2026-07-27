"""Canonical state repository, root discovery, and status projection."""

from __future__ import annotations

import copy
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
OPEN_ISSUE_STATUSES = {"open", "acknowledged", "in-progress", "blocked"}
ROOT_MARKERS = ("AGENTS.md", ".studio", "pyproject.toml")

StateObject = dict[str, Any]
CanonicalState = dict[str, StateObject]


class StateReadError(ValueError):
    """A canonical state file could not be read safely."""


def _is_project_root(path: Path) -> bool:
    return (
        (path / "AGENTS.md").is_file()
        and (path / ".studio").is_dir()
        and (path / "pyproject.toml").is_file()
    )


def find_project_root(
    start: Path | None = None, *, explicit: Path | str | None = None
) -> Path:
    """Resolve an explicit root or find the nearest parent with all PGS markers."""

    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_dir():
            raise FileNotFoundError(
                f"PGS root does not exist or is not a directory: {candidate}"
            )
        if not _is_project_root(candidate):
            markers = ", ".join(ROOT_MARKERS)
            raise FileNotFoundError(
                f"Not a Practical Game Studio root: {candidate}. "
                f"Expected all of: {markers}."
            )
        return candidate

    candidate = (start or Path.cwd()).expanduser().resolve()
    if not candidate.is_dir():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if _is_project_root(directory):
            return directory
    raise FileNotFoundError(
        "No Practical Game Studio project found. "
        "Run from a repository containing AGENTS.md, .studio/, and pyproject.toml, "
        "or pass --root PATH."
    )


def load_json(path: Path) -> Any:
    """Load UTF-8 JSON, preserving a useful filename in parse errors."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise StateReadError(
            f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise StateReadError(f"{path}: could not read state: {exc}") from exc


class StateRepository:
    """Read canonical state without caching or exposing mutable shared objects."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.state_dir = self.root / ".studio" / "state"

    def _load(self, name: str) -> StateObject:
        path = self.state_dir / STATE_FILES[name]
        value = load_json(path)
        if not isinstance(value, dict):
            raise StateReadError(f"{path}: expected a JSON object at the document root")
        return copy.deepcopy(value)

    def load_project(self) -> StateObject:
        return self._load("project")

    def load_issues(self) -> StateObject:
        return self._load("issues")

    def load_decisions(self) -> StateObject:
        return self._load("decisions")

    def load_critical_path(self) -> StateObject:
        return self._load("critical_path")

    def load_evidence(self) -> StateObject:
        return self._load("evidence")

    def load_milestone(self) -> StateObject:
        return self._load("milestone")

    def load_all(self) -> CanonicalState:
        return {
            "project": self.load_project(),
            "issues": self.load_issues(),
            "decisions": self.load_decisions(),
            "critical_path": self.load_critical_path(),
            "evidence": self.load_evidence(),
            "milestone": self.load_milestone(),
        }


def load_state(root: Path) -> CanonicalState:
    """Load every canonical state object."""

    return StateRepository(root).load_all()


def build_status_summary(state: dict[str, Any]) -> StatusSummary:
    """Project canonical state into the fields printed by ``studio status``."""

    counts = {severity: 0 for severity in SEVERITIES}
    for issue in state["issues"]["issues"]:
        if issue["status"] in OPEN_ISSUE_STATUSES:
            counts[issue["severity"]] += 1

    active_evidence = {
        item["id"]: item
        for item in state["evidence"]["evidence"]
        if item["status"] == "active"
    }
    evidence_counts = {
        classification: 0
        for classification in ("observed", "user-reported", "inferred", "unknown")
    }
    for item in active_evidence.values():
        evidence_counts[item["classification"]] += 1
    unsupported_critical = sum(
        issue["status"] in OPEN_ISSUE_STATUSES
        and issue["severity"] == "critical"
        and not any(
            reference in active_evidence for reference in issue["evidence_references"]
        )
        for issue in state["issues"]["issues"]
    )

    pending_records = [
        decision
        for decision in state["decisions"]["decisions"]
        if decision["status"] in {"open", "ready", "blocked", "deferred"}
    ]
    urgency_priority = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
    pending_records.sort(
        key=lambda item: (
            urgency_priority[item["urgency"]],
            item["decision_required_by"] or "9999-12-31",
            item["created_at"],
            item["id"],
        )
    )
    pending = [
        f"{decision['id']}: {decision['question']}" for decision in pending_records
    ]
    pending_by_urgency = {
        urgency: sum(item["urgency"] == urgency for item in pending_records)
        for urgency in ("blocking", "high")
    }
    next_required = (
        f"{pending_records[0]['id']} — {pending_records[0]['question']}"
        if pending_records
        else None
    )
    path_items = [
        f"{item['id']}: {item['title']}" for item in state["critical_path"]["items"]
    ]
    project = state["project"]
    return StatusSummary(
        phase=project["current_phase"],
        milestone=project["current_milestone"],
        build_status=project["current_build_status"],
        open_issues_by_severity=counts,
        active_evidence_by_classification=evidence_counts,
        critical_issues_without_evidence=unsupported_critical,
        pending_decisions=pending,
        pending_decisions_by_urgency=pending_by_urgency,
        next_required_decision=next_required,
        critical_path_items=path_items,
        recommended_next_playbook=project["recommended_next_playbook"],
    )
