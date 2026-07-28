"""Typed, transactional authoring of explicit actionable dependencies."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MutationResult
from .reporting import render_report_contents
from .state import CanonicalState, StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

Clock = Callable[[], datetime]

DEPENDENCY_ID_PATTERN = re.compile(r"^DEP-(\d{4,})$")
ENDPOINT_PATTERN = re.compile(
    r"^(?:ISS-\d{3,}|DEC-\d{3,}|MC-\d{3,}|MANUAL:[a-z0-9][a-z0-9-]*)$"
)
SCOPES = {"current-milestone", "project"}
STATUSES = {"active", "inactive"}
ISSUE_SATISFACTION = {
    "open": (False, False),
    "acknowledged": (False, False),
    "in-progress": (False, False),
    "blocked": (False, False),
    "resolved": (True, True),
    "accepted": (True, True),
    "deferred": (True, False),
    "wont-fix": (True, False),
}
DECISION_SATISFACTION = {
    "open": (False, False),
    "ready": (False, False),
    "blocked": (False, False),
    "deferred": (True, False),
    "resolved": (True, True),
    "rejected": (True, False),
    "superseded": (True, False),
}


class DependencyError(ValueError):
    """Base class for dependency-domain errors."""


class DependencyInputError(DependencyError):
    """Dependency input or graph state is invalid."""


class DependencyNotFoundError(DependencyError):
    """A requested dependency does not exist."""


class DependencyCycleError(DependencyInputError):
    """An explicit or combined dependency graph contains a cycle."""


@dataclass(frozen=True, slots=True)
class EndpointSatisfaction:
    """Canonical dependency-prerequisite satisfaction verdict."""

    endpoint: str
    endpoint_type: str
    status: str
    terminal: bool
    satisfied: bool
    valid: bool
    reason: str

    @property
    def state(self) -> str:
        if not self.valid:
            return "invalid-or-missing"
        if self.satisfied:
            return "satisfied"
        if self.terminal:
            return "terminal-unsatisfied"
        return "active-unsatisfied"


@dataclass(frozen=True, slots=True)
class DependencyEndpoint:
    """A canonical actionable endpoint."""

    id: str
    type: str
    title: str
    state: str
    satisfied: bool
    terminal: bool
    valid: bool
    reason: str


@dataclass(frozen=True, slots=True)
class DependencyCreateRequest:
    prerequisite: str
    dependent: str
    reason: str
    scope: str = "current-milestone"


@dataclass(frozen=True, slots=True)
class DependencyPatch:
    prerequisite: str | None = None
    dependent: str | None = None
    reason: str | None = None
    scope: str | None = None
    status: str | None = None

    @property
    def requested(self) -> bool:
        return any(
            value is not None
            for value in (
                self.prerequisite,
                self.dependent,
                self.reason,
                self.scope,
                self.status,
            )
        )


@dataclass(frozen=True, slots=True)
class DependencyRecord:
    id: str
    prerequisite: str
    dependent: str
    relationship: str
    reason: str
    scope: str
    milestone: str | None
    status: str
    created_at: str
    updated_at: str
    deactivated_at: str | None
    deactivation_reason: str | None
    prerequisite_status: str = ""
    prerequisite_terminal: bool = False
    prerequisite_satisfied: bool = False
    prerequisite_valid: bool = True
    prerequisite_satisfaction_reason: str = ""
    prerequisite_state: str = "active-unsatisfied"
    upstream: tuple[str, ...] = field(default_factory=tuple)
    downstream: tuple[str, ...] = field(default_factory=tuple)
    on_critical_path: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise DependencyInputError(f"{field_name} cannot be empty")
    return normalized


def canonical_endpoint(value: str) -> str:
    normalized = value.strip()
    if normalized.upper().startswith("MANUAL:"):
        normalized = f"MANUAL:{normalized.split(':', 1)[1].casefold()}"
    else:
        normalized = normalized.upper()
    if not ENDPOINT_PATTERN.fullmatch(normalized):
        raise DependencyInputError(
            f"invalid dependency endpoint '{value}'; expected ISS-, DEC-, MC-, "
            "or MANUAL:slug"
        )
    return normalized


def endpoint_source_key(endpoint: str) -> str:
    canonical = canonical_endpoint(endpoint)
    if canonical.startswith("ISS-"):
        return f"issue:{canonical}"
    if canonical.startswith("DEC-"):
        return f"decision:{canonical}"
    if canonical.startswith("MC-"):
        return f"milestone:{canonical}"
    return f"manual:{canonical.split(':', 1)[1]}"


def source_key_endpoint(source_key: str) -> str | None:
    if source_key.startswith("issue:"):
        return source_key.split(":", 1)[1]
    if source_key.startswith("decision:"):
        return source_key.split(":", 1)[1]
    if source_key.startswith("milestone:"):
        return source_key.split(":", 1)[1]
    if source_key.startswith("manual:"):
        return f"MANUAL:{source_key.split(':', 1)[1]}"
    return None


def allocate_dependency_id(records: Iterable[Mapping[str, Any]]) -> str:
    highest = 0
    for record in records:
        match = DEPENDENCY_ID_PATTERN.fullmatch(str(record.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"DEP-{highest + 1:04d}"


def find_dependency(records: Iterable[StateObject], dependency_id: str) -> StateObject:
    canonical = dependency_id.strip().upper()
    if not DEPENDENCY_ID_PATTERN.fullmatch(canonical):
        raise DependencyInputError(
            f"invalid dependency ID '{dependency_id}'; expected DEP-0001"
        )
    for record in records:
        if record["id"] == canonical:
            return record
    raise DependencyNotFoundError(
        f"dependency {canonical} was not found; run 'studio dependency list'"
    )


def resolve_endpoint_satisfaction(
    state: CanonicalState, endpoint: str
) -> EndpointSatisfaction:
    """Resolve one endpoint using the only dependency-satisfaction rules."""

    canonical = canonical_endpoint(endpoint)
    if canonical.startswith("ISS-"):
        record = next(
            (item for item in state["issues"]["issues"] if item["id"] == canonical),
            None,
        )
        if record is None:
            return EndpointSatisfaction(
                canonical,
                "issue",
                "missing",
                False,
                False,
                False,
                f"{canonical} does not exist.",
            )
        status = record["status"]
        terminal, satisfied = ISSUE_SATISFACTION[status]
        return EndpointSatisfaction(
            canonical,
            "issue",
            status,
            terminal,
            satisfied,
            True,
            (
                f"{canonical} is {status} and satisfies the dependency."
                if satisfied
                else (
                    f"{canonical} is {status} and does not satisfy the dependency."
                    if terminal
                    else f"{canonical} is {status} and does not yet satisfy the dependency."
                )
            ),
        )
    if canonical.startswith("DEC-"):
        record = next(
            (
                item
                for item in state["decisions"]["decisions"]
                if item["id"] == canonical
            ),
            None,
        )
        if record is None:
            return EndpointSatisfaction(
                canonical,
                "decision",
                "missing",
                False,
                False,
                False,
                f"{canonical} does not exist.",
            )
        status = record["status"]
        terminal, satisfied = DECISION_SATISFACTION[status]
        return EndpointSatisfaction(
            canonical,
            "decision",
            status,
            terminal,
            satisfied,
            True,
            (
                f"{canonical} is {status} and satisfies the dependency."
                if satisfied
                else (
                    f"{canonical} is {status} and does not satisfy the dependency."
                    if terminal
                    else f"{canonical} is {status} and does not yet satisfy the dependency."
                )
            ),
        )
    if canonical.startswith("MC-"):
        record = next(
            (
                item
                for item in state["milestone"]["criteria_results"]
                if item["id"] == canonical
            ),
            None,
        )
        if record is None:
            return EndpointSatisfaction(
                canonical,
                "milestone-criterion",
                "missing",
                False,
                False,
                False,
                f"{canonical} does not exist.",
            )
        lifecycle = record["lifecycle_status"]
        support = record["support_status"]
        freshness = record["evaluation_freshness"]["status"]
        satisfied = (
            lifecycle == "active" and support == "verified" and freshness == "current"
        )
        terminal = lifecycle == "retired" or support == "verified"
        status = "retired" if lifecycle == "retired" else support
        if satisfied:
            reason = (
                f"{canonical} is active, verified, and current and satisfies "
                "the dependency."
            )
        elif lifecycle == "retired":
            reason = f"{canonical} is retired and does not satisfy the dependency."
        elif support == "verified" and freshness != "current":
            reason = (
                f"{canonical} is verified, but its evaluation is {freshness} and "
                "does not satisfy the dependency."
            )
        else:
            reason = (
                f"{canonical} is {support} and does not yet satisfy the dependency."
            )
        return EndpointSatisfaction(
            canonical,
            "milestone-criterion",
            status,
            terminal,
            satisfied,
            True,
            reason,
        )
    source_key = endpoint_source_key(canonical)
    records = [
        *state["critical_path"].get("items", []),
        *state["critical_path"].get("history", []),
    ]
    record = next(
        (
            item
            for item in records
            if item.get("source_key") == source_key and item.get("manual")
        ),
        None,
    )
    if record is None:
        return EndpointSatisfaction(
            canonical,
            "manual-action",
            "missing",
            False,
            False,
            False,
            f"{canonical} does not exist.",
        )
    status = record["status"]
    satisfied = status == "completed"
    terminal = status in {"completed", "removed"}
    return EndpointSatisfaction(
        canonical,
        "manual-action",
        status,
        terminal,
        satisfied,
        True,
        (
            f"{canonical} is completed and satisfies the dependency."
            if satisfied
            else (
                f"{canonical} is removed and does not satisfy the dependency."
                if terminal
                else f"{canonical} is {status} and does not yet satisfy the dependency."
            )
        ),
    )


def resolve_endpoint(state: CanonicalState, endpoint: str) -> DependencyEndpoint:
    """Resolve endpoint metadata while delegating satisfaction semantics."""

    satisfaction = resolve_endpoint_satisfaction(state, endpoint)
    if not satisfaction.valid:
        raise DependencyInputError(
            f"dependency endpoint {satisfaction.endpoint} does not exist"
        )
    if satisfaction.endpoint_type == "issue":
        record = next(
            item
            for item in state["issues"]["issues"]
            if item["id"] == satisfaction.endpoint
        )
        title = record["title"]
    elif satisfaction.endpoint_type == "decision":
        record = next(
            item
            for item in state["decisions"]["decisions"]
            if item["id"] == satisfaction.endpoint
        )
        title = record["question"]
    elif satisfaction.endpoint_type == "milestone-criterion":
        record = next(
            item
            for item in state["milestone"]["criteria_results"]
            if item["id"] == satisfaction.endpoint
        )
        title = record["description"]
    else:
        source_key = endpoint_source_key(satisfaction.endpoint)
        record = next(
            item
            for item in [
                *state["critical_path"].get("items", []),
                *state["critical_path"].get("history", []),
            ]
            if item.get("source_key") == source_key and item.get("manual")
        )
        title = record["title"]
    return DependencyEndpoint(
        satisfaction.endpoint,
        satisfaction.endpoint_type,
        title,
        satisfaction.status,
        satisfaction.satisfied,
        satisfaction.terminal,
        satisfaction.valid,
        satisfaction.reason,
    )


def dependency_applies(record: Mapping[str, Any], milestone: str) -> bool:
    return record["status"] == "active" and (
        record["scope"] == "project" or record["milestone"] == milestone
    )


def built_in_edges(state: CanonicalState) -> list[tuple[str, str, str]]:
    """Return compatibility-derived prerequisite/dependent endpoint edges."""

    edges: list[tuple[str, str, str]] = []
    for issue in state["issues"]["issues"]:
        for prerequisite in issue["dependencies"]:
            edges.append(
                (
                    prerequisite,
                    issue["id"],
                    "legacy issue dependency",
                )
            )
    pending = {"open", "ready", "blocked", "deferred"}
    for issue in state["issues"]["issues"]:
        if not issue["user_decision_required"]:
            continue
        for decision in state["decisions"]["decisions"]:
            if (
                decision["status"] in pending
                and issue["id"] in decision["affected_issues"]
            ):
                edges.append(
                    (
                        decision["id"],
                        issue["id"],
                        "decision blocks implementation issue",
                    )
                )
    return sorted(set(edges))


def combined_dependency_edges(
    state: CanonicalState, milestone: str
) -> list[tuple[str, str, str, str | None]]:
    edges = [
        (
            record["prerequisite"],
            record["dependent"],
            "explicit",
            record["id"],
        )
        for record in state["dependencies"]["dependencies"]
        if dependency_applies(record, milestone)
    ]
    edges.extend(
        (prerequisite, dependent, reason, None)
        for prerequisite, dependent, reason in built_in_edges(state)
    )
    unique: dict[tuple[str, str], tuple[str, str, str, str | None]] = {}
    for edge in sorted(edges, key=lambda value: (value[0], value[1], value[3] or "")):
        unique.setdefault((edge[0], edge[1]), edge)
    return list(unique.values())


def find_dependency_cycle(
    edges: Iterable[tuple[str, str, str, str | None]],
) -> list[str] | None:
    graph: dict[str, list[str]] = {}
    for prerequisite, dependent, _origin, _dependency_id in edges:
        graph.setdefault(dependent, []).append(prerequisite)
        graph.setdefault(prerequisite, [])
    for values in graph.values():
        values.sort()
    visited: set[str] = set()
    active: list[str] = []

    def visit(endpoint: str) -> list[str] | None:
        if endpoint in active:
            index = active.index(endpoint)
            return [*active[index:], endpoint]
        if endpoint in visited:
            return None
        active.append(endpoint)
        for prerequisite in graph.get(endpoint, []):
            cycle = visit(prerequisite)
            if cycle:
                return cycle
        active.pop()
        visited.add(endpoint)
        return None

    for endpoint in sorted(graph):
        cycle = visit(endpoint)
        if cycle:
            return cycle
    return None


def validate_combined_dependency_graph(state: CanonicalState, milestone: str) -> None:
    cycle = find_dependency_cycle(combined_dependency_edges(state, milestone))
    if cycle:
        raise DependencyCycleError("dependency cycle: " + " -> ".join(cycle))


def _mark_path_stale(critical_path: StateObject, reason: str) -> None:
    reasons = list(critical_path.get("freshness", {}).get("reasons", []))
    reasons.append(reason)
    critical_path["freshness"] = {
        "status": "stale",
        "reasons": list(dict.fromkeys(reasons)),
    }


class DependencyService:
    """Create, query, update, and deactivate explicit dependencies."""

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

    def allocate_dependency_id(
        self, records: Iterable[Mapping[str, Any]] | None = None
    ) -> str:
        source = (
            records
            if records is not None
            else self.repository.load_dependencies()["dependencies"]
        )
        return allocate_dependency_id(source)

    def preview_dependency(self, request: DependencyCreateRequest) -> StateObject:
        state = self.repository.load_all()
        return self._build_or_reactivate(state, request, _timestamp(self.clock))[0]

    def create_dependency(
        self, request: DependencyCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="dependency.add",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            timestamp = _timestamp(self.clock)
            record, reactivated = self._build_or_reactivate(state, request, timestamp)
            if not reactivated:
                state["dependencies"]["dependencies"].append(record)
            validate_combined_dependency_graph(
                state, state["project"]["current_milestone"]
            )
            transaction.set_dependencies(state["dependencies"])
            _mark_path_stale(
                state["critical_path"],
                f"{record['id']} changed the active dependency graph.",
            )
            transaction.set_critical_path(state["critical_path"])
            return transaction.commit(
                changed_fields={
                    "dependency": {
                        "old": "inactive" if reactivated else None,
                        "new": record["id"],
                    }
                },
                details={
                    "dependency": copy.deepcopy(record),
                    "reactivated": reactivated,
                    "path_stale": True,
                    "path_impact": "stale",
                    "recommended_next_command": "studio path calculate",
                },
            )

    def get_dependency(self, dependency_id: str) -> StateObject:
        state = self.repository.load_all()
        record = copy.deepcopy(
            find_dependency(state["dependencies"]["dependencies"], dependency_id)
        )
        return self._with_derived_state(state, record)

    def list_dependencies(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        prerequisite: str | None = None,
        dependent: str | None = None,
        scope: str | None = None,
        include_all: bool = False,
    ) -> list[StateObject]:
        state = self.repository.load_all()
        if status is not None and status not in STATUSES:
            raise DependencyInputError("status must be active or inactive")
        if scope is not None and scope not in SCOPES:
            raise DependencyInputError("scope must be current-milestone or project")
        source_id = canonical_endpoint(source) if source else None
        prerequisite_id = canonical_endpoint(prerequisite) if prerequisite else None
        dependent_id = canonical_endpoint(dependent) if dependent else None
        matches: list[StateObject] = []
        for record in state["dependencies"]["dependencies"]:
            if not include_all and status is None and record["status"] != "active":
                continue
            if status is not None and record["status"] != status:
                continue
            if source_id and source_id not in {
                record["prerequisite"],
                record["dependent"],
            }:
                continue
            if prerequisite_id and record["prerequisite"] != prerequisite_id:
                continue
            if dependent_id and record["dependent"] != dependent_id:
                continue
            if scope and record["scope"] != scope:
                continue
            matches.append(self._with_derived_state(state, copy.deepcopy(record)))
        return sorted(
            matches,
            key=lambda item: (
                item["prerequisite"],
                item["dependent"],
                item["id"],
            ),
        )

    def update_dependency(
        self,
        dependency_id: str,
        patch: DependencyPatch,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        if not patch.requested:
            raise DependencyInputError("at least one dependency update is required")
        with StateTransaction(
            self.root,
            operation="dependency.update",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            record = find_dependency(
                state["dependencies"]["dependencies"], dependency_id
            )
            before = copy.deepcopy(record)
            if patch.prerequisite is not None:
                record["prerequisite"] = canonical_endpoint(patch.prerequisite)
            if patch.dependent is not None:
                record["dependent"] = canonical_endpoint(patch.dependent)
            if patch.reason is not None:
                record["reason"] = _text(patch.reason, field_name="reason")
            if patch.scope is not None:
                if patch.scope not in SCOPES:
                    raise DependencyInputError(
                        "scope must be current-milestone or project"
                    )
                record["scope"] = patch.scope
                record["milestone"] = (
                    state["project"]["current_milestone"]
                    if patch.scope == "current-milestone"
                    else None
                )
            if patch.status is not None:
                if patch.status not in STATUSES:
                    raise DependencyInputError("status must be active or inactive")
                record["status"] = patch.status
            timestamp = _timestamp(self.clock)
            if record["status"] == "inactive":
                record["deactivated_at"] = (
                    before["deactivated_at"] or timestamp
                    if before["status"] == "inactive"
                    else timestamp
                )
                record["deactivation_reason"] = (
                    before["deactivation_reason"]
                    if before["status"] == "inactive"
                    else patch.reason or "Deactivated through dependency update."
                )
            else:
                record["deactivated_at"] = None
                record["deactivation_reason"] = None
            self._validate_record(state, record, ignore_id=record["id"])
            validate_combined_dependency_graph(
                state, state["project"]["current_milestone"]
            )
            changed = {
                key: {"old": before[key], "new": record[key]}
                for key in record
                if before.get(key) != record.get(key) and key != "updated_at"
            }
            if changed:
                record["updated_at"] = timestamp
                changed["updated_at"] = {
                    "old": before["updated_at"],
                    "new": timestamp,
                }
                transaction.set_dependencies(state["dependencies"])
                material = any(
                    key
                    in {
                        "prerequisite",
                        "dependent",
                        "scope",
                        "milestone",
                        "status",
                    }
                    for key in changed
                )
                _mark_path_stale(
                    state["critical_path"],
                    (
                        f"{record['id']} changed the active dependency graph."
                        if material
                        else f"{record['id']} dependency explanation changed."
                    ),
                )
                transaction.set_critical_path(state["critical_path"])
            else:
                material = False
            return transaction.commit(
                changed_fields=changed,
                details={
                    "dependency": self._with_derived_state(
                        state, copy.deepcopy(record)
                    ),
                    "no_op": not changed,
                    "path_stale": bool(changed),
                    "path_impact": "stale" if material else "may-be-stale",
                    "recommended_next_command": (
                        "studio path calculate" if material else "studio path check"
                    ),
                },
            )

    def deactivate_dependency(
        self,
        dependency_id: str,
        reason: str,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        deactivation_reason = _text(reason, field_name="deactivation reason")
        with StateTransaction(
            self.root,
            operation="dependency.deactivate",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            record = find_dependency(
                state["dependencies"]["dependencies"], dependency_id
            )
            if record["status"] == "inactive":
                raise DependencyInputError(f"{record['id']} is already inactive")
            timestamp = _timestamp(self.clock)
            before = copy.deepcopy(record)
            record["status"] = "inactive"
            record["deactivated_at"] = timestamp
            record["deactivation_reason"] = deactivation_reason
            record["updated_at"] = timestamp
            transaction.set_dependencies(state["dependencies"])
            _mark_path_stale(
                state["critical_path"],
                f"{record['id']} was deactivated and may change path ordering.",
            )
            transaction.set_critical_path(state["critical_path"])
            return transaction.commit(
                changed_fields={
                    "status": {"old": before["status"], "new": "inactive"},
                    "deactivation_reason": {
                        "old": None,
                        "new": deactivation_reason,
                    },
                },
                details={
                    "dependency": copy.deepcopy(record),
                    "path_stale": True,
                    "path_impact": "stale",
                    "recommended_next_command": "studio path calculate",
                },
            )

    def reactivate_dependency(
        self, dependency_id: str, *, dry_run: bool = False
    ) -> MutationResult:
        return self.update_dependency(
            dependency_id,
            DependencyPatch(status="active"),
            dry_run=dry_run,
        )

    def validate_dependency_graph(self, state: CanonicalState | None = None) -> None:
        current = copy.deepcopy(state or self.repository.load_all())
        validate_combined_dependency_graph(
            current, current["project"]["current_milestone"]
        )

    def find_upstream(self, source: str) -> tuple[str, ...]:
        endpoint = canonical_endpoint(source)
        return tuple(
            item["prerequisite"]
            for item in self.list_dependencies(include_all=False)
            if item["dependent"] == endpoint
        )

    def find_downstream(self, source: str) -> tuple[str, ...]:
        endpoint = canonical_endpoint(source)
        return tuple(
            item["dependent"]
            for item in self.list_dependencies(include_all=False)
            if item["prerequisite"] == endpoint
        )

    def _build_or_reactivate(
        self,
        state: CanonicalState,
        request: DependencyCreateRequest,
        timestamp: str,
    ) -> tuple[StateObject, bool]:
        prerequisite = canonical_endpoint(request.prerequisite)
        dependent = canonical_endpoint(request.dependent)
        reason = _text(request.reason, field_name="reason")
        scope = request.scope
        if scope not in SCOPES:
            raise DependencyInputError("scope must be current-milestone or project")
        milestone = (
            state["project"]["current_milestone"]
            if scope == "current-milestone"
            else None
        )
        for record in state["dependencies"]["dependencies"]:
            if (
                record["prerequisite"] == prerequisite
                and record["dependent"] == dependent
            ):
                if record["status"] == "active":
                    raise DependencyInputError(
                        f"active dependency {record['id']} already represents "
                        f"{dependent} requires {prerequisite}"
                    )
                record.update(
                    {
                        "reason": reason,
                        "scope": scope,
                        "milestone": milestone,
                        "status": "active",
                        "updated_at": timestamp,
                        "deactivated_at": None,
                        "deactivation_reason": None,
                    }
                )
                self._validate_record(state, record, ignore_id=record["id"])
                return copy.deepcopy(record), True
        record = {
            "id": allocate_dependency_id(state["dependencies"]["dependencies"]),
            "prerequisite": prerequisite,
            "dependent": dependent,
            "relationship": "requires",
            "reason": reason,
            "scope": scope,
            "milestone": milestone,
            "status": "active",
            "created_at": timestamp,
            "updated_at": timestamp,
            "deactivated_at": None,
            "deactivation_reason": None,
        }
        self._validate_record(state, record)
        return record, False

    def _validate_record(
        self,
        state: CanonicalState,
        record: Mapping[str, Any],
        *,
        ignore_id: str | None = None,
    ) -> None:
        prerequisite = resolve_endpoint(state, record["prerequisite"])
        dependent = resolve_endpoint(state, record["dependent"])
        if prerequisite.id == dependent.id:
            raise DependencyInputError("a dependency cannot depend on itself")
        if record["status"] == "active":
            if prerequisite.terminal and not prerequisite.satisfied:
                raise DependencyInputError(
                    f"cannot activate dependency: {prerequisite.reason} "
                    "Update the prerequisite or keep the dependency inactive."
                )
            if dependent.type == "milestone-criterion" and dependent.state == "retired":
                raise DependencyInputError(
                    f"cannot activate dependency: {dependent.id} is retired"
                )
        for other in state["dependencies"]["dependencies"]:
            if other["id"] == ignore_id or other["status"] != "active":
                continue
            if (
                other["prerequisite"] == record["prerequisite"]
                and other["dependent"] == record["dependent"]
                and record["status"] == "active"
            ):
                raise DependencyInputError(
                    f"active dependency {other['id']} already represents this edge"
                )

    def _with_derived_state(
        self, state: CanonicalState, record: StateObject
    ) -> StateObject:
        prerequisite = resolve_endpoint_satisfaction(state, record["prerequisite"])
        active = [
            item
            for item in state["dependencies"]["dependencies"]
            if item["status"] == "active"
        ]
        record["prerequisite_status"] = prerequisite.status
        record["prerequisite_terminal"] = prerequisite.terminal
        record["prerequisite_satisfied"] = prerequisite.satisfied
        record["prerequisite_valid"] = prerequisite.valid
        record["prerequisite_satisfaction_reason"] = prerequisite.reason
        record["prerequisite_state"] = prerequisite.state
        record["upstream"] = sorted(
            item["prerequisite"]
            for item in active
            if item["dependent"] == record["prerequisite"]
        )
        record["downstream"] = sorted(
            item["dependent"]
            for item in active
            if item["prerequisite"] == record["dependent"]
        )
        source_keys = {
            endpoint_source_key(record["prerequisite"]),
            endpoint_source_key(record["dependent"]),
        }
        active_path_keys = {
            item["source_key"] for item in state["critical_path"]["items"]
        }
        record["on_critical_path"] = source_keys <= active_path_keys
        return record
