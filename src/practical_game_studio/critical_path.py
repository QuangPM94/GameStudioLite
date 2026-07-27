"""Dependency-aware milestone critical-path calculation.

The service in this module is deliberately deterministic.  It calculates a
milestone priority path, not a duration-based Critical Path Method schedule.
CLI parsing and human presentation live in :mod:`practical_game_studio.cli`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .decisions import recommendation_support
from .models import MutationResult
from .reporting import render_report_contents
from .state import CanonicalState, StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction
from .validation import validate_state

CP_ID_PATTERN = re.compile(r"^CP-(\d{4,})$")
SOURCE_KEY_PATTERN = re.compile(
    r"^(?:issue:ISS-\d{3,}|decision:DEC-\d{3,}|milestone:MC-\d{3,}|"
    r"verification:(?:ISS|DEC|MC)-\d{3,}:[a-z0-9-]+|manual:[a-z0-9][a-z0-9-]*)$"
)
ACTIVE_ITEM_STATUSES = {"pending", "ready", "blocked", "in-progress"}
HISTORICAL_ITEM_STATUSES = {"completed", "removed"}
INACTIVE_ISSUE_STATUSES = {"resolved", "accepted", "wont-fix", "deferred"}
HISTORICAL_DECISION_STATUSES = {"resolved", "rejected", "superseded"}
PENDING_DECISION_STATUSES = {"open", "ready", "blocked"}

Clock = Callable[[], datetime]


class CriticalPathError(ValueError):
    """Base class for actionable path-domain errors."""


class CriticalPathInputError(CriticalPathError):
    """Calculation input is invalid or internally conflicting."""


class CriticalPathNotFoundError(CriticalPathError):
    """A requested path item does not exist."""


class CriticalPathCycleError(CriticalPathInputError):
    """Explicit source dependencies contain a cycle."""


@dataclass(frozen=True, slots=True)
class PathCalculationRequest:
    """Inputs that can change one calculation."""

    milestone: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    exclude_reason: str | None = None
    max_items: int = 7


@dataclass(frozen=True, slots=True)
class PathCandidate:
    """A possible milestone-gating action before stable CP identity is assigned."""

    type: str
    source_id: str | None
    source_key: str
    title: str
    description: str
    reason: str
    milestone_impact: str
    priority_tier: int
    dependency_keys: tuple[str, ...]
    completion_condition: str
    recommended_action: str
    owner: str
    evidence_required: tuple[str, ...] = ()
    default_selected: bool = True
    pinned: bool = False
    manual: bool = False
    source_status: str = "active"
    evidence_state: str = "unknown"
    sort_hint: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PathItem:
    """Typed projection of one persisted path item."""

    id: str
    type: str
    source_id: str | None
    source_key: str
    title: str
    description: str
    reason: str
    milestone_impact: str
    priority_tier: int
    dependencies: tuple[str, ...]
    status: str
    completion_condition: str
    recommended_action: str
    owner: str
    evidence_required: tuple[str, ...]
    pinned: bool
    manual: bool
    created_at: str
    updated_at: str
    source_status: str
    evidence_state: str

    def to_dict(self) -> StateObject:
        value = asdict(self)
        value["dependencies"] = list(self.dependencies)
        value["evidence_required"] = list(self.evidence_required)
        return value


@dataclass(frozen=True, slots=True)
class PathCalculationResult:
    """A complete, validated-in-memory calculation proposal."""

    critical_path: StateObject
    issues: StateObject
    candidates: tuple[PathCandidate, ...]
    active_items: tuple[PathItem, ...]
    warnings: tuple[str, ...]
    changed: bool

    @property
    def recommended_next(self) -> str | None:
        return self.critical_path["recommended_next_id"]


@dataclass(frozen=True, slots=True)
class PathExplanation:
    """Explanation of one active or historical path item."""

    item: StateObject
    source: StateObject | None
    downstream_items: tuple[str, ...]
    lower_priority_alternatives: tuple[str, ...]
    manual_context: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": copy.deepcopy(self.item),
            "source": copy.deepcopy(self.source),
            "downstream_items": list(self.downstream_items),
            "lower_priority_alternatives": list(self.lower_priority_alternatives),
            "manual_context": self.manual_context,
        }


@dataclass(frozen=True, slots=True)
class PathFreshness:
    """Read-only freshness verdict."""

    status: str
    reasons: tuple[str, ...]

    @property
    def current(self) -> bool:
        return self.status == "current"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reasons": list(self.reasons)}


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "action"


def _criterion_id(result: Mapping[str, Any], index: int) -> str:
    return str(result.get("id") or f"MC-{index:03d}").upper()


def _criterion_support(result: Mapping[str, Any]) -> str:
    return {
        "pass": "verified",
        "partial": "partially-supported",
        "fail": "contradicted",
        "unknown": "unsupported",
    }[str(result["result"])]


def _candidate_fingerprint(candidate: PathCandidate) -> str:
    return _stable_hash(
        {
            "type": candidate.type,
            "source_id": candidate.source_id,
            "source_key": candidate.source_key,
            "title": candidate.title,
            "description": candidate.description,
            "reason": candidate.reason,
            "milestone_impact": candidate.milestone_impact,
            "priority_tier": candidate.priority_tier,
            "dependency_keys": candidate.dependency_keys,
            "completion_condition": candidate.completion_condition,
            "recommended_action": candidate.recommended_action,
            "owner": candidate.owner,
            "evidence_required": candidate.evidence_required,
            "default_selected": candidate.default_selected,
            "source_status": candidate.source_status,
            "evidence_state": candidate.evidence_state,
        }
    )


def allocate_path_item_ids(
    existing_items: Iterable[Mapping[str, Any]], count: int
) -> tuple[str, ...]:
    """Allocate IDs after the highest active or historical CP ID."""

    highest = 0
    for item in existing_items:
        match = CP_ID_PATTERN.fullmatch(str(item.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return tuple(
        f"CP-{number:04d}" for number in range(highest + 1, highest + count + 1)
    )


class CriticalPathService:
    """Calculate, persist, query, explain, and check milestone priority paths."""

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

    def collect_candidates(
        self,
        state: CanonicalState | None = None,
        *,
        milestone: str | None = None,
        pinned_sources: Iterable[str] = (),
    ) -> tuple[PathCandidate, ...]:
        """Collect every usable candidate, including dependency-only records."""

        state = copy.deepcopy(state or self.repository.load_all())
        current_milestone = milestone or state["project"]["current_milestone"]
        pinned = set(pinned_sources)
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        decisions = state["decisions"]["decisions"]
        criterion_decision_dependencies = {
            decision_id
            for criterion in state["milestone"]["criteria_results"]
            if criterion.get("required", True) and criterion["result"] != "pass"
            for decision_id in criterion.get("related_decisions", [])
        }
        pending_decisions = [
            item
            for item in decisions
            if self._decision_is_active(
                item,
                current_milestone,
                milestone_dependency=(item["id"] in criterion_decision_dependencies),
            )
        ]
        decision_by_issue: dict[str, list[StateObject]] = {}
        for decision in pending_decisions:
            for issue_id in decision["affected_issues"]:
                decision_by_issue.setdefault(issue_id, []).append(decision)

        candidates: list[PathCandidate] = []
        issue_by_id = {issue["id"]: issue for issue in state["issues"]["issues"]}
        for issue in state["issues"]["issues"]:
            if issue["status"] in INACTIVE_ISSUE_STATUSES:
                continue
            source_key = f"issue:{issue['id']}"
            linked_decisions = sorted(
                decision_by_issue.get(issue["id"], []), key=lambda item: item["id"]
            )
            dependency_keys = [f"issue:{item}" for item in issue["dependencies"]]
            if issue["user_decision_required"]:
                dependency_keys.extend(
                    f"decision:{item['id']}" for item in linked_decisions
                )
            default_selected, tier = self._issue_priority(
                issue, issue_by_id, pending_decisions
            )
            if source_key in pinned:
                default_selected = True
                tier = min(tier, 5)
            reason = (
                issue["milestone_impact"]
                or issue["player_impact"]
                or issue["description"]
            )
            action = issue["recommended_action"]
            candidate = PathCandidate(
                type="issue",
                source_id=issue["id"],
                source_key=source_key,
                title=issue["title"],
                description=issue["description"],
                reason=reason,
                milestone_impact=issue["milestone_impact"] or reason,
                priority_tier=tier,
                dependency_keys=tuple(dict.fromkeys(dependency_keys)),
                completion_condition=action,
                recommended_action=action,
                owner=issue["owner"],
                evidence_required=tuple(issue["evidence_references"]),
                default_selected=default_selected,
                pinned=source_key in pinned,
                source_status=issue["status"],
                evidence_state=issue["evidence_type"].casefold().replace("_", "-"),
                sort_hint=(issue["created_at"], issue["id"]),
            )
            candidates.append(candidate)

            if self._issue_needs_reproduction(issue, evidence_by_id):
                verification_key = f"verification:{issue['id']}:reproduction"
                verification = PathCandidate(
                    type="verification",
                    source_id=issue["id"],
                    source_key=verification_key,
                    title=f"Reproduce {issue['title']}",
                    description=(
                        f"Test the reported claim for {issue['id']}: "
                        f"{issue['description']}"
                    ),
                    reason=(
                        f"{issue['id']} requires a known failure condition before "
                        "implementation can be verified."
                    ),
                    milestone_impact=reason,
                    priority_tier=4,
                    dependency_keys=tuple(
                        f"issue:{item}" for item in issue["dependencies"]
                    ),
                    completion_condition=(
                        "Capture active observed runtime, test-output, or build-log "
                        f"evidence that reproduces or refutes {issue['id']}."
                    ),
                    recommended_action=f"Reproduce the failure described by {issue['id']}.",
                    owner="technical-lead",
                    evidence_required=("observed reproduction evidence",),
                    default_selected=default_selected,
                    source_status=issue["status"],
                    evidence_state=issue["evidence_type"].casefold().replace("_", "-"),
                    sort_hint=(issue["created_at"], verification_key),
                )
                candidates.append(verification)
                candidates[-2] = dataclass_replace_dependency(
                    candidates[-2], verification_key
                )

        for decision in pending_decisions:
            source_key = f"decision:{decision['id']}"
            support = recommendation_support(decision, evidence_by_id)
            milestone_match = decision["milestone"] == current_milestone
            required_near = decision[
                "decision_required_by"
            ] is not None and date.fromisoformat(
                decision["decision_required_by"]
            ) <= self.clock().date() + timedelta(days=7)
            milestone_dependency = decision["id"] in criterion_decision_dependencies
            default_selected = (
                decision["urgency"] == "blocking"
                or decision["urgency"] == "high"
                and milestone_match
                or required_near
                and milestone_match
                or milestone_dependency
                or source_key in pinned
            )
            if decision["urgency"] == "blocking":
                tier = 1
            elif decision["urgency"] == "high" or milestone_dependency:
                tier = 3
            else:
                tier = 5
            dependencies: list[str] = []
            if self._decision_needs_verification(decision, support):
                dependencies.append(f"verification:{decision['id']}:observed-support")
            recommended = next(
                option
                for option in decision["options"]
                if option["id"] == decision["recommended_option"]
            )
            candidates.append(
                PathCandidate(
                    type="decision",
                    source_id=decision["id"],
                    source_key=source_key,
                    title=decision["question"],
                    description=decision["context"],
                    reason=(
                        decision["recommendation_reason"]
                        or f"{decision['id']} gates current milestone work."
                    ),
                    milestone_impact=(
                        f"Affects {', '.join(decision['affected_issues'])}."
                        if decision["affected_issues"]
                        else f"Affects milestone: {decision['milestone']}."
                    ),
                    priority_tier=tier,
                    dependency_keys=tuple(dependencies),
                    completion_condition=(
                        f"Record the owner's choice for {decision['id']} and its "
                        "accepted trade-off."
                    ),
                    recommended_action=(
                        f"Choose {recommended['id']} — {recommended['label']}, or "
                        "record an explicit alternative."
                    ),
                    owner=decision["decision_owner"],
                    evidence_required=tuple(decision["supporting_evidence"]),
                    default_selected=default_selected,
                    pinned=source_key in pinned,
                    source_status=decision["status"],
                    evidence_state=support["level"],
                    sort_hint=(
                        decision["decision_required_by"] or "9999-12-31",
                        decision["created_at"],
                        decision["id"],
                    ),
                )
            )
            if dependencies:
                candidates.append(
                    PathCandidate(
                        type="verification",
                        source_id=decision["id"],
                        source_key=dependencies[0],
                        title=f"Verify evidence needed for {decision['id']}",
                        description=(
                            f"Test the claim needed to choose responsibly: "
                            f"{decision['question']}"
                        ),
                        reason=(
                            f"{decision['id']} is blocked and its recommendation is "
                            f"{support['level']}."
                        ),
                        milestone_impact=(
                            f"Without sufficient evidence, {decision['id']} cannot "
                            "unlock its affected work."
                        ),
                        priority_tier=4,
                        dependency_keys=(),
                        completion_condition=(
                            "Attach active observed evidence that directly "
                            f"distinguishes the options in {decision['id']}."
                        ),
                        recommended_action=(
                            f"Run the smallest observation that distinguishes "
                            f"{decision['id']} options."
                        ),
                        owner="player-advocate",
                        evidence_required=(
                            "decision-distinguishing observed evidence",
                        ),
                        default_selected=default_selected,
                        source_status=decision["status"],
                        evidence_state=support["level"],
                        sort_hint=(decision["created_at"], dependencies[0]),
                    )
                )

        for index, criterion in enumerate(
            state["milestone"]["criteria_results"], start=1
        ):
            criterion_id = _criterion_id(criterion, index)
            required = bool(criterion.get("required", True))
            support = _criterion_support(criterion)
            if not required and support in {"unsupported", "partially-supported"}:
                continue
            related = [
                *(f"issue:{item}" for item in criterion.get("related_issues", [])),
                *(
                    f"decision:{item}"
                    for item in criterion.get("related_decisions", [])
                ),
            ]
            if support in {"unsupported", "partially-supported"} and required:
                source_key = f"verification:{criterion_id}:observed-support"
                candidates.append(
                    PathCandidate(
                        type="verification",
                        source_id=criterion_id,
                        source_key=source_key,
                        title=f"Verify milestone criterion {criterion_id}",
                        description=(
                            f"Test whether the required claim is true: "
                            f"{criterion['criterion']}"
                        ),
                        reason=(
                            f"Required milestone criterion {criterion_id} is {support}."
                        ),
                        milestone_impact=(
                            f"The milestone verdict cannot be supported until "
                            f"{criterion_id} has sufficient evidence."
                        ),
                        priority_tier=4,
                        dependency_keys=tuple(dict.fromkeys(related)),
                        completion_condition=(
                            "Attach active observed evidence that directly supports "
                            f"{criterion_id}: {criterion['criterion']}"
                        ),
                        recommended_action=(
                            f"Run a concrete verification for {criterion_id}: "
                            f"{criterion['criterion']}"
                        ),
                        owner="player-advocate",
                        evidence_required=tuple(criterion["evidence_references"])
                        or ("observed criterion evidence",),
                        default_selected=True,
                        pinned=source_key in pinned,
                        source_status=criterion["result"],
                        evidence_state=support,
                        sort_hint=(f"{index:06d}", criterion_id),
                    )
                )
            elif support == "contradicted" and required:
                source_key = f"milestone:{criterion_id}"
                candidates.append(
                    PathCandidate(
                        type="milestone-criterion",
                        source_id=criterion_id,
                        source_key=source_key,
                        title=f"Satisfy milestone criterion {criterion_id}",
                        description=criterion["criterion"],
                        reason=(
                            f"Required milestone criterion {criterion_id} is "
                            "contradicted by current evidence."
                        ),
                        milestone_impact=(
                            "The current milestone cannot pass while this required "
                            "criterion is contradicted."
                        ),
                        priority_tier=1,
                        dependency_keys=tuple(dict.fromkeys(related)),
                        completion_condition=criterion["criterion"],
                        recommended_action=(
                            criterion["notes"]
                            or f"Address the failure of {criterion_id}."
                        ),
                        owner="producer",
                        evidence_required=tuple(criterion["evidence_references"]),
                        default_selected=True,
                        pinned=source_key in pinned,
                        source_status=criterion["result"],
                        evidence_state=support,
                        sort_hint=(f"{index:06d}", criterion_id),
                    )
                )

        candidates.extend(self._manual_candidates(state, pinned))
        unique: dict[str, PathCandidate] = {}
        for candidate in candidates:
            if candidate.source_key in unique:
                raise CriticalPathInputError(
                    f"duplicate candidate source key {candidate.source_key}"
                )
            unique[candidate.source_key] = candidate
        return tuple(sorted(unique.values(), key=self._candidate_sort_key))

    def calculate_path(
        self,
        request: PathCalculationRequest,
        *,
        state: CanonicalState | None = None,
    ) -> PathCalculationResult:
        """Calculate and reconcile a proposed path without writing files."""

        self._validate_request(request)
        state = copy.deepcopy(state or self.repository.load_all())
        existing = state["critical_path"]
        milestone = (request.milestone or state["project"]["current_milestone"]).strip()
        if not milestone:
            raise CriticalPathInputError("milestone cannot be empty")

        includes = list(existing.get("pinned_sources", []))
        excludes = list(existing.get("excluded_sources", []))
        exclusion_reasons = dict(existing.get("exclusion_reasons", {}))
        provisional_candidates = self.collect_candidates(
            state, milestone=milestone, pinned_sources=includes
        )
        includes.extend(
            self._resolve_source_reference(value, provisional_candidates, existing)
            for value in request.include
        )
        requested_excludes = [
            self._resolve_source_reference(value, provisional_candidates, existing)
            for value in request.exclude
        ]
        if requested_excludes and not (request.exclude_reason or "").strip():
            raise CriticalPathInputError(
                "--exclude-reason is required when --exclude is used"
            )
        excludes.extend(requested_excludes)
        includes = list(dict.fromkeys(includes))
        excludes = list(dict.fromkeys(excludes))
        for source_key in requested_excludes:
            exclusion_reasons[source_key] = request.exclude_reason.strip()
        for source_key in list(exclusion_reasons):
            if source_key not in excludes:
                del exclusion_reasons[source_key]
        overlap = sorted(set(includes) & set(excludes))
        if overlap:
            raise CriticalPathInputError(
                f"source cannot be both pinned and excluded: {', '.join(overlap)}"
            )

        candidates = self.collect_candidates(
            state, milestone=milestone, pinned_sources=includes
        )
        by_key = {candidate.source_key: candidate for candidate in candidates}
        warnings = self._manual_control_warnings(
            state, includes, excludes, by_key, existing
        )
        valid_includes = [source_key for source_key in includes if source_key in by_key]
        valid_excludes = [source_key for source_key in excludes if source_key in by_key]
        roots = [
            candidate
            for candidate in candidates
            if candidate.default_selected or candidate.source_key in valid_includes
        ]
        roots.sort(key=self._candidate_sort_key)
        selected, size_warnings = self._select_candidates(
            roots,
            by_key,
            excluded=set(valid_excludes),
            max_items=request.max_items,
            state=state,
        )
        warnings.extend(size_warnings)
        ordered = self.order_dependencies(selected)
        timestamp = _timestamp(self.clock)
        active, history = self.reconcile_existing_path(
            ordered, existing, timestamp=timestamp, state=state
        )
        recommended = self._recommended_next(active)
        snapshot = self._build_snapshot(
            milestone, candidates, includes, excludes, state
        )
        proposed = {
            "schema_version": "2.0",
            "current_milestone": milestone,
            "milestone_override": request.milestone is not None,
            "milestone_success_criteria": list(
                state["milestone"]["success_criteria"]
                if milestone == state["milestone"]["milestone"]
                else []
            ),
            "configured_max_items": request.max_items,
            "items": active,
            "history": history,
            "recommended_next_id": recommended,
            "pinned_sources": valid_includes,
            "excluded_sources": valid_excludes,
            "exclusion_reasons": {
                key: exclusion_reasons[key] for key in valid_excludes
            },
            "non_critical_work": list(existing["non_critical_work"]),
            "exit_condition": existing["exit_condition"],
            "calculated_at": timestamp,
            "calculation_snapshot": snapshot,
            "freshness": {"status": "current", "reasons": []},
            "warnings": list(dict.fromkeys(warnings)),
        }
        issues = copy.deepcopy(state["issues"])
        active_issue_ids = {
            item["source_id"] for item in active if item["type"] == "issue"
        }
        for issue in issues["issues"]:
            issue["on_critical_path"] = issue["id"] in active_issue_ids

        logical_existing = copy.deepcopy(existing)
        logical_proposed = copy.deepcopy(proposed)
        for value in (logical_existing, logical_proposed):
            value.pop("calculated_at", None)
            value.pop("freshness", None)
        if logical_existing == logical_proposed:
            proposed = copy.deepcopy(existing)
            issues = copy.deepcopy(state["issues"])
            changed = False
        else:
            changed = proposed != existing or issues != state["issues"]
        typed_items = tuple(self._typed_item(item) for item in proposed["items"])
        proposed_state = copy.deepcopy(state)
        proposed_state["critical_path"] = copy.deepcopy(proposed)
        proposed_state["issues"] = copy.deepcopy(issues)
        validation = validate_state(self.root, proposed_state)
        if not validation.ok:
            raise CriticalPathInputError(
                "proposed path is invalid: " + "; ".join(validation.errors)
            )
        return PathCalculationResult(
            critical_path=proposed,
            issues=issues,
            candidates=candidates,
            active_items=typed_items,
            warnings=tuple(proposed.get("warnings", warnings)),
            changed=changed,
        )

    def order_dependencies(
        self, candidates: Iterable[PathCandidate]
    ) -> tuple[PathCandidate, ...]:
        """Return a stable topological order or report the exact cycle."""

        items = {item.source_key: item for item in candidates}
        dependencies = {
            key: [
                dependency for dependency in item.dependency_keys if dependency in items
            ]
            for key, item in items.items()
        }
        cycle = self._find_cycle(dependencies)
        if cycle:
            raise CriticalPathCycleError("dependency cycle: " + " -> ".join(cycle))
        indegree = {key: len(value) for key, value in dependencies.items()}
        downstream: dict[str, list[str]] = {key: [] for key in items}
        for key, values in dependencies.items():
            for dependency in values:
                downstream[dependency].append(key)
        ready = [items[key] for key, degree in indegree.items() if degree == 0]
        ready.sort(key=self._candidate_sort_key)
        ordered: list[PathCandidate] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for child in sorted(downstream[current.source_key]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(items[child])
                    ready.sort(key=self._candidate_sort_key)
        return tuple(ordered)

    def allocate_path_item_ids(
        self, existing_items: Iterable[Mapping[str, Any]], count: int
    ) -> tuple[str, ...]:
        return allocate_path_item_ids(existing_items, count)

    def reconcile_existing_path(
        self,
        candidates: Iterable[PathCandidate],
        critical_path: Mapping[str, Any],
        *,
        timestamp: str,
        state: CanonicalState | None = None,
    ) -> tuple[list[StateObject], list[StateObject]]:
        """Preserve stable IDs and compact history while reconciling candidates."""

        state = state or self.repository.load_all()
        active_existing = list(critical_path.get("items", []))
        history_existing = list(critical_path.get("history", []))
        all_existing = [*active_existing, *history_existing]
        by_source: dict[str, StateObject] = {}
        id_sources: dict[str, str] = {}
        for item in all_existing:
            source_key = item.get("source_key")
            if not source_key:
                continue
            if item["id"] in id_sources and id_sources[item["id"]] != source_key:
                raise CriticalPathInputError(
                    f"{item['id']} is reused for different source keys"
                )
            id_sources[item["id"]] = source_key
            by_source.setdefault(source_key, item)
        candidates = tuple(candidates)
        new_keys = [
            item.source_key for item in candidates if item.source_key not in by_source
        ]
        allocated = iter(allocate_path_item_ids(all_existing, len(new_keys)))
        allocated_by_key = {key: next(allocated) for key in new_keys}
        key_to_id = {
            item.source_key: (
                by_source[item.source_key]["id"]
                if item.source_key in by_source
                else allocated_by_key[item.source_key]
            )
            for item in candidates
        }

        active: list[StateObject] = []
        for candidate in candidates:
            previous = by_source.get(candidate.source_key)
            dependencies = [
                key_to_id[key] for key in candidate.dependency_keys if key in key_to_id
            ]
            status = self._item_status(candidate, dependencies)
            created_at = previous["created_at"] if previous else timestamp
            item = PathItem(
                id=key_to_id[candidate.source_key],
                type=candidate.type,
                source_id=candidate.source_id,
                source_key=candidate.source_key,
                title=candidate.title,
                description=candidate.description,
                reason=candidate.reason,
                milestone_impact=candidate.milestone_impact,
                priority_tier=candidate.priority_tier,
                dependencies=tuple(dependencies),
                status=status,
                completion_condition=candidate.completion_condition,
                recommended_action=candidate.recommended_action,
                owner=candidate.owner,
                evidence_required=candidate.evidence_required,
                pinned=candidate.pinned,
                manual=candidate.manual,
                created_at=created_at,
                updated_at=timestamp,
                source_status=candidate.source_status,
                evidence_state=candidate.evidence_state,
            ).to_dict()
            if previous:
                comparison = copy.deepcopy(item)
                prior = copy.deepcopy(previous)
                comparison.pop("updated_at", None)
                prior.pop("updated_at", None)
                if comparison == prior:
                    item["updated_at"] = previous["updated_at"]
            active.append(item)

        selected_keys = {item["source_key"] for item in active}
        history_by_source = {
            item["source_key"]: copy.deepcopy(item)
            for item in history_existing
            if item.get("source_key") not in selected_keys
        }
        for previous in active_existing:
            if previous.get("source_key") in selected_keys:
                continue
            historical = copy.deepcopy(previous)
            historical["status"] = self._historical_status(previous, state)
            if historical.get("updated_at") != timestamp:
                historical["updated_at"] = timestamp
            history_by_source[historical["source_key"]] = historical
        history = sorted(
            history_by_source.values(),
            key=lambda item: (item["created_at"], item["id"]),
        )
        return active, history

    def explain_item(self, path_item_id: str) -> PathExplanation:
        """Explain one active or historical item from canonical state."""

        canonical = path_item_id.strip().upper()
        if not CP_ID_PATTERN.fullmatch(canonical):
            raise CriticalPathInputError(
                f"invalid path item ID '{path_item_id}'; expected CP-0001"
            )
        state = self.repository.load_all()
        critical_path = state["critical_path"]
        records = [*critical_path["items"], *critical_path.get("history", [])]
        item = next((value for value in records if value["id"] == canonical), None)
        if item is None:
            raise CriticalPathNotFoundError(
                f"path item {canonical} was not found; run 'studio path show --all'"
            )
        source = self._source_record(state, item)
        downstream = tuple(
            value["id"]
            for value in critical_path["items"]
            if canonical in value["dependencies"]
        )
        selected_keys = {value["source_key"] for value in critical_path["items"]}
        candidates = self.collect_candidates(
            state,
            milestone=critical_path["current_milestone"],
            pinned_sources=critical_path["pinned_sources"],
        )
        alternatives = tuple(
            f"{candidate.source_id or candidate.source_key} — {candidate.title}"
            for candidate in candidates
            if candidate.source_key not in selected_keys and candidate.default_selected
        )[:5]
        manual_context: str | None = None
        if item["source_key"] in critical_path["pinned_sources"]:
            manual_context = "Explicitly included by a persistent manual control."
        elif item["source_key"] in critical_path["excluded_sources"]:
            manual_context = (
                "Explicitly excluded: "
                f"{critical_path['exclusion_reasons'][item['source_key']]}"
            )
        elif item["manual"]:
            manual_context = "Preserved as an explicitly authored manual action."
        return PathExplanation(
            item=copy.deepcopy(item),
            source=source,
            downstream_items=downstream,
            lower_priority_alternatives=alternatives,
            manual_context=manual_context,
        )

    def check_freshness(self, state: CanonicalState | None = None) -> PathFreshness:
        """Compare current source state with the last calculation snapshot."""

        state = copy.deepcopy(state or self.repository.load_all())
        critical_path = state["critical_path"]
        snapshot = critical_path.get("calculation_snapshot") or {}
        if not snapshot:
            if not critical_path["items"]:
                return PathFreshness("absent", ("No active milestone critical path.",))
            return PathFreshness("stale", ("The path predates freshness snapshots.",))
        reasons: list[str] = (
            list(critical_path.get("freshness", {}).get("reasons", []))
            if critical_path.get("freshness", {}).get("status") == "stale"
            else []
        )
        project_milestone = state["project"]["current_milestone"]
        if critical_path[
            "current_milestone"
        ] != project_milestone and not critical_path.get("milestone_override", False):
            reasons.append(
                f"Milestone changed from {critical_path['current_milestone']} "
                f"to {project_milestone}."
            )
        candidates = self.collect_candidates(
            state,
            milestone=critical_path["current_milestone"],
            pinned_sources=critical_path["pinned_sources"],
        )
        current = {item.source_key: item for item in candidates}
        current_criteria = [
            {
                "id": _criterion_id(item, index),
                "result": item["result"],
                "required": item.get("required", True),
                "evidence_references": item["evidence_references"],
                "related_issues": item.get("related_issues", []),
                "related_decisions": item.get("related_decisions", []),
            }
            for index, item in enumerate(
                state["milestone"]["criteria_results"], start=1
            )
        ]
        if snapshot.get("criteria_fingerprint") != _stable_hash(current_criteria):
            reasons.append("Milestone criterion state changed.")
        controls_fingerprint = _stable_hash(
            {
                "pinned_sources": critical_path["pinned_sources"],
                "excluded_sources": critical_path["excluded_sources"],
            }
        )
        if snapshot.get("manual_controls_fingerprint") != controls_fingerprint:
            reasons.append("Manual inclusion or exclusion controls changed.")
        relevant_evidence = set(snapshot.get("evidence_sources", []))
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        current_evidence_fingerprint = _stable_hash(
            {
                reference: evidence_by_id.get(reference)
                for reference in sorted(relevant_evidence)
            }
        )
        if (
            snapshot.get("evidence_fingerprint")
            and snapshot["evidence_fingerprint"] != current_evidence_fingerprint
        ):
            reasons.append("Evidence support changed materially.")
        prior = snapshot.get("candidates", {})
        for item in critical_path["items"]:
            source_key = item["source_key"]
            candidate = current.get(source_key)
            if candidate is None:
                reasons.append(f"{source_key} is missing or no longer active.")
                continue
            before = prior.get(source_key)
            if before and before["fingerprint"] != _candidate_fingerprint(candidate):
                if before.get("source_status") != candidate.source_status:
                    reasons.append(
                        f"{candidate.source_id or source_key} status changed from "
                        f"{before.get('source_status')} to {candidate.source_status}."
                    )
                elif before.get("evidence_state") != candidate.evidence_state:
                    reasons.append(
                        f"{candidate.source_id or source_key} evidence support "
                        f"changed from {before.get('evidence_state')} to "
                        f"{candidate.evidence_state}."
                    )
                else:
                    reasons.append(
                        f"{candidate.source_id or source_key} materially changed."
                    )
        active_keys = {item["source_key"] for item in critical_path["items"]}
        for candidate in candidates:
            if (
                candidate.default_selected
                and candidate.priority_tier == 1
                and candidate.source_key not in active_keys
                and candidate.source_key not in critical_path["excluded_sources"]
            ):
                reasons.append(
                    f"{candidate.source_id or candidate.source_key} is a new "
                    "hard milestone blocker."
                )
        for source_key in critical_path["pinned_sources"]:
            if source_key not in current:
                reasons.append(f"Pinned source {source_key} is missing or inactive.")
        for source_key in critical_path["excluded_sources"]:
            if source_key not in current:
                reasons.append(f"Excluded source {source_key} is missing or inactive.")
            if source_key not in critical_path["exclusion_reasons"]:
                reasons.append(f"Excluded source {source_key} has no reason.")
        status = "stale" if reasons else "current"
        return PathFreshness(status, tuple(dict.fromkeys(reasons)))

    def apply_path(
        self,
        request: PathCalculationRequest,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        """Calculate and commit the proposed path through ``StateTransaction``."""

        with StateTransaction(
            self.root,
            operation="path.calculate",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            calculated = self.calculate_path(request, state=state)
            if calculated.changed:
                transaction.set_critical_path(calculated.critical_path)
                if calculated.issues != state["issues"]:
                    transaction.set_issues(calculated.issues)
            details = {
                "milestone": calculated.critical_path["current_milestone"],
                "active_count": len(calculated.active_items),
                "recommended_next": calculated.recommended_next,
                "items": [
                    {
                        "id": item.id,
                        "type": item.type,
                        "source_id": item.source_id,
                        "source_key": item.source_key,
                        "title": item.title,
                        "status": item.status,
                        "priority_tier": item.priority_tier,
                        "dependencies": list(item.dependencies),
                    }
                    for item in calculated.active_items
                ],
                "no_op": not calculated.changed,
            }
            return transaction.commit(
                warnings=calculated.warnings,
                changed_fields={
                    "critical_path": {
                        "old": [item["id"] for item in state["critical_path"]["items"]],
                        "new": [item.id for item in calculated.active_items],
                    }
                }
                if calculated.changed
                else {},
                details=details,
            )

    def show_path(self, *, include_history: bool = False) -> dict[str, Any]:
        """Return a stable read model for ``studio path show``."""

        state = self.repository.load_all()
        critical_path = copy.deepcopy(state["critical_path"])
        freshness = self.check_freshness(state)
        blocked = [
            item["id"] for item in critical_path["items"] if item["status"] == "blocked"
        ]
        result = {
            "milestone": critical_path["current_milestone"],
            "items": critical_path["items"],
            "recommended_next": critical_path["recommended_next_id"],
            "blocked_items": blocked,
            "pinned_sources": critical_path["pinned_sources"],
            "excluded_sources": critical_path["excluded_sources"],
            "exclusion_reasons": critical_path["exclusion_reasons"],
            "non_critical_work": critical_path["non_critical_work"],
            "calculated_at": critical_path["calculated_at"],
            "freshness": freshness.to_dict(),
            "warnings": critical_path["warnings"],
        }
        if include_history:
            result["history"] = critical_path["history"]
        return result

    @staticmethod
    def _validate_request(request: PathCalculationRequest) -> None:
        if not 3 <= request.max_items <= 10:
            raise CriticalPathInputError("--max-items must be between 3 and 10")
        if request.exclude_reason and not request.exclude:
            raise CriticalPathInputError(
                "--exclude-reason requires at least one --exclude"
            )

    def _issue_priority(
        self,
        issue: Mapping[str, Any],
        issue_by_id: Mapping[str, Mapping[str, Any]],
        pending_decisions: Iterable[Mapping[str, Any]],
    ) -> tuple[bool, int]:
        if issue["severity"] == "blocker" or issue["status"] == "blocked":
            return True, 1
        if issue["severity"] == "critical":
            return True, 2
        blocks_critical = any(
            issue_by_id.get(item, {}).get("severity") in {"blocker", "critical"}
            and issue_by_id[item]["status"] not in INACTIVE_ISSUE_STATUSES
            for item in issue["issues_blocked"]
        )
        required_by_decision = any(
            issue["id"] in decision["affected_issues"]
            and decision["urgency"] in {"blocking", "high"}
            for decision in pending_decisions
        )
        if blocks_critical or required_by_decision:
            return True, 3
        if issue["severity"] == "major" and issue["milestone_impact"].strip():
            return True, 5
        return False, 5

    @staticmethod
    def _issue_needs_reproduction(
        issue: Mapping[str, Any],
        evidence_by_id: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        if issue["evidence_type"] != "USER_REPORTED":
            return False
        active_observed = any(
            reference in evidence_by_id
            and evidence_by_id[reference]["status"] == "active"
            and evidence_by_id[reference]["classification"] == "observed"
            for reference in issue["evidence_references"]
        )
        if active_observed:
            return False
        text = " ".join(
            (
                issue["description"],
                issue["recommended_action"],
                issue["milestone_impact"],
            )
        ).casefold()
        explicit = any(
            token in text
            for token in ("reproduc", "verify", "failure condition", "confirm crash")
        )
        return explicit and issue["severity"] in {"blocker", "critical"}

    def _decision_is_active(
        self,
        decision: Mapping[str, Any],
        milestone: str,
        *,
        milestone_dependency: bool = False,
    ) -> bool:
        if decision["status"] in PENDING_DECISION_STATUSES:
            return True
        if decision["status"] != "deferred":
            return False
        if milestone_dependency:
            return True
        required_by = decision["decision_required_by"]
        if not required_by:
            return False
        return date.fromisoformat(required_by) <= self.clock().date()

    @staticmethod
    def _decision_needs_verification(
        decision: Mapping[str, Any], support: Mapping[str, Any]
    ) -> bool:
        if decision["status"] != "blocked" or support["level"] not in {
            "unsupported",
            "conflicted",
        }:
            return False
        text = " ".join(
            (
                decision["context"],
                decision["recommendation_reason"],
                decision["revisit_condition"] or "",
            )
        ).casefold()
        return any(
            token in text
            for token in ("evidence", "observe", "test", "verify", "playtest")
        )

    def _manual_candidates(
        self, state: CanonicalState, pinned: set[str]
    ) -> list[PathCandidate]:
        critical_path = state["critical_path"]
        existing = [
            *critical_path.get("items", []),
            *critical_path.get("history", []),
        ]
        id_to_source = {
            item["id"]: item.get("source_key")
            for item in existing
            if item.get("source_key")
        }
        candidates: list[PathCandidate] = []
        seen: set[str] = set()
        controlled = set(critical_path.get("pinned_sources", [])) | set(
            critical_path.get("excluded_sources", [])
        )
        for item in existing:
            if not item.get("manual"):
                continue
            if (
                item.get("status") in {"completed", "removed"}
                and item.get("source_key") not in controlled
            ):
                continue
            source_key = item["source_key"]
            if source_key in seen:
                continue
            seen.add(source_key)
            dependencies: list[str] = []
            for dependency in item.get("dependencies", []):
                source = id_to_source.get(dependency)
                if source is None:
                    raise CriticalPathInputError(
                        f"{item['id']} has missing manual dependency {dependency}"
                    )
                dependencies.append(source)
            candidates.append(
                PathCandidate(
                    type="manual-action",
                    source_id=item.get("source_id"),
                    source_key=source_key,
                    title=item["title"],
                    description=item["description"],
                    reason=item["reason"],
                    milestone_impact=item["milestone_impact"],
                    priority_tier=item["priority_tier"],
                    dependency_keys=tuple(dependencies),
                    completion_condition=item["completion_condition"],
                    recommended_action=item["recommended_action"],
                    owner=item["owner"],
                    evidence_required=tuple(item["evidence_required"]),
                    default_selected=item.get("status") not in {"completed", "removed"},
                    pinned=source_key in pinned,
                    manual=True,
                    source_status=item.get("source_status", "active"),
                    evidence_state=item.get("evidence_state", "unknown"),
                    sort_hint=(item["created_at"], item["id"]),
                )
            )
        return candidates

    @staticmethod
    def _candidate_sort_key(candidate: PathCandidate) -> tuple[Any, ...]:
        type_order = {
            "verification": 0,
            "decision": 1,
            "issue": 2,
            "milestone-criterion": 3,
            "manual-action": 4,
        }
        return (
            candidate.priority_tier,
            type_order[candidate.type],
            candidate.sort_hint,
            candidate.source_key,
        )

    def _select_candidates(
        self,
        roots: Iterable[PathCandidate],
        by_key: Mapping[str, PathCandidate],
        *,
        excluded: set[str],
        max_items: int,
        state: CanonicalState,
    ) -> tuple[tuple[PathCandidate, ...], list[str]]:
        selected: dict[str, PathCandidate] = {}
        warnings: list[str] = []

        def closure(source_key: str, visiting: tuple[str, ...] = ()) -> list[str]:
            if source_key in visiting:
                cycle = [*visiting[visiting.index(source_key) :], source_key]
                raise CriticalPathCycleError("dependency cycle: " + " -> ".join(cycle))
            candidate = by_key.get(source_key)
            if candidate is None:
                raise CriticalPathInputError(
                    f"missing dependency candidate {source_key}"
                )
            result: list[str] = []
            for dependency in candidate.dependency_keys:
                dependency_candidate = by_key.get(dependency)
                if dependency_candidate is None:
                    # A completed/inactive source satisfies the dependency.
                    if self._source_is_completed(dependency, state):
                        continue
                    raise CriticalPathInputError(
                        f"{candidate.source_key} references missing dependency "
                        f"{dependency}"
                    )
                if dependency in excluded:
                    raise CriticalPathInputError(
                        f"excluded source {dependency} is required by "
                        f"{candidate.source_key}; remove the exclusion or choose "
                        "different work"
                    )
                result.extend(closure(dependency, (*visiting, source_key)))
            result.append(source_key)
            return list(dict.fromkeys(result))

        for root in roots:
            if root.source_key in excluded:
                continue
            required = closure(root.source_key)
            new = [key for key in required if key not in selected]
            if len(selected) + len(new) > max_items:
                if len(required) > max_items or any(by_key[key].pinned for key in new):
                    for key in new:
                        selected[key] = by_key[key]
                    if len(selected) > max_items:
                        limit = "seven" if max_items == 7 else str(max_items)
                        warnings.append(
                            "The milestone currently has more than "
                            f"{limit} mandatory dependency items. The path "
                            "could not be reduced safely."
                        )
                continue
            for key in new:
                selected[key] = by_key[key]
        if len(selected) < 3:
            warnings.append(
                "Fewer than three milestone-gating items were identified; no "
                "filler work was added."
            )
        return tuple(selected.values()), warnings

    @staticmethod
    def _source_is_completed(source_key: str, state: CanonicalState) -> bool:
        if source_key.startswith("issue:"):
            source_id = source_key.split(":", 1)[1]
            return any(
                item["id"] == source_id and item["status"] in INACTIVE_ISSUE_STATUSES
                for item in state["issues"]["issues"]
            )
        if source_key.startswith("decision:"):
            source_id = source_key.split(":", 1)[1]
            return any(
                item["id"] == source_id
                and item["status"] in HISTORICAL_DECISION_STATUSES
                for item in state["decisions"]["decisions"]
            )
        return False

    @staticmethod
    def _find_cycle(dependencies: Mapping[str, list[str]]) -> list[str] | None:
        visited: set[str] = set()
        active: list[str] = []

        def visit(key: str) -> list[str] | None:
            if key in active:
                index = active.index(key)
                return [*active[index:], key]
            if key in visited:
                return None
            active.append(key)
            for dependency in dependencies.get(key, []):
                cycle = visit(dependency)
                if cycle:
                    return cycle
            active.pop()
            visited.add(key)
            return None

        for key in sorted(dependencies):
            cycle = visit(key)
            if cycle:
                return cycle
        return None

    @staticmethod
    def _item_status(candidate: PathCandidate, dependency_ids: list[str]) -> str:
        if dependency_ids:
            return "blocked"
        if candidate.source_status == "in-progress":
            return "in-progress"
        if candidate.source_status == "blocked":
            return "blocked"
        return "ready"

    @staticmethod
    def _historical_status(item: Mapping[str, Any], state: CanonicalState) -> str:
        source_key = item["source_key"]
        if source_key.startswith("issue:"):
            source_id = source_key.split(":", 1)[1]
            record = next(
                (
                    value
                    for value in state["issues"]["issues"]
                    if value["id"] == source_id
                ),
                None,
            )
            if record and record["status"] in {"resolved", "accepted"}:
                return "completed"
        if source_key.startswith("decision:"):
            source_id = source_key.split(":", 1)[1]
            record = next(
                (
                    value
                    for value in state["decisions"]["decisions"]
                    if value["id"] == source_id
                ),
                None,
            )
            if record and record["status"] == "resolved":
                return "completed"
        return "removed"

    @staticmethod
    def _recommended_next(items: list[StateObject]) -> str | None:
        eligible = [
            (index, item)
            for index, item in enumerate(items)
            if not item["dependencies"] and item["status"] in {"ready", "in-progress"}
        ]
        if not eligible:
            return None
        eligible.sort(
            key=lambda pair: (
                pair[1]["priority_tier"],
                pair[1]["status"] != "in-progress",
                pair[0],
            )
        )
        return eligible[0][1]["id"]

    def _build_snapshot(
        self,
        milestone: str,
        candidates: Iterable[PathCandidate],
        includes: Iterable[str],
        excludes: Iterable[str],
        state: CanonicalState,
    ) -> StateObject:
        candidates = tuple(candidates)
        candidate_snapshot = {
            candidate.source_key: {
                "fingerprint": _candidate_fingerprint(candidate),
                "priority_tier": candidate.priority_tier,
                "source_status": candidate.source_status,
                "evidence_state": candidate.evidence_state,
            }
            for candidate in candidates
        }
        criteria = [
            {
                "id": _criterion_id(item, index),
                "result": item["result"],
                "required": item.get("required", True),
                "evidence_references": item["evidence_references"],
                "related_issues": item.get("related_issues", []),
                "related_decisions": item.get("related_decisions", []),
            }
            for index, item in enumerate(
                state["milestone"]["criteria_results"], start=1
            )
        ]
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        relevant_evidence = {
            reference
            for candidate in candidates
            for reference in candidate.evidence_required
            if reference.startswith("EVD-")
        }
        return {
            "milestone": milestone,
            "candidates": candidate_snapshot,
            "criteria_fingerprint": _stable_hash(criteria),
            "evidence_sources": sorted(relevant_evidence),
            "evidence_fingerprint": _stable_hash(
                {
                    reference: evidence_by_id.get(reference)
                    for reference in sorted(relevant_evidence)
                }
            ),
            "manual_controls_fingerprint": _stable_hash(
                {
                    "pinned_sources": list(includes),
                    "excluded_sources": list(excludes),
                }
            ),
        }

    def _resolve_source_reference(
        self,
        value: str,
        candidates: Iterable[PathCandidate],
        critical_path: Mapping[str, Any],
    ) -> str:
        normalized = value.strip()
        if not normalized:
            raise CriticalPathInputError("source references cannot be empty")
        candidate_list = list(candidates)
        by_key = {item.source_key: item for item in candidate_list}
        keys_by_casefold = {key.casefold(): key for key in by_key}
        if normalized.casefold() in keys_by_casefold:
            return keys_by_casefold[normalized.casefold()]
        upper = normalized.upper()
        matches = [
            item.source_key for item in candidate_list if item.source_id == upper
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            primary = [key for key in matches if not key.startswith("verification:")]
            if len(primary) == 1:
                return primary[0]
            raise CriticalPathInputError(
                f"source {upper} is ambiguous; use a canonical source key"
            )
        if CP_ID_PATTERN.fullmatch(upper):
            for item in [
                *critical_path.get("items", []),
                *critical_path.get("history", []),
            ]:
                if item["id"] == upper:
                    return item["source_key"]
        raise CriticalPathInputError(f"source {value} was not found or is inactive")

    def _manual_control_warnings(
        self,
        state: CanonicalState,
        includes: Iterable[str],
        excludes: Iterable[str],
        by_key: Mapping[str, PathCandidate],
        critical_path: Mapping[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        historical_keys = {
            item.get("source_key") for item in critical_path.get("history", [])
        }
        for source_key in includes:
            if source_key not in by_key:
                qualifier = (
                    "completed or inactive"
                    if source_key in historical_keys
                    else "missing or inactive"
                )
                warnings.append(f"Pinned source {source_key} is {qualifier}.")
        for source_key in excludes:
            if source_key not in by_key:
                warnings.append(f"Excluded source {source_key} is missing or inactive.")
        return warnings

    def _source_record(
        self, state: CanonicalState, item: Mapping[str, Any]
    ) -> StateObject | None:
        source_id = item["source_id"]
        if item["type"] == "issue":
            return copy.deepcopy(
                next(
                    (
                        value
                        for value in state["issues"]["issues"]
                        if value["id"] == source_id
                    ),
                    None,
                )
            )
        if item["type"] == "decision":
            return copy.deepcopy(
                next(
                    (
                        value
                        for value in state["decisions"]["decisions"]
                        if value["id"] == source_id
                    ),
                    None,
                )
            )
        if source_id and source_id.startswith("MC-"):
            for index, value in enumerate(
                state["milestone"]["criteria_results"], start=1
            ):
                if _criterion_id(value, index) == source_id:
                    return copy.deepcopy(value)
        return None

    @staticmethod
    def _typed_item(item: Mapping[str, Any]) -> PathItem:
        return PathItem(
            id=item["id"],
            type=item["type"],
            source_id=item["source_id"],
            source_key=item["source_key"],
            title=item["title"],
            description=item["description"],
            reason=item["reason"],
            milestone_impact=item["milestone_impact"],
            priority_tier=item["priority_tier"],
            dependencies=tuple(item["dependencies"]),
            status=item["status"],
            completion_condition=item["completion_condition"],
            recommended_action=item["recommended_action"],
            owner=item["owner"],
            evidence_required=tuple(item["evidence_required"]),
            pinned=item["pinned"],
            manual=item["manual"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            source_status=item["source_status"],
            evidence_state=item["evidence_state"],
        )


def dataclass_replace_dependency(
    candidate: PathCandidate, dependency_key: str
) -> PathCandidate:
    """Return a candidate with one additional dependency without importing replace."""

    values = asdict(candidate)
    values["dependency_keys"] = tuple(
        dict.fromkeys((*candidate.dependency_keys, dependency_key))
    )
    values["evidence_required"] = tuple(candidate.evidence_required)
    values["sort_hint"] = tuple(candidate.sort_hint)
    return PathCandidate(**values)
