"""Decision-domain operations backed by canonical PGS state."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .models import MutationResult
from .reporting import render_report_contents
from .state import StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

DECISION_ID_PATTERN = re.compile(r"^DEC-(\d{3,})$")
OPTION_ID_PATTERN = re.compile(r"^OPT-[A-Z0-9][A-Z0-9-]*$")
ISSUE_ID_PATTERN = re.compile(r"^ISS-[0-9]{3,}$")
EVIDENCE_ID_PATTERN = re.compile(r"^EVD-[0-9]{3,}$")
PHASES = (
    "intake",
    "clarify",
    "prototype-plan",
    "prototype-build",
    "evaluate",
    "iterate",
    "vertical-slice-decision",
    "vertical-slice",
    "production",
)
URGENCIES = ("low", "medium", "high", "blocking")
STATUSES = (
    "open",
    "ready",
    "blocked",
    "resolved",
    "deferred",
    "rejected",
    "superseded",
)
PENDING_STATUSES = {"open", "ready", "blocked", "deferred"}
HISTORICAL_STATUSES = {"resolved", "rejected", "superseded"}
CREATE_STATUSES = {"open", "ready", "blocked"}
URGENCY_PRIORITY = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
ALLOWED_TRANSITIONS = {
    "open": {"ready", "blocked", "deferred", "rejected"},
    "ready": {"open", "blocked", "deferred", "rejected"},
    "blocked": {"open", "ready", "deferred", "rejected"},
    "deferred": {"open", "ready", "rejected"},
    "resolved": {"open"},
    "rejected": {"open"},
    "superseded": set(),
}

Clock = Callable[[], datetime]


class DecisionError(ValueError):
    """Base class for actionable decision-domain errors."""


class DecisionInputError(DecisionError):
    """Decision input is missing or invalid."""


class DecisionNotFoundError(DecisionError):
    """The requested decision does not exist."""


@dataclass(frozen=True, slots=True)
class DecisionOption:
    id: str
    label: str
    description: str
    benefits: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    effort: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionCreateRequest:
    question: str
    context: str
    options: tuple[DecisionOption, ...]
    recommended_option: str
    recommendation_reason: str
    phase: str | None = None
    milestone: str | None = None
    urgency: str = "medium"
    decision_owner: str = "user"
    decision_required_by: str | None = None
    affected_issues: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    trade_offs: tuple[str, ...] = ()
    revisit_condition: str | None = None
    status: str = "open"


@dataclass(frozen=True, slots=True)
class DecisionPatch:
    values: Mapping[str, Any] = field(default_factory=dict)
    add_trade_offs: tuple[str, ...] = ()
    remove_trade_offs: tuple[str, ...] = ()
    add_issues: tuple[str, ...] = ()
    remove_issues: tuple[str, ...] = ()
    add_evidence: tuple[str, ...] = ()
    remove_evidence: tuple[str, ...] = ()
    add_options: tuple[DecisionOption, ...] = ()
    update_options: tuple[DecisionOption, ...] = ()
    remove_options: tuple[str, ...] = ()
    supersedes: str | None = None

    @property
    def requested(self) -> bool:
        return bool(
            self.values
            or self.add_trade_offs
            or self.remove_trade_offs
            or self.add_issues
            or self.remove_issues
            or self.add_evidence
            or self.remove_evidence
            or self.add_options
            or self.update_options
            or self.remove_options
            or self.supersedes is not None
        )


@dataclass(frozen=True, slots=True)
class DecisionResolution:
    option_id: str | None = None
    custom_decision: str | None = None
    reason: str = ""
    consequences: tuple[str, ...] = ()
    follow_up_actions: tuple[str, ...] = ()
    revisit_condition: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = False) -> str | None:
    normalized = value.strip() if value is not None else ""
    if required and not normalized:
        raise DecisionInputError(f"{field_name} cannot be empty")
    return normalized or None


def _enum(value: str, allowed: Iterable[str], *, field_name: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    if normalized not in allowed:
        raise DecisionInputError(
            f"invalid {field_name} '{value}'; expected one of: {', '.join(allowed)}"
        )
    return normalized


def _deduplicate_text(values: Iterable[str], *, field_name: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise DecisionInputError(f"{field_name} values cannot be empty")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _canonical_id(value: str, pattern: re.Pattern[str], label: str) -> str:
    normalized = value.strip().upper()
    if not pattern.fullmatch(normalized):
        example = {
            "decision": "DEC-0001",
            "option": "OPT-A",
            "issue": "ISS-0001",
            "evidence": "EVD-0001",
        }[label]
        raise DecisionInputError(
            f"invalid {label} ID '{value}'; expected a value such as {example}"
        )
    return normalized


def _decision_id(value: str) -> str:
    return _canonical_id(value, DECISION_ID_PATTERN, "decision")


def _option_id(value: str) -> str:
    return _canonical_id(value, OPTION_ID_PATTERN, "option")


def _issue_id(value: str) -> str:
    return _canonical_id(value, ISSUE_ID_PATTERN, "issue")


def _evidence_id(value: str) -> str:
    return _canonical_id(value, EVIDENCE_ID_PATTERN, "evidence")


def _deduplicate_ids(
    values: Iterable[str], normalizer: Callable[[str], str]
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalizer(value)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _date(value: str | None) -> str | None:
    normalized = _text(value, field_name="required-by date")
    if normalized is None:
        return None
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise DecisionInputError(
            f"invalid required-by date '{value}'; use YYYY-MM-DD"
        ) from exc
    return normalized


def allocate_decision_id(decisions: Iterable[Mapping[str, Any]]) -> str:
    highest = 0
    for record in decisions:
        match = DECISION_ID_PATTERN.fullmatch(str(record.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"DEC-{highest + 1:04d}"


def _find_decision(decisions: list[StateObject], decision_id: str) -> StateObject:
    canonical = _decision_id(decision_id)
    for decision in decisions:
        if decision["id"] == canonical:
            return decision
    raise DecisionNotFoundError(
        f"decision {canonical} was not found; run 'studio decision list'"
    )


def recommendation_support(
    decision: Mapping[str, Any], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Derive support from active evidence without persisting a second score."""

    active = [
        evidence_by_id[reference]
        for reference in decision["supporting_evidence"]
        if reference in evidence_by_id
        and evidence_by_id[reference]["status"] == "active"
    ]
    active_ids = {item["id"] for item in active}
    conflicted = any(
        limitation.casefold().startswith("conflicts with ")
        and limitation.split()[-1].upper() in active_ids
        for item in active
        for limitation in item["limitations"]
    )
    if conflicted:
        level = "conflicted"
    elif any(item["classification"] == "observed" for item in active):
        level = "strong"
    elif len(active) >= 2:
        level = "moderate"
    elif active:
        level = "weak"
    else:
        level = "unsupported"
    return {
        "level": level,
        "active_evidence": [item["id"] for item in active],
        "classifications": {
            classification: sum(
                item["classification"] == classification for item in active
            )
            for classification in (
                "observed",
                "user-reported",
                "inferred",
                "unknown",
            )
        },
    }


