"""Issue-domain operations backed by canonical PGS state."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MutationResult
from .reporting import render_report_contents
from .state import OPEN_ISSUE_STATUSES, SEVERITIES, StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

ISSUE_ID_PATTERN = re.compile(r"^ISS-(\d{3,})$")
CP_ID_PATTERN = re.compile(r"^CP-(\d{3,})$")
CATEGORIES = (
    "build",
    "mechanic",
    "clarity",
    "engagement",
    "pacing",
    "feedback",
    "friction",
    "emotion",
    "stability",
    "scope",
    "technical",
    "evidence",
    "other",
)
STATUSES = (
    "open",
    "acknowledged",
    "in-progress",
    "blocked",
    "resolved",
    "accepted",
    "wont-fix",
    "deferred",
)
TERMINAL_STATUSES = {"resolved", "accepted", "wont-fix"}
INACTIVE_STATUSES = TERMINAL_STATUSES | {"deferred"}
EFFORTS = ("tiny", "small", "medium", "large", "unknown")
OWNERS = (
    "producer",
    "game-designer",
    "technical-lead",
    "developer",
    "player-advocate",
    "user",
    "unassigned",
)
ALLOWED_TRANSITIONS = {
    "open": {
        "acknowledged",
        "in-progress",
        "blocked",
        "resolved",
        "accepted",
        "wont-fix",
        "deferred",
    },
    "acknowledged": {
        "open",
        "in-progress",
        "blocked",
        "resolved",
        "accepted",
        "wont-fix",
        "deferred",
    },
    "in-progress": {
        "open",
        "blocked",
        "resolved",
        "accepted",
        "wont-fix",
        "deferred",
    },
    "blocked": {
        "open",
        "in-progress",
        "resolved",
        "accepted",
        "wont-fix",
        "deferred",
    },
    "resolved": {"open"},
    "accepted": {"open"},
    "wont-fix": {"open"},
    "deferred": {"open"},
}

Clock = Callable[[], datetime]


class IssueError(ValueError):
    """Base class for actionable issue-domain errors."""


class IssueInputError(IssueError):
    """Issue input is missing or invalid."""


class IssueNotFoundError(IssueError):
    """The requested issue does not exist."""


@dataclass(frozen=True, slots=True)
class IssueCreateRequest:
    title: str
    severity: str
    description: str | None = None
    category: str | None = None
    player_impact: str | None = None
    milestone_impact: str | None = None
    recommended_action: str | None = None
    effort: str | None = None
    owner: str | None = None
    user_decision_required: bool = False
    on_critical_path: bool = False


@dataclass(frozen=True, slots=True)
class IssuePatch:
    values: Mapping[str, Any] = field(default_factory=dict)
    add_dependencies: tuple[str, ...] = ()
    remove_dependencies: tuple[str, ...] = ()
    add_blocked_issues: tuple[str, ...] = ()
    remove_blocked_issues: tuple[str, ...] = ()
    add_evidence: tuple[str, ...] = ()
    remove_evidence: tuple[str, ...] = ()
    critical_path: bool | None = None

    @property
    def requested(self) -> bool:
        return bool(
            self.values
            or self.add_dependencies
            or self.remove_dependencies
            or self.add_blocked_issues
            or self.remove_blocked_issues
            or self.add_evidence
            or self.remove_evidence
            or self.critical_path is not None
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = False) -> str:
    normalized = value.strip() if value is not None else ""
    if required and not normalized:
        raise IssueInputError(f"{field_name} cannot be empty")
    return normalized


def _enum(value: str, allowed: Iterable[str], *, field_name: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in allowed:
        choices = ", ".join(allowed)
        raise IssueInputError(
            f"invalid {field_name} '{value}'; expected one of: {choices}"
        )
    return normalized


def _deduplicate(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip().upper()
        if not normalized:
            raise IssueInputError("reference values cannot be empty")
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _canonical_issue_id(value: str) -> str:
    normalized = value.strip().upper()
    if not ISSUE_ID_PATTERN.fullmatch(normalized):
        raise IssueInputError(
            f"invalid issue ID '{value}'; expected a value such as ISS-0001"
        )
    return normalized


def allocate_issue_id(issues: Iterable[Mapping[str, Any]]) -> str:
    """Allocate after the greatest historical numeric issue ID."""

    highest = 0
    for issue in issues:
        match = ISSUE_ID_PATTERN.fullmatch(str(issue.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"ISS-{highest + 1:04d}"


def _allocate_cp_id(items: Iterable[Mapping[str, Any]]) -> str:
    highest = 0
    for item in items:
        match = CP_ID_PATTERN.fullmatch(str(item.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"CP-{highest + 1:03d}"


def _sort_key(issue: Mapping[str, Any]) -> tuple[Any, ...]:
    severity = (
        SEVERITIES.index(issue["severity"])
        if issue["severity"] in SEVERITIES
        else len(SEVERITIES)
    )
    return (
        severity,
        not issue["on_critical_path"],
        issue["status"] != "blocked",
        issue["created_at"],
        issue["id"],
    )


def _find_issue(issues: list[StateObject], issue_id: str) -> StateObject:
    canonical = _canonical_issue_id(issue_id)
    for issue in issues:
        if issue["id"] == canonical:
            return issue
    raise IssueNotFoundError(
        f"issue {canonical} was not found; run 'studio issue list'"
    )


class IssueService:
    """Create, query, and update issue records without terminal concerns."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Clock = utc_now,
        report_renderer: ReportRenderer = render_report_contents,
    ) -> None:
        self.root = root.resolve()
        self.repository = StateRepository(self.root)
        self.clock = clock
        self.report_renderer = report_renderer

    def preview_issue(self, request: IssueCreateRequest) -> StateObject:
        state = self.repository.load_all()
        return self._build_issue(state, request, timestamp=_timestamp(self.clock))

    def create_issue(
        self, request: IssueCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="issue.add",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            issue = self._build_issue(state, request, timestamp=_timestamp(self.clock))
            issues = state["issues"]
            issues["issues"].append(issue)
            transaction.set_issues(issues)
            if issue["on_critical_path"]:
                critical_path = state["critical_path"]
                if len(critical_path["items"]) >= 7:
                    raise IssueInputError(
                        "cannot add issue to the critical path: it already has 7 items"
                    )
                critical_path["items"].append(
                    self._critical_path_item(issue, critical_path["items"])
                )
                transaction.set_critical_path(critical_path)
            return transaction.commit(
                changed_fields={"issue": {"old": None, "new": issue["id"]}},
                details={
                    "issue": copy.deepcopy(issue),
                    "recommended_next_workflow": self._issue_map_workflow(),
                },
            )

    def get_issue(self, issue_id: str) -> StateObject:
        issues = self.repository.load_issues()["issues"]
        return copy.deepcopy(_find_issue(issues, issue_id))

    def list_issues(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        critical_path: bool = False,
        user_decision_required: bool = False,
        include_all: bool = False,
    ) -> list[StateObject]:
        if status is not None:
            status = _enum(status, STATUSES, field_name="status")
        if severity is not None:
            severity = _enum(severity, SEVERITIES, field_name="severity")
        if category is not None:
            category = _enum(category, CATEGORIES, field_name="category")
        if owner is not None:
            owner = _enum(owner, OWNERS, field_name="owner")
        matches: list[StateObject] = []
        for issue in self.repository.load_issues()["issues"]:
            if not include_all and issue["status"] not in OPEN_ISSUE_STATUSES:
                continue
            if status is not None and issue["status"] != status:
                continue
            if severity is not None and issue["severity"] != severity:
                continue
            if category is not None and issue["category"] != category:
                continue
            if owner is not None and issue["owner"] != owner:
                continue
            if critical_path and not issue["on_critical_path"]:
                continue
            if user_decision_required and not issue["user_decision_required"]:
                continue
            matches.append(copy.deepcopy(issue))
        return sorted(matches, key=_sort_key)

    def update_issue(
        self,
        issue_id: str,
        patch: IssuePatch,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        if not patch.requested:
            raise IssueInputError("at least one issue update must be requested")
        canonical_id = _canonical_issue_id(issue_id)
        warnings: list[str] = []
        with StateTransaction(
            self.root,
            operation="issue.update",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            issue = _find_issue(state["issues"]["issues"], canonical_id)
            before = copy.deepcopy(issue)
            self._apply_values(issue, patch.values)
            self._apply_references(state, issue, patch, warnings)
            critical_path_changed = self._apply_critical_path(
                state, issue, patch.critical_path
            )
            self._validate_transition(before, issue, patch.critical_path)
            critical_path_changed = (
                self._synchronize_path_item(state, issue) or critical_path_changed
            )
            changed_fields = self._changes(before, issue)
            if changed_fields:
                issue["updated_at"] = _timestamp(self.clock)
                changed_fields["updated_at"] = {
                    "old": before["updated_at"],
                    "new": issue["updated_at"],
                }
                transaction.set_issues(state["issues"])
                if critical_path_changed:
                    transaction.set_critical_path(state["critical_path"])
            return transaction.commit(
                warnings=warnings,
                changed_fields=changed_fields,
                details={
                    "issue": copy.deepcopy(issue),
                    "recommended_next_workflow": self._issue_map_workflow(),
                    "no_op": not changed_fields,
                },
            )

    def _build_issue(
        self,
        state: dict[str, StateObject],
        request: IssueCreateRequest,
        *,
        timestamp: str,
    ) -> StateObject:
        title = _text(request.title, field_name="title", required=True)
        severity = _enum(request.severity, SEVERITIES, field_name="severity")
        description = _text(request.description, field_name="description")
        player_impact = _text(request.player_impact, field_name="player impact")
        milestone_impact = _text(
            request.milestone_impact, field_name="milestone impact"
        )
        if not any((description, player_impact, milestone_impact)):
            raise IssueInputError(
                "provide at least one of description, player impact, or "
                "milestone impact"
            )
        category = (
            _enum(request.category, CATEGORIES, field_name="category")
            if request.category
            else "other"
        )
        effort = (
            _enum(request.effort, EFFORTS, field_name="effort")
            if request.effort
            else "unknown"
        )
        owner = (
            _enum(request.owner, OWNERS, field_name="owner")
            if request.owner
            else "unassigned"
        )
        action = _text(request.recommended_action, field_name="recommended action")
        if not action:
            action = "Investigate and define the smallest useful response."
        return {
            "id": allocate_issue_id(state["issues"]["issues"]),
            "title": title,
            "description": description or "Not yet described.",
            "severity": severity,
            "category": category,
            "status": "open",
            "phase_discovered": state["project"]["current_phase"],
            "evidence_type": "UNKNOWN",
            "evidence_references": [],
            "player_impact": player_impact,
            "milestone_impact": milestone_impact,
            "recommended_action": action,
            "alternative_actions": [],
            "effort": effort,
            "dependencies": [],
            "issues_blocked": [],
            "on_critical_path": request.on_critical_path,
            "user_decision_required": request.user_decision_required,
            "owner": owner,
            "resolution": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _apply_values(self, issue: StateObject, values: Mapping[str, Any]) -> None:
        text_fields = {
            "title",
            "description",
            "player_impact",
            "milestone_impact",
            "recommended_action",
            "resolution",
        }
        enum_fields = {
            "severity": SEVERITIES,
            "category": CATEGORIES,
            "status": STATUSES,
            "effort": EFFORTS,
            "owner": OWNERS,
        }
        for field_name, value in values.items():
            if field_name in text_fields:
                if value is None and field_name == "resolution":
                    issue[field_name] = None
                else:
                    issue[field_name] = _text(
                        value,
                        field_name=field_name.replace("_", " "),
                        required=field_name
                        in {
                            "title",
                            "description",
                            "recommended_action",
                            "resolution",
                        },
                    )
            elif field_name in enum_fields:
                issue[field_name] = _enum(
                    value, enum_fields[field_name], field_name=field_name
                )
            elif field_name == "phase_discovered":
                normalized = value.strip().casefold()
                catalog = json.loads(
                    (self.root / ".studio" / "workflow-catalog.json").read_text(
                        encoding="utf-8"
                    )
                )
                phases = {item["id"] for item in catalog["phases"]}
                if normalized not in phases:
                    raise IssueInputError(
                        f"invalid phase discovered '{value}'; expected one of: "
                        + ", ".join(sorted(phases))
                    )
                issue[field_name] = normalized
            elif field_name in {
                "user_decision_required",
            }:
                issue[field_name] = bool(value)
            else:
                raise IssueInputError(f"unsupported issue field '{field_name}'")

    def _apply_references(
        self,
        state: dict[str, StateObject],
        issue: StateObject,
        patch: IssuePatch,
        warnings: list[str],
    ) -> None:
        issue_ids = {item["id"] for item in state["issues"]["issues"]}
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        operations = (
            ("dependencies", patch.add_dependencies, patch.remove_dependencies),
            (
                "issues_blocked",
                patch.add_blocked_issues,
                patch.remove_blocked_issues,
            ),
        )
        for field_name, additions, removals in operations:
            current = list(issue[field_name])
            for reference in _deduplicate(additions):
                _canonical_issue_id(reference)
                if reference == issue["id"]:
                    relation = (
                        "depend on itself"
                        if field_name == "dependencies"
                        else "block itself"
                    )
                    raise IssueInputError(f"{issue['id']} cannot {relation}")
                if reference not in issue_ids:
                    raise IssueInputError(
                        f"referenced issue {reference} does not exist"
                    )
                if reference not in current:
                    current.append(reference)
                else:
                    warnings.append(
                        f"{reference} is already in {field_name.replace('_', ' ')}"
                    )
            for reference in _deduplicate(removals):
                if reference in current:
                    current.remove(reference)
                else:
                    warnings.append(
                        f"{reference} is not in {field_name.replace('_', ' ')}"
                    )
            issue[field_name] = current

        if patch.add_evidence or patch.remove_evidence:
            current_evidence = list(issue["evidence_references"])
            for reference in _deduplicate(patch.add_evidence):
                if reference not in evidence_by_id:
                    raise IssueInputError(f"evidence {reference} does not exist")
                if reference not in current_evidence:
                    current_evidence.append(reference)
                else:
                    warnings.append(f"{reference} is already attached")
            for reference in _deduplicate(patch.remove_evidence):
                if reference in current_evidence:
                    current_evidence.remove(reference)
                else:
                    warnings.append(f"{reference} is not attached")
            issue["evidence_references"] = current_evidence
            issue["evidence_type"] = self._evidence_type(
                current_evidence, evidence_by_id
            )

    def _apply_critical_path(
        self,
        state: dict[str, StateObject],
        issue: StateObject,
        requested: bool | None,
    ) -> bool:
        if requested is None:
            return False
        items = state["critical_path"]["items"]
        matches = [item for item in items if item["source_issue_id"] == issue["id"]]
        if requested:
            if issue["status"] in INACTIVE_STATUSES:
                raise IssueInputError(
                    f"{issue['id']} is {issue['status']} and cannot join the active "
                    "critical path"
                )
            issue["on_critical_path"] = True
            if matches:
                return False
            if len(items) >= 7:
                raise IssueInputError(
                    "cannot add issue to the critical path: it already has 7 items"
                )
            items.append(self._critical_path_item(issue, items))
            return True
        issue["on_critical_path"] = False
        if not matches:
            return False
        state["critical_path"]["items"] = [
            item for item in items if item["source_issue_id"] != issue["id"]
        ]
        return True

    def _validate_transition(
        self,
        before: StateObject,
        issue: StateObject,
        requested_path: bool | None,
    ) -> None:
        old_status = before["status"]
        new_status = issue["status"]
        if (
            new_status != old_status
            and new_status not in ALLOWED_TRANSITIONS[old_status]
        ):
            allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[old_status]))
            raise IssueInputError(
                f"cannot transition {before['id']} from {old_status} to {new_status}; "
                f"allowed next statuses: {allowed}"
            )
        if new_status in TERMINAL_STATUSES and not issue["resolution"]:
            raise IssueInputError(f"resolution is required when status is {new_status}")
        if (
            new_status in INACTIVE_STATUSES
            and before["on_critical_path"]
            and requested_path is not False
        ):
            raise IssueInputError(
                f"{before['id']} is on the active critical path; include "
                "--off-critical-path before making it inactive"
            )

    def _synchronize_path_item(
        self, state: dict[str, StateObject], issue: StateObject
    ) -> bool:
        """Keep issue-backed path display fields aligned without reordering."""

        changed = False
        for item in state["critical_path"]["items"]:
            if item["source_issue_id"] != issue["id"]:
                continue
            expected = {
                "title": issue["title"],
                "type": self._critical_path_type(issue),
                "blocked": issue["status"] == "blocked",
                "why_critical": (
                    issue["milestone_impact"]
                    or issue["player_impact"]
                    or issue["description"]
                ),
                "exit_condition": issue["recommended_action"],
            }
            for field_name, value in expected.items():
                if item[field_name] != value:
                    item[field_name] = value
                    changed = True
        return changed

    def _changes(
        self, before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return {
            key: {"old": copy.deepcopy(before[key]), "new": copy.deepcopy(value)}
            for key, value in after.items()
            if key != "updated_at" and before[key] != value
        }

    def _critical_path_item(
        self, issue: StateObject, items: list[StateObject]
    ) -> StateObject:
        why = (
            issue["milestone_impact"] or issue["player_impact"] or issue["description"]
        )
        return {
            "id": _allocate_cp_id(items),
            "title": issue["title"],
            "type": self._critical_path_type(issue),
            "source_issue_id": issue["id"],
            "source_decision_id": None,
            "dependencies": [],
            "blocked": issue["status"] == "blocked",
            "why_critical": why,
            "exit_condition": issue["recommended_action"],
        }

    @staticmethod
    def _critical_path_type(issue: StateObject) -> str:
        if issue["severity"] == "blocker" or issue["category"] == "build":
            return "build-blocker"
        if issue["severity"] == "critical":
            return "hypothesis-risk"
        return "player-impact"

    @staticmethod
    def _evidence_type(
        references: list[str], evidence_by_id: Mapping[str, Mapping[str, Any]]
    ) -> str:
        if not references:
            return "UNKNOWN"
        priority = {
            "OBSERVED": 0,
            "USER_REPORTED": 1,
            "INFERRED": 2,
            "UNKNOWN": 3,
        }
        return min(
            (evidence_by_id[reference]["type"] for reference in references),
            key=priority.__getitem__,
        )

    def _issue_map_workflow(self) -> str:
        catalog = self.repository.root / ".studio" / "workflow-catalog.json"
        payload = json.loads(catalog.read_text(encoding="utf-8"))
        aliases = {item["alias"] for item in payload["workflows"]}
        if "/issue-map" in aliases:
            return "/issue-map"
        return self.repository.load_project()["recommended_next_playbook"]
