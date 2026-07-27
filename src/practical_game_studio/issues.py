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

from .evidence import derive_issue_evidence_type
from .models import MutationResult
from .reporting import render_report_contents
from .state import OPEN_ISSUE_STATUSES, SEVERITIES, StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

ISSUE_ID_PATTERN = re.compile(r"^ISS-(\d{3,})$")
CP_ID_PATTERN = re.compile(r"^CP-(\d{4,})$")
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
    return f"CP-{highest + 1:04d}"


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
                if len(critical_path["items"]) >= critical_path["configured_max_items"]:
                    raise IssueInputError(
                        "cannot add issue to the critical path: it is already at "
                        "its configured maximum"
                    )
                source_key = f"issue:{issue['id']}"
                if source_key not in critical_path["pinned_sources"]:
                    critical_path["pinned_sources"].append(source_key)
                critical_path["items"].append(
                    self._critical_path_item(issue, critical_path)
                )
                self._mark_path_stale(
                    critical_path,
                    f"{issue['id']} was manually included; recalculate the path.",
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
            evidence_changed = self._apply_references(state, issue, patch, warnings)
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
                if evidence_changed:
                    transaction.set_evidence(state["evidence"])
            elif evidence_changed:
                transaction.set_evidence(state["evidence"])
                transaction.set_issues(state["issues"])
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
    ) -> bool:
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

        evidence_changed = False
        if patch.add_evidence or patch.remove_evidence:
            current_evidence = list(issue["evidence_references"])
            for reference in _deduplicate(patch.add_evidence):
                if reference not in evidence_by_id:
                    raise IssueInputError(f"evidence {reference} does not exist")
                if reference not in current_evidence:
                    current_evidence.append(reference)
                else:
                    warnings.append(f"{reference} is already attached")
                related = evidence_by_id[reference]["related_issues"]
                if issue["id"] not in related:
                    related.append(issue["id"])
                    evidence_changed = True
            for reference in _deduplicate(patch.remove_evidence):
                if reference in current_evidence:
                    current_evidence.remove(reference)
                else:
                    warnings.append(f"{reference} is not attached")
                related = evidence_by_id.get(reference, {}).get("related_issues", [])
                if issue["id"] in related:
                    related.remove(issue["id"])
                    evidence_changed = True
            issue["evidence_references"] = current_evidence
            issue["evidence_type"] = derive_issue_evidence_type(
                current_evidence, evidence_by_id
            )
        return evidence_changed

    def _apply_critical_path(
        self,
        state: dict[str, StateObject],
        issue: StateObject,
        requested: bool | None,
    ) -> bool:
        if requested is None:
            return False
        critical_path = state["critical_path"]
        items = critical_path["items"]
        source_key = f"issue:{issue['id']}"
        matches = [item for item in items if item["source_key"] == source_key]
        if requested:
            if issue["status"] in INACTIVE_STATUSES:
                raise IssueInputError(
                    f"{issue['id']} is {issue['status']} and cannot join the active "
                    "critical path"
                )
            issue["on_critical_path"] = True
            if source_key not in critical_path["pinned_sources"]:
                critical_path["pinned_sources"].append(source_key)
            if matches:
                return False
            if len(items) >= critical_path["configured_max_items"]:
                raise IssueInputError(
                    "cannot add issue to the critical path: it is already at "
                    "its configured maximum"
                )
            items.append(self._critical_path_item(issue, critical_path))
            self._mark_path_stale(
                critical_path,
                f"{issue['id']} was manually included; recalculate the path.",
            )
            return True
        issue["on_critical_path"] = False
        if source_key in critical_path["pinned_sources"]:
            critical_path["pinned_sources"].remove(source_key)
        if not matches:
            return False
        removed = [item for item in items if item["source_key"] == source_key]
        state["critical_path"]["items"] = [
            item for item in items if item["source_key"] != source_key
        ]
        removed_ids = {item["id"] for item in removed}
        for downstream in state["critical_path"]["items"]:
            dependencies = [
                dependency
                for dependency in downstream["dependencies"]
                if dependency not in removed_ids
            ]
            if dependencies != downstream["dependencies"]:
                downstream["dependencies"] = dependencies
                if (
                    not dependencies
                    and downstream["status"] == "blocked"
                    and downstream["source_status"] != "blocked"
                ):
                    downstream["status"] = "ready"
        timestamp = _timestamp(self.clock)
        for item in removed:
            item["status"] = (
                "completed"
                if issue["status"] in {"resolved", "accepted"}
                else "removed"
            )
            item["source_status"] = issue["status"]
            item["updated_at"] = timestamp
            critical_path["history"] = [
                history
                for history in critical_path["history"]
                if history["source_key"] != source_key
            ]
            critical_path["history"].append(item)
        if critical_path["recommended_next_id"] in {item["id"] for item in removed}:
            critical_path["recommended_next_id"] = None
        self._mark_path_stale(
            critical_path,
            f"{issue['id']} was manually excluded from the active path; recalculate.",
        )
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

    def _synchronize_path_item(
        self, state: dict[str, StateObject], issue: StateObject
    ) -> bool:
        """Keep issue-backed path display fields aligned without reordering."""

        changed = False
        critical_path = state["critical_path"]
        source_key = f"issue:{issue['id']}"
        if issue["status"] in INACTIVE_STATUSES:
            matching = [
                item
                for item in critical_path["items"]
                if item["source_key"] == source_key
            ]
            if not matching:
                return False
            issue["on_critical_path"] = False
            critical_path["items"] = [
                item
                for item in critical_path["items"]
                if item["source_key"] != source_key
            ]
            removed_ids = {item["id"] for item in matching}
            for downstream in critical_path["items"]:
                dependencies = [
                    dependency
                    for dependency in downstream["dependencies"]
                    if dependency not in removed_ids
                ]
                if dependencies != downstream["dependencies"]:
                    downstream["dependencies"] = dependencies
                    if (
                        not dependencies
                        and downstream["status"] == "blocked"
                        and downstream["source_status"] != "blocked"
                    ):
                        downstream["status"] = "ready"
            timestamp = _timestamp(self.clock)
            for item in matching:
                item["status"] = (
                    "completed"
                    if issue["status"] in {"resolved", "accepted"}
                    else "removed"
                )
                item["source_status"] = issue["status"]
                item["updated_at"] = timestamp
                critical_path["history"] = [
                    history
                    for history in critical_path["history"]
                    if history["source_key"] != source_key
                ]
                critical_path["history"].append(item)
            if source_key in critical_path["pinned_sources"]:
                critical_path["pinned_sources"].remove(source_key)
            if critical_path["recommended_next_id"] in {
                item["id"] for item in matching
            }:
                critical_path["recommended_next_id"] = None
            self._mark_path_stale(
                critical_path,
                f"{issue['id']} is now {issue['status']}; recalculate the path.",
            )
            return True

        for item in critical_path["items"]:
            if item["source_key"] != f"issue:{issue['id']}":
                continue
            expected = {
                "title": issue["title"],
                "description": issue["description"],
                "reason": (
                    issue["milestone_impact"]
                    or issue["player_impact"]
                    or issue["description"]
                ),
                "milestone_impact": (
                    issue["milestone_impact"]
                    or issue["player_impact"]
                    or issue["description"]
                ),
                "completion_condition": issue["recommended_action"],
                "recommended_action": issue["recommended_action"],
                "owner": issue["owner"],
                "source_status": issue["status"],
                "evidence_state": issue["evidence_type"].casefold().replace("_", "-"),
            }
            if any(item[field_name] != value for field_name, value in expected.items()):
                for field_name, value in expected.items():
                    item[field_name] = value
                changed = True
                item["updated_at"] = _timestamp(self.clock)
                self._mark_path_stale(
                    critical_path,
                    f"{issue['id']} materially changed; recalculate the path.",
                )
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
        self, issue: StateObject, critical_path: StateObject
    ) -> StateObject:
        why = (
            issue["milestone_impact"] or issue["player_impact"] or issue["description"]
        )
        timestamp = _timestamp(self.clock)
        all_items = [
            *critical_path["items"],
            *critical_path["history"],
        ]
        return {
            "id": _allocate_cp_id(all_items),
            "type": "issue",
            "source_id": issue["id"],
            "source_key": f"issue:{issue['id']}",
            "title": issue["title"],
            "description": issue["description"],
            "reason": why,
            "milestone_impact": why,
            "priority_tier": self._critical_path_tier(issue),
            "dependencies": [],
            "status": "blocked" if issue["status"] == "blocked" else "ready",
            "completion_condition": issue["recommended_action"],
            "recommended_action": issue["recommended_action"],
            "owner": issue["owner"],
            "evidence_required": list(issue["evidence_references"]),
            "pinned": True,
            "manual": False,
            "created_at": timestamp,
            "updated_at": timestamp,
            "source_status": issue["status"],
            "evidence_state": issue["evidence_type"].casefold().replace("_", "-"),
        }

    @staticmethod
    def _critical_path_tier(issue: StateObject) -> int:
        if issue["severity"] == "blocker" or issue["category"] == "build":
            return 1
        if issue["severity"] == "critical":
            return 2
        return 5

    @staticmethod
    def _mark_path_stale(critical_path: StateObject, reason: str) -> None:
        critical_path["freshness"] = {
            "status": "stale",
            "reasons": [reason],
        }

    def _issue_map_workflow(self) -> str:
        catalog = self.repository.root / ".studio" / "workflow-catalog.json"
        payload = json.loads(catalog.read_text(encoding="utf-8"))
        aliases = {item["alias"] for item in payload["workflows"]}
        if "/issue-map" in aliases:
            return "/issue-map"
        return self.repository.load_project()["recommended_next_playbook"]