class DecisionService:
    """Create, query, update, and resolve decisions without CLI presentation."""

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

    def preview_decision(self, request: DecisionCreateRequest) -> StateObject:
        state = self.repository.load_all()
        return self._with_support(self._build_decision(state, request))

    def create_decision(
        self, request: DecisionCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="decision.add",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            decision = self._build_decision(state, request)
            state["decisions"]["decisions"].append(decision)
            transaction.set_decisions(state["decisions"])
            warnings = self._evidence_warnings(state, decision)
            return transaction.commit(
                warnings=warnings,
                changed_fields={"decision": {"old": None, "new": decision["id"]}},
                details={
                    "decision": self._with_support(decision, state),
                    "recommended_next_workflow": "/next-step",
                },
            )

    def get_decision(self, decision_id: str) -> StateObject:
        state = self.repository.load_all()
        record = copy.deepcopy(
            _find_decision(state["decisions"]["decisions"], decision_id)
        )
        record["superseded_by"] = sorted(
            item["id"]
            for item in state["decisions"]["decisions"]
            if item["supersedes"] == record["id"]
        )
        return self._with_support(record, state)

    def list_decisions(
        self,
        *,
        status: str | None = None,
        urgency: str | None = None,
        owner: str | None = None,
        phase: str | None = None,
        issue_id: str | None = None,
        evidence_id: str | None = None,
        pending: bool = False,
        resolved: bool = False,
        include_all: bool = False,
    ) -> list[StateObject]:
        state = self.repository.load_all()
        if status is not None:
            status = _enum(status, STATUSES, field_name="status")
        if urgency is not None:
            urgency = _enum(urgency, URGENCIES, field_name="urgency")
        if phase is not None:
            phase = _enum(phase, PHASES, field_name="phase")
        normalized_owner = (
            _text(owner, field_name="owner", required=True) if owner else None
        )
        canonical_issue = _issue_id(issue_id) if issue_id else None
        canonical_evidence = _evidence_id(evidence_id) if evidence_id else None
        if canonical_issue and canonical_issue not in {
            item["id"] for item in state["issues"]["issues"]
        }:
            raise DecisionInputError(
                f"referenced issue {canonical_issue} does not exist"
            )
        if canonical_evidence and canonical_evidence not in {
            item["id"] for item in state["evidence"]["evidence"]
        }:
            raise DecisionInputError(
                f"referenced evidence {canonical_evidence} does not exist"
            )

        matches: list[StateObject] = []
        for record in state["decisions"]["decisions"]:
            if (
                not include_all
                and status is None
                and not resolved
                and record["status"] not in PENDING_STATUSES
            ):
                continue
            if (
                not include_all
                and status is None
                and not resolved
                and record["status"] == "deferred"
                and record["milestone"] != state["project"]["current_milestone"]
                and record["decision_required_by"] is None
                and record["revisit_condition"] is None
            ):
                continue
            if pending and record["status"] not in PENDING_STATUSES:
                continue
            if resolved and record["status"] != "resolved":
                continue
            if status is not None and record["status"] != status:
                continue
            if urgency is not None and record["urgency"] != urgency:
                continue
            if (
                normalized_owner is not None
                and record["decision_owner"] != normalized_owner
            ):
                continue
            if phase is not None and record["phase"] != phase:
                continue
            if canonical_issue and canonical_issue not in record["affected_issues"]:
                continue
            if (
                canonical_evidence
                and canonical_evidence not in record["supporting_evidence"]
            ):
                continue
            matches.append(self._with_support(copy.deepcopy(record), state))
        current_milestone = state["project"]["current_milestone"]
        return sorted(
            matches,
            key=lambda item: (
                URGENCY_PRIORITY[item["urgency"]],
                item["decision_required_by"] or "9999-12-31",
                item["milestone"] != current_milestone,
                item["created_at"],
                item["id"],
            ),
        )

    def update_decision(
        self,
        decision_id: str,
        patch: DecisionPatch,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        if not patch.requested:
            raise DecisionInputError("at least one decision update must be requested")
        canonical = _decision_id(decision_id)
        warnings: list[str] = []
        with StateTransaction(
            self.root,
            operation="decision.update",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            decisions = state["decisions"]["decisions"]
            record = _find_decision(decisions, canonical)
            before = copy.deepcopy(record)
            old_status = record["status"]

            self._apply_values(record, patch.values)
            if record["status"] == "resolved" and old_status != "resolved":
                raise DecisionInputError(
                    "use 'studio decision resolve' to resolve a decision"
                )
            self._validate_transition(old_status, record["status"])
            if old_status == "resolved" and record["status"] == "open":
                self._clear_active_resolution(record)
            self._apply_list_changes(
                record,
                "trade_offs",
                patch.add_trade_offs,
                patch.remove_trade_offs,
                warnings,
                normalizer=lambda value: _text(
                    value, field_name="trade-off", required=True
                ),
            )
            self._apply_reference_changes(state, record, patch, warnings)
            self._apply_option_changes(record, patch, warnings)
            superseded_record = self._apply_supersession(
                decisions, record, patch.supersedes
            )
            self._validate_decision(state, record)
            self._validate_acyclic(decisions)

            changed_fields = self._changes(before, record)
            timestamp = _timestamp(self.clock)
            if changed_fields:
                record["updated_at"] = timestamp
                changed_fields["updated_at"] = {
                    "old": before["updated_at"],
                    "new": timestamp,
                }
            if superseded_record is not None:
                changed_fields[f"superseded:{superseded_record['id']}"] = {
                    "old": superseded_record.pop("_previous_status"),
                    "new": "superseded",
                }
                superseded_record["updated_at"] = timestamp
            changed = bool(changed_fields)
            if changed:
                transaction.set_decisions(state["decisions"])
            warnings.extend(self._evidence_warnings(state, record))
            return transaction.commit(
                warnings=warnings,
                changed_fields=changed_fields,
                details={
                    "decision": self._with_support(record, state),
                    "recommended_next_workflow": "/next-step",
                    "no_op": not changed,
                },
            )

    def resolve_decision(
        self,
        decision_id: str,
        resolution: DecisionResolution,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        canonical = _decision_id(decision_id)
        with StateTransaction(
            self.root,
            operation="decision.resolve",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            record = _find_decision(state["decisions"]["decisions"], canonical)
            if record["status"] == "resolved":
                raise DecisionInputError(
                    f"{canonical} is already resolved; reopen it before resolving again"
                )
            if record["status"] in {"rejected", "superseded"}:
                raise DecisionInputError(
                    f"{canonical} must be reopened before it can be resolved"
                )
            if (resolution.option_id is None) == (resolution.custom_decision is None):
                raise DecisionInputError(
                    "provide exactly one of --option or --custom-decision"
                )
            reason = _text(
                resolution.reason, field_name="resolution reason", required=True
            )
            option_id: str | None = None
            followed = False
            if resolution.option_id is not None:
                option_id = _option_id(resolution.option_id)
                option = next(
                    (item for item in record["options"] if item["id"] == option_id),
                    None,
                )
                if option is None:
                    raise DecisionInputError(
                        f"option {option_id} does not exist on {canonical}"
                    )
                final_decision = f"{option_id} — {option['label']}"
                followed = option_id == record["recommended_option"]
            else:
                final_decision = _text(
                    resolution.custom_decision,
                    field_name="custom decision",
                    required=True,
                )

            before = copy.deepcopy(record)
            timestamp = _timestamp(self.clock)
            record.update(
                {
                    "status": "resolved",
                    "final_decision": final_decision,
                    "final_option_id": option_id,
                    "decision_reason": reason,
                    "consequences": _deduplicate_text(
                        resolution.consequences, field_name="consequence"
                    ),
                    "follow_up_actions": _deduplicate_text(
                        resolution.follow_up_actions, field_name="follow-up"
                    ),
                    "revisit_condition": _text(
                        resolution.revisit_condition,
                        field_name="revisit condition",
                    )
                    if resolution.revisit_condition is not None
                    else record["revisit_condition"],
                    "recommendation_followed": followed,
                    "resolved_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            record["resolution_history"].append(self._resolution_snapshot(record))
            self._validate_decision(state, record)
            changed_fields = self._changes(before, record, include_updated=True)
            transaction.set_decisions(state["decisions"])
            return transaction.commit(
                warnings=self._evidence_warnings(state, record),
                changed_fields=changed_fields,
                details={
                    "decision": self._with_support(record, state),
                    "recommended_next_workflow": "/iterate",
                },
            )

    def _build_decision(
        self, state: dict[str, StateObject], request: DecisionCreateRequest
    ) -> StateObject:
        project = state["project"]
        timestamp = _timestamp(self.clock)
        options = [self._normalize_option(item) for item in request.options]
        record = {
            "id": allocate_decision_id(state["decisions"]["decisions"]),
            "question": _text(request.question, field_name="question", required=True),
            "context": _text(request.context, field_name="context", required=True),
            "phase": _enum(
                request.phase or project["current_phase"],
                PHASES,
                field_name="phase",
            ),
            "milestone": _text(
                request.milestone or project["current_milestone"],
                field_name="milestone",
                required=True,
            ),
            "urgency": _enum(request.urgency, URGENCIES, field_name="urgency"),
            "status": _enum(request.status, CREATE_STATUSES, field_name="status"),
            "options": options,
            "recommended_option": _option_id(request.recommended_option),
            "recommendation_reason": _text(
                request.recommendation_reason,
                field_name="recommendation reason",
                required=True,
            ),
            "trade_offs": _deduplicate_text(request.trade_offs, field_name="trade-off"),
            "affected_issues": _deduplicate_ids(request.affected_issues, _issue_id),
            "supporting_evidence": _deduplicate_ids(
                request.supporting_evidence, _evidence_id
            ),
            "decision_owner": _text(
                request.decision_owner, field_name="decision owner", required=True
            ),
            "decision_required_by": _date(request.decision_required_by),
            "final_decision": None,
            "final_option_id": None,
            "decision_reason": None,
            "consequences": [],
            "follow_up_actions": [],
            "revisit_condition": _text(
                request.revisit_condition, field_name="revisit condition"
            ),
            "recommendation_followed": None,
            "resolved_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "supersedes": None,
            "resolution_history": [],
        }
        self._validate_decision(state, record)
        return record

    def _normalize_option(self, option: DecisionOption) -> StateObject:
        return {
            "id": _option_id(option.id),
            "label": _text(option.label, field_name="option label", required=True),
            "description": _text(
                option.description, field_name="option description", required=True
            ),
            "benefits": _deduplicate_text(option.benefits, field_name="benefit"),
            "risks": _deduplicate_text(option.risks, field_name="risk"),
            "effort": _text(option.effort, field_name="option effort"),
        }

    def _validate_decision(
        self, state: dict[str, StateObject], record: Mapping[str, Any]
    ) -> None:
        options = record["options"]
        option_ids = [item["id"] for item in options]
        if len(option_ids) != len(set(option_ids)):
            raise DecisionInputError("option IDs must be unique")
        labels = [item["label"].casefold() for item in options]
        if len(labels) != len(set(labels)):
            raise DecisionInputError("option labels must be unique")
        if record["recommended_option"] not in option_ids:
            raise DecisionInputError(
                f"recommended option {record['recommended_option']} does not exist"
            )
        if not 2 <= len(options) <= 6:
            raise DecisionInputError(
                "a decision must contain between two and six options"
            )
        if (
            record["final_option_id"] is not None
            and record["final_option_id"] not in option_ids
        ):
            raise DecisionInputError(
                f"final option {record['final_option_id']} does not exist"
            )
        issue_ids = {item["id"] for item in state["issues"]["issues"]}
        evidence_ids = {item["id"] for item in state["evidence"]["evidence"]}
        for issue_id in record["affected_issues"]:
            if issue_id not in issue_ids:
                raise DecisionInputError(f"referenced issue {issue_id} does not exist")
        for evidence_id in record["supporting_evidence"]:
            if evidence_id not in evidence_ids:
                raise DecisionInputError(
                    f"referenced evidence {evidence_id} does not exist"
                )
        if record["status"] == "resolved":
            if not all(
                (
                    record["final_decision"],
                    record["decision_reason"],
                    record["resolved_at"],
                )
            ):
                raise DecisionInputError(
                    "resolved decisions require a final decision, reason, and timestamp"
                )
        elif record["status"] in PENDING_STATUSES and not record["decision_owner"]:
            raise DecisionInputError(
                "decision owner is required while user action may be pending"
            )

    def _apply_values(self, record: StateObject, values: Mapping[str, Any]) -> None:
        required_text = {
            "question",
            "context",
            "milestone",
            "recommendation_reason",
            "decision_owner",
        }
        optional_text = {"revisit_condition"}
        enum_fields = {
            "phase": PHASES,
            "urgency": URGENCIES,
            "status": STATUSES,
        }
        for field_name, value in values.items():
            if field_name in required_text:
                record[field_name] = _text(
                    value,
                    field_name=field_name.replace("_", " "),
                    required=True,
                )
            elif field_name in optional_text:
                record[field_name] = _text(
                    value, field_name=field_name.replace("_", " ")
                )
            elif field_name in enum_fields:
                record[field_name] = _enum(
                    value, enum_fields[field_name], field_name=field_name
                )
            elif field_name == "recommended_option":
                record[field_name] = _option_id(value)
            elif field_name == "decision_required_by":
                record[field_name] = _date(value)
            else:
                raise DecisionInputError(f"unsupported decision field '{field_name}'")

    def _apply_reference_changes(
        self,
        state: dict[str, StateObject],
        record: StateObject,
        patch: DecisionPatch,
        warnings: list[str],
    ) -> None:
        known_issues = {item["id"] for item in state["issues"]["issues"]}
        known_evidence = {item["id"] for item in state["evidence"]["evidence"]}
        self._apply_list_changes(
            record,
            "affected_issues",
            patch.add_issues,
            patch.remove_issues,
            warnings,
            normalizer=_issue_id,
            known=known_issues,
            missing_label="issue",
        )
        self._apply_list_changes(
            record,
            "supporting_evidence",
            patch.add_evidence,
            patch.remove_evidence,
            warnings,
            normalizer=_evidence_id,
            known=known_evidence,
            missing_label="evidence",
        )

    @staticmethod
    def _apply_list_changes(
        record: StateObject,
        field_name: str,
        additions: Iterable[str],
        removals: Iterable[str],
        warnings: list[str],
        *,
        normalizer: Callable[[str], Any],
        known: set[str] | None = None,
        missing_label: str = "value",
    ) -> None:
        current = list(record[field_name])
        normalized_additions = []
        for value in additions:
            normalized = normalizer(value)
            if normalized not in normalized_additions:
                normalized_additions.append(normalized)
        normalized_removals = []
        for value in removals:
            normalized = normalizer(value)
            if normalized not in normalized_removals:
                normalized_removals.append(normalized)
        for value in (*normalized_additions, *normalized_removals):
            if known is not None and value not in known:
                raise DecisionInputError(
                    f"referenced {missing_label} {value} does not exist"
                )
        for value in normalized_additions:
            if value in current:
                warnings.append(f"{value} is already recorded")
            else:
                current.append(value)
        for value in normalized_removals:
            if value in current:
                current.remove(value)
            else:
                warnings.append(f"{value} is not recorded")
        record[field_name] = current

    def _apply_option_changes(
        self,
        record: StateObject,
        patch: DecisionPatch,
        warnings: list[str],
    ) -> None:
        options = list(record["options"])
        by_id = {item["id"]: item for item in options}
        for option in patch.add_options:
            normalized = self._normalize_option(option)
            if normalized["id"] in by_id:
                raise DecisionInputError(
                    f"option {normalized['id']} already exists; use --update-option"
                )
            options.append(normalized)
            by_id[normalized["id"]] = normalized
        for option in patch.update_options:
            normalized = self._normalize_option(option)
            existing = by_id.get(normalized["id"])
            if existing is None:
                raise DecisionInputError(
                    f"option {normalized['id']} does not exist; use --add-option"
                )
            if existing == normalized:
                warnings.append(f"option {normalized['id']} is unchanged")
            else:
                existing.update(normalized)
        for raw_id in _deduplicate_ids(patch.remove_options, _option_id):
            if raw_id not in by_id:
                warnings.append(f"option {raw_id} does not exist")
                continue
            options.remove(by_id[raw_id])
            del by_id[raw_id]
        record["options"] = options

    def _apply_supersession(
        self,
        decisions: list[StateObject],
        record: StateObject,
        requested: str | None,
    ) -> StateObject | None:
        if requested is None:
            return None
        target_id = _decision_id(requested)
        if target_id == record["id"]:
            raise DecisionInputError("a decision cannot supersede itself")
        try:
            target = _find_decision(decisions, target_id)
        except DecisionNotFoundError as exc:
            raise DecisionInputError(
                f"superseded decision {target_id} does not exist"
            ) from exc
        if record["supersedes"] not in {None, target_id}:
            raise DecisionInputError(
                "an existing supersedes relationship cannot be replaced in B4"
            )
        if record["status"] not in PENDING_STATUSES:
            raise DecisionInputError(
                "only an unresolved decision can supersede another decision"
            )
        other = [
            item["id"]
            for item in decisions
            if item["id"] != record["id"] and item["supersedes"] == target_id
        ]
        if other:
            raise DecisionInputError(
                f"{target_id} is already superseded by {', '.join(other)}"
            )
        record["supersedes"] = target_id
        if target["status"] == "superseded":
            return None
        target["_previous_status"] = target["status"]
        target["status"] = "superseded"
        return target

    @staticmethod
    def _validate_transition(old_status: str, new_status: str) -> None:
        if old_status == new_status:
            return
        if new_status == "resolved":
            return
        if new_status not in ALLOWED_TRANSITIONS[old_status]:
            raise DecisionInputError(
                f"invalid decision transition: {old_status} -> {new_status}"
            )

    @staticmethod
    def _validate_acyclic(decisions: list[StateObject]) -> None:
        graph = {
            item["id"]: item["supersedes"]
            for item in decisions
            if item["supersedes"] is not None
        }
        for start in graph:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise DecisionInputError(
                        f"circular decision supersession detected at {current}"
                    )
                seen.add(current)
                current = graph.get(current)

    @staticmethod
    def _resolution_snapshot(record: Mapping[str, Any]) -> StateObject:
        return {
            "final_decision": record["final_decision"],
            "final_option_id": record["final_option_id"],
            "decision_reason": record["decision_reason"],
            "consequences": copy.deepcopy(record["consequences"]),
            "follow_up_actions": copy.deepcopy(record["follow_up_actions"]),
            "revisit_condition": record["revisit_condition"],
            "recommendation_followed": record["recommendation_followed"],
            "resolved_at": record["resolved_at"],
        }

    @staticmethod
    def _clear_active_resolution(record: StateObject) -> None:
        record.update(
            {
                "final_decision": None,
                "final_option_id": None,
                "decision_reason": None,
                "consequences": [],
                "follow_up_actions": [],
                "recommendation_followed": None,
                "resolved_at": None,
            }
        )

    def _with_support(
        self,
        decision: Mapping[str, Any],
        state: dict[str, StateObject] | None = None,
    ) -> StateObject:
        current_state = state or self.repository.load_all()
        evidence_by_id = {
            item["id"]: item for item in current_state["evidence"]["evidence"]
        }
        result = copy.deepcopy(dict(decision))
        result["evidence_support"] = recommendation_support(decision, evidence_by_id)
        return result

    @staticmethod
    def _evidence_warnings(
        state: dict[str, StateObject], decision: Mapping[str, Any]
    ) -> list[str]:
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        inactive = [
            reference
            for reference in decision["supporting_evidence"]
            if evidence_by_id[reference]["status"] != "active"
        ]
        return (
            [
                (
                    "inactive evidence is retained for traceability but does not "
                    f"count as current support: {', '.join(inactive)}"
                )
            ]
            if inactive
            else []
        )

    @staticmethod
    def _changes(
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        include_updated: bool = False,
    ) -> dict[str, dict[str, Any]]:
        ignored = set() if include_updated else {"updated_at"}
        return {
            key: {"old": copy.deepcopy(before[key]), "new": copy.deepcopy(value)}
            for key, value in after.items()
            if key not in ignored
            and not key.startswith("_")
            and before.get(key) != value
        }
