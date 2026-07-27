"""Transactional milestone-criterion management and explicit evaluation."""

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

CRITERION_ID_PATTERN = re.compile(r"^MC-(\d{3,})$")
SUPPORT_STATUSES = {
    "unsupported",
    "partially-supported",
    "verified",
    "contradicted",
}
NON_RUNTIME_TERMS = {
    "document review",
    "documentation review",
    "source review",
    "spec review",
    "static inspection",
    "approval review",
}
PLAYER_BEHAVIOR_TERMS = {
    "player",
    "tester",
    "playtest",
    "unaided",
    "without assistance",
    "understand",
    "complete the loop",
}


class CriterionError(ValueError):
    """Base class for criterion-domain errors."""


class CriterionInputError(CriterionError):
    """Criterion input or evaluation is invalid."""


class CriterionNotFoundError(CriterionError):
    """A requested criterion does not exist."""


@dataclass(frozen=True, slots=True)
class CriterionCreateRequest:
    description: str
    required: bool
    completion_condition: str
    milestone: str | None = None
    verification_method: str | None = None
    related_issues: tuple[str, ...] = ()
    related_decisions: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CriterionPatch:
    values: Mapping[str, Any] = field(default_factory=dict)
    add_issues: tuple[str, ...] = ()
    remove_issues: tuple[str, ...] = ()
    add_decisions: tuple[str, ...] = ()
    remove_decisions: tuple[str, ...] = ()
    add_evidence: tuple[str, ...] = ()
    remove_evidence: tuple[str, ...] = ()

    @property
    def requested(self) -> bool:
        return bool(
            self.values
            or self.add_issues
            or self.remove_issues
            or self.add_decisions
            or self.remove_decisions
            or self.add_evidence
            or self.remove_evidence
        )


@dataclass(frozen=True, slots=True)
class CriterionEvaluation:
    support_status: str
    reason: str
    evidence: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CriterionEvaluationHistoryEntry:
    support_status: str
    reason: str
    evidence_snapshot: tuple[Mapping[str, str], ...]
    issue_references: tuple[str, ...]
    decision_references: tuple[str, ...]
    limitations: tuple[str, ...]
    evaluated_at: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise CriterionInputError(f"{field_name} cannot be empty")
        return None
    normalized = value.strip()
    if not normalized:
        if required:
            raise CriterionInputError(f"{field_name} cannot be empty")
        return None
    return normalized


def _canonical_id(value: str, prefix: str, width: int = 3) -> str:
    canonical = value.strip().upper()
    pattern = re.compile(rf"^{prefix}-\d{{{width},}}$")
    if not pattern.fullmatch(canonical):
        raise CriterionInputError(
            f"invalid {prefix} ID '{value}'; expected {prefix}-"
            + ("001" if width == 3 else "0001")
        )
    return canonical


def _deduplicate_ids(
    values: Iterable[str], prefix: str, *, field_name: str
) -> list[str]:
    result: list[str] = []
    for value in values:
        canonical = _canonical_id(value, prefix)
        if canonical in result:
            raise CriterionInputError(f"duplicate {field_name} reference {canonical}")
        result.append(canonical)
    return sorted(result)


def allocate_criterion_id(criteria: Iterable[Mapping[str, Any]]) -> str:
    highest = 0
    for criterion in criteria:
        match = CRITERION_ID_PATTERN.fullmatch(str(criterion.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"MC-{highest + 1:03d}"


def find_criterion(criteria: Iterable[StateObject], criterion_id: str) -> StateObject:
    canonical = criterion_id.strip().upper()
    if not CRITERION_ID_PATTERN.fullmatch(canonical):
        raise CriterionInputError(
            f"invalid criterion ID '{criterion_id}'; expected MC-001"
        )
    for criterion in criteria:
        if criterion["id"] == canonical:
            return criterion
    raise CriterionNotFoundError(
        f"criterion {canonical} was not found; run 'studio criterion list'"
    )


def _mark_path_stale(critical_path: StateObject, reason: str) -> None:
    reasons = list(critical_path.get("freshness", {}).get("reasons", []))
    reasons.append(reason)
    critical_path["freshness"] = {
        "status": "stale",
        "reasons": list(dict.fromkeys(reasons)),
    }


class CriterionService:
    """Create, query, update, evaluate, and retire milestone criteria."""

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

    def allocate_criterion_id(
        self, criteria: Iterable[Mapping[str, Any]] | None = None
    ) -> str:
        source = (
            criteria
            if criteria is not None
            else self.repository.load_milestone()["criteria_results"]
        )
        return allocate_criterion_id(source)

    def preview_criterion(self, request: CriterionCreateRequest) -> StateObject:
        state = self.repository.load_all()
        return self._build_criterion(state, request, _timestamp(self.clock))

    def create_criterion(
        self, request: CriterionCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="criterion.add",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            criterion = self._build_criterion(state, request, _timestamp(self.clock))
            state["milestone"]["criteria_results"].append(criterion)
            transaction.set_milestone(state["milestone"])
            _mark_path_stale(
                state["critical_path"],
                f"{criterion['id']} was added to milestone criteria.",
            )
            transaction.set_critical_path(state["critical_path"])
            warning = (
                ()
                if criterion["required"]
                else ("Optional unsupported criteria are not selected by default.",)
            )
            return transaction.commit(
                warnings=warning,
                changed_fields={"criterion": {"old": None, "new": criterion["id"]}},
                details={
                    "criterion": copy.deepcopy(criterion),
                    "path_stale": True,
                    "path_impact": "stale",
                    "recommended_next_command": "studio path calculate",
                },
            )

    def get_criterion(self, criterion_id: str) -> StateObject:
        state = self.repository.load_all()
        criterion = copy.deepcopy(
            find_criterion(state["milestone"]["criteria_results"], criterion_id)
        )
        return self._with_derived_state(state, criterion)

    def list_criteria(
        self,
        *,
        milestone: str | None = None,
        required: bool | None = None,
        support_status: str | None = None,
        lifecycle_status: str | None = None,
        include_all: bool = False,
    ) -> list[StateObject]:
        state = self.repository.load_all()
        selected_milestone = (
            _text(milestone, field_name="milestone")
            if milestone is not None
            else state["project"]["current_milestone"]
        )
        if support_status is not None and support_status not in SUPPORT_STATUSES:
            raise CriterionInputError(
                "support status must be unsupported, partially-supported, "
                "verified, or contradicted"
            )
        if lifecycle_status is not None and lifecycle_status not in {
            "active",
            "retired",
        }:
            raise CriterionInputError("lifecycle status must be active or retired")
        matches = []
        for criterion in state["milestone"]["criteria_results"]:
            if criterion["milestone"] != selected_milestone:
                continue
            if (
                not include_all
                and lifecycle_status is None
                and criterion["lifecycle_status"] != "active"
            ):
                continue
            if required is not None and criterion["required"] != required:
                continue
            if (
                support_status is not None
                and criterion["support_status"] != support_status
            ):
                continue
            if (
                lifecycle_status is not None
                and criterion["lifecycle_status"] != lifecycle_status
            ):
                continue
            matches.append(self._with_derived_state(state, copy.deepcopy(criterion)))
        return sorted(
            matches,
            key=lambda item: (
                not item["required"],
                int(item["id"].split("-", 1)[1]),
            ),
        )

    def update_criterion(
        self,
        criterion_id: str,
        patch: CriterionPatch,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        if not patch.requested:
            raise CriterionInputError("at least one criterion update is required")
        warnings: list[str] = []
        with StateTransaction(
            self.root,
            operation="criterion.update",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            criterion = find_criterion(
                state["milestone"]["criteria_results"], criterion_id
            )
            if criterion["lifecycle_status"] == "retired":
                raise CriterionInputError(
                    f"{criterion['id']} is retired; criterion reactivation is "
                    "deferred beyond Phase C2"
                )
            before = copy.deepcopy(criterion)
            timestamp = _timestamp(self.clock)
            for field_name, value in patch.values.items():
                if field_name == "description":
                    criterion[field_name] = _text(value, field_name="description")
                elif field_name == "completion_condition":
                    criterion[field_name] = _text(
                        value, field_name="completion condition"
                    )
                elif field_name == "verification_method":
                    criterion[field_name] = _text(
                        value,
                        field_name="verification method",
                        required=False,
                    )
                elif field_name == "milestone":
                    new_milestone = _text(value, field_name="milestone")
                    if new_milestone != criterion["milestone"]:
                        criterion["milestone_history"].append(
                            {
                                "from": criterion["milestone"],
                                "to": new_milestone,
                                "changed_at": timestamp,
                            }
                        )
                    criterion[field_name] = new_milestone
                elif field_name == "required":
                    criterion[field_name] = bool(value)
                else:
                    raise CriterionInputError(
                        f"unsupported criterion field {field_name}"
                    )
            self._apply_references(
                state,
                criterion,
                "related_issues",
                patch.add_issues,
                patch.remove_issues,
                "ISS",
                warnings,
            )
            self._apply_references(
                state,
                criterion,
                "related_decisions",
                patch.add_decisions,
                patch.remove_decisions,
                "DEC",
                warnings,
            )
            removed_evidence = self._apply_references(
                state,
                criterion,
                "supporting_evidence",
                patch.add_evidence,
                patch.remove_evidence,
                "EVD",
                warnings,
            )
            if removed_evidence and criterion["evaluation_history"]:
                warnings.append(
                    "Evidence supporting the latest explicit evaluation was "
                    "removed; reevaluate the criterion."
                )
            changed = {
                key: {"old": before[key], "new": criterion[key]}
                for key in criterion
                if before.get(key) != criterion.get(key) and key != "updated_at"
            }
            if changed:
                criterion["updated_at"] = timestamp
                changed["updated_at"] = {
                    "old": before["updated_at"],
                    "new": timestamp,
                }
                definition_fields = {
                    "milestone",
                    "description",
                    "required",
                    "completion_condition",
                    "verification_method",
                }
                material = bool(definition_fields & set(changed))
                if criterion["evaluation_history"] and (material or removed_evidence):
                    reasons = list(criterion["evaluation_freshness"]["reasons"])
                    reasons.append(
                        "Criterion definition or current evaluation evidence changed."
                    )
                    criterion["evaluation_freshness"] = {
                        "status": "stale",
                        "reasons": list(dict.fromkeys(reasons)),
                    }
                transaction.set_milestone(state["milestone"])
                _mark_path_stale(
                    state["critical_path"],
                    f"{criterion['id']} definition or references changed.",
                )
                transaction.set_critical_path(state["critical_path"])
            else:
                material = False
            return transaction.commit(
                warnings=warnings,
                changed_fields=changed,
                details={
                    "criterion": self._with_derived_state(
                        state, copy.deepcopy(criterion)
                    ),
                    "no_op": not changed,
                    "path_stale": bool(changed),
                    "path_impact": "stale" if material else "may-be-stale",
                    "recommended_next_command": (
                        "studio path calculate" if material else "studio path check"
                    ),
                },
            )

    def evaluate_criterion(
        self,
        criterion_id: str,
        evaluation: CriterionEvaluation,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="criterion.evaluate",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            criterion = find_criterion(
                state["milestone"]["criteria_results"], criterion_id
            )
            if criterion["lifecycle_status"] != "active":
                raise CriterionInputError(
                    f"{criterion['id']} is retired and cannot be evaluated"
                )
            support = evaluation.support_status.strip().casefold()
            if support not in SUPPORT_STATUSES:
                raise CriterionInputError(
                    "support must be unsupported, partially-supported, verified, "
                    "or contradicted"
                )
            reason = _text(evaluation.reason, field_name="evaluation reason")
            evidence_ids = _deduplicate_ids(
                evaluation.evidence, "EVD", field_name="evidence"
            )
            issue_ids = _deduplicate_ids(evaluation.issues, "ISS", field_name="issue")
            decision_ids = _deduplicate_ids(
                evaluation.decisions, "DEC", field_name="decision"
            )
            limitations = self._deduplicate_text(evaluation.limitations, "limitation")
            self._validate_references(state, issue_ids, decision_ids, evidence_ids)
            evidence_by_id = {
                item["id"]: item for item in state["evidence"]["evidence"]
            }
            selected_evidence = [
                evidence_by_id[evidence_id] for evidence_id in evidence_ids
            ]
            self._validate_evaluation(
                criterion,
                support,
                reason,
                selected_evidence,
                limitations,
            )
            snapshot = [
                {
                    "id": item["id"],
                    "classification": item["classification"],
                    "status": item["status"],
                }
                for item in selected_evidence
            ]
            logical_entry = {
                "support_status": support,
                "reason": reason,
                "evidence_snapshot": snapshot,
                "issue_references": issue_ids,
                "decision_references": decision_ids,
                "limitations": limitations,
            }
            latest = (
                criterion["evaluation_history"][-1]
                if criterion["evaluation_history"]
                else None
            )
            if latest is not None:
                latest_logical = {key: latest[key] for key in logical_entry}
                if (
                    latest_logical == logical_entry
                    and criterion["evaluation_freshness"]["status"] == "current"
                ):
                    return transaction.commit(
                        details={
                            "criterion": self._with_derived_state(
                                state, copy.deepcopy(criterion)
                            ),
                            "no_op": True,
                            "path_stale": False,
                            "path_impact": "none",
                            "recommended_next_command": "studio path check",
                        }
                    )
            timestamp = _timestamp(self.clock)
            before_support = criterion["support_status"]
            entry = {**logical_entry, "evaluated_at": timestamp}
            criterion["evaluation_history"].append(entry)
            criterion.update(
                {
                    "support_status": support,
                    "supporting_evidence": evidence_ids,
                    "evaluation_reason": reason,
                    "evaluation_limitations": limitations,
                    "evaluation_freshness": {
                        "status": "current",
                        "reasons": [],
                    },
                    "evaluated_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            transaction.set_milestone(state["milestone"])
            path_changed = self._archive_satisfied_path_items(
                state, criterion, timestamp
            )
            _mark_path_stale(
                state["critical_path"],
                f"{criterion['id']} support changed to {support}.",
            )
            transaction.set_critical_path(state["critical_path"])
            warnings: list[str] = []
            if support == "unsupported" and before_support == "verified":
                warnings.append(
                    "Previous verification remains in evaluation history but is "
                    "no longer current."
                )
            return transaction.commit(
                warnings=warnings,
                changed_fields={
                    "support_status": {
                        "old": before_support,
                        "new": support,
                    },
                    "evaluation_history": {
                        "old": len(criterion["evaluation_history"]) - 1,
                        "new": len(criterion["evaluation_history"]),
                    },
                },
                details={
                    "criterion": self._with_derived_state(
                        state, copy.deepcopy(criterion)
                    ),
                    "no_op": False,
                    "path_synchronized": path_changed,
                    "path_stale": True,
                    "path_impact": "stale",
                    "recommended_next_command": "studio path calculate",
                },
            )

    def retire_criterion(
        self,
        criterion_id: str,
        reason: str,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        retirement_reason = _text(reason, field_name="retirement reason")
        with StateTransaction(
            self.root,
            operation="criterion.retire",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            criterion = find_criterion(
                state["milestone"]["criteria_results"], criterion_id
            )
            if criterion["lifecycle_status"] == "retired":
                raise CriterionInputError(f"{criterion['id']} is already retired")
            timestamp = _timestamp(self.clock)
            criterion.update(
                {
                    "lifecycle_status": "retired",
                    "retired_at": timestamp,
                    "retirement_reason": retirement_reason,
                    "updated_at": timestamp,
                }
            )
            transaction.set_milestone(state["milestone"])
            self._archive_satisfied_path_items(state, criterion, timestamp)
            _mark_path_stale(
                state["critical_path"],
                f"{criterion['id']} was retired from milestone requirements.",
            )
            transaction.set_critical_path(state["critical_path"])
            warnings = (
                (
                    f"{criterion['id']} was required; retiring it changes the milestone requirements.",
                )
                if criterion["required"]
                else ()
            )
            return transaction.commit(
                warnings=warnings,
                changed_fields={
                    "lifecycle_status": {"old": "active", "new": "retired"},
                    "retirement_reason": {
                        "old": None,
                        "new": retirement_reason,
                    },
                },
                details={
                    "criterion": copy.deepcopy(criterion),
                    "path_stale": True,
                    "path_impact": "stale",
                    "recommended_next_command": "studio path calculate",
                },
            )

    def derive_support_summary(self) -> dict[str, int]:
        records = self.list_criteria(include_all=False)
        return {
            status: sum(criterion["support_status"] == status for criterion in records)
            for status in (
                "verified",
                "partially-supported",
                "unsupported",
                "contradicted",
            )
        }

    def _build_criterion(
        self,
        state: CanonicalState,
        request: CriterionCreateRequest,
        timestamp: str,
    ) -> StateObject:
        description = _text(request.description, field_name="description")
        completion = _text(
            request.completion_condition, field_name="completion condition"
        )
        milestone = (
            _text(request.milestone, field_name="milestone")
            if request.milestone is not None
            else state["project"]["current_milestone"]
        )
        issues = _deduplicate_ids(request.related_issues, "ISS", field_name="issue")
        decisions = _deduplicate_ids(
            request.related_decisions, "DEC", field_name="decision"
        )
        evidence = _deduplicate_ids(
            request.supporting_evidence, "EVD", field_name="evidence"
        )
        self._validate_references(state, issues, decisions, evidence)
        return {
            "id": allocate_criterion_id(state["milestone"]["criteria_results"]),
            "milestone": milestone,
            "description": description,
            "required": bool(request.required),
            "lifecycle_status": "active",
            "support_status": "unsupported",
            "completion_condition": completion,
            "verification_method": _text(
                request.verification_method,
                field_name="verification method",
                required=False,
            ),
            "related_issues": issues,
            "related_decisions": decisions,
            "supporting_evidence": evidence,
            "evaluation_reason": None,
            "evaluation_limitations": [],
            "evaluation_history": [],
            "evaluation_freshness": {"status": "current", "reasons": []},
            "milestone_history": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "evaluated_at": None,
            "retired_at": None,
            "retirement_reason": None,
        }

    @staticmethod
    def _deduplicate_text(values: Iterable[str], field_name: str) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = _text(value, field_name=field_name)
            if normalized in result:
                raise CriterionInputError(f"duplicate {field_name}: {normalized}")
            result.append(normalized)
        return result

    @staticmethod
    def _validate_references(
        state: CanonicalState,
        issue_ids: Iterable[str],
        decision_ids: Iterable[str],
        evidence_ids: Iterable[str],
    ) -> None:
        known = {
            "ISS": {item["id"] for item in state["issues"]["issues"]},
            "DEC": {item["id"] for item in state["decisions"]["decisions"]},
            "EVD": {item["id"] for item in state["evidence"]["evidence"]},
        }
        for prefix, values in (
            ("ISS", issue_ids),
            ("DEC", decision_ids),
            ("EVD", evidence_ids),
        ):
            for value in values:
                if value not in known[prefix]:
                    raise CriterionInputError(
                        f"referenced {prefix} record {value} does not exist"
                    )

    def _apply_references(
        self,
        state: CanonicalState,
        criterion: StateObject,
        field_name: str,
        additions: Iterable[str],
        removals: Iterable[str],
        prefix: str,
        warnings: list[str],
    ) -> bool:
        add = _deduplicate_ids(
            additions, prefix, field_name=field_name.replace("_", " ")
        )
        remove = _deduplicate_ids(
            removals, prefix, field_name=field_name.replace("_", " ")
        )
        overlap = sorted(set(add) & set(remove))
        if overlap:
            raise CriterionInputError(
                f"cannot add and remove the same reference: {', '.join(overlap)}"
            )
        self._validate_references(
            state,
            add if prefix == "ISS" else (),
            add if prefix == "DEC" else (),
            add if prefix == "EVD" else (),
        )
        values = list(criterion[field_name])
        for value in add:
            if value not in values:
                values.append(value)
        removed = False
        for value in remove:
            if value not in values:
                warnings.append(
                    f"{value} was not linked to {criterion['id']}; nothing removed."
                )
                continue
            values.remove(value)
            removed = True
        criterion[field_name] = sorted(values)
        return removed

    @staticmethod
    def _validate_evaluation(
        criterion: Mapping[str, Any],
        support: str,
        reason: str,
        evidence: list[Mapping[str, Any]],
        limitations: list[str],
    ) -> None:
        del reason
        active = [item for item in evidence if item["status"] == "active"]
        if len(active) != len(evidence):
            inactive = sorted(
                item["id"] for item in evidence if item["status"] != "active"
            )
            raise CriterionInputError(
                "inactive evidence cannot support a current evaluation: "
                + ", ".join(inactive)
            )
        if (
            support in {"verified", "partially-supported", "contradicted"}
            and not active
        ):
            raise CriterionInputError(f"{support} evaluation requires active evidence")
        if support == "partially-supported" and not limitations:
            raise CriterionInputError(
                "partially-supported evaluation requires at least one limitation"
            )
        if support != "partially-supported" and limitations and support == "verified":
            # Verified limitations are useful context but cannot contradict completion.
            pass
        if support != "verified":
            return
        text = " ".join(
            (
                criterion["description"],
                criterion["completion_condition"],
                criterion["verification_method"] or "",
            )
        ).casefold()
        player_behavior = any(term in text for term in PLAYER_BEHAVIOR_TERMS)
        non_runtime = any(
            term in (criterion["verification_method"] or "").casefold()
            for term in NON_RUNTIME_TERMS
        )
        observed = any(item["classification"] == "observed" for item in active)
        if player_behavior and not observed:
            raise CriterionInputError(
                "player-behavior criteria require active observed evidence; "
                "inferred or user-reported evidence alone is insufficient"
            )
        if not player_behavior and not non_runtime and not observed:
            raise CriterionInputError(
                "verified evaluation requires active observed evidence unless "
                "the verification method explicitly documents a non-runtime review"
            )

    @staticmethod
    def _archive_satisfied_path_items(
        state: CanonicalState, criterion: Mapping[str, Any], timestamp: str
    ) -> bool:
        if not (
            criterion["support_status"] == "verified"
            or criterion["lifecycle_status"] == "retired"
            or not criterion["required"]
        ):
            return False
        path = state["critical_path"]
        matching = [
            item
            for item in path["items"]
            if item.get("source_id") == criterion["id"]
            and item["type"] in {"verification", "milestone-criterion"}
        ]
        if not matching:
            return False
        removed_ids = {item["id"] for item in matching}
        path["items"] = [
            item for item in path["items"] if item["id"] not in removed_ids
        ]
        for downstream in path["items"]:
            new_dependencies = [
                item for item in downstream["dependencies"] if item not in removed_ids
            ]
            if new_dependencies != downstream["dependencies"]:
                downstream["dependencies"] = new_dependencies
                downstream["dependency_origins"] = [
                    origin
                    for origin in downstream["dependency_origins"]
                    if origin["prerequisite_source_key"]
                    not in {item["source_key"] for item in matching}
                ]
                downstream["updated_at"] = timestamp
                if (
                    not new_dependencies
                    and downstream["status"] == "blocked"
                    and downstream["source_status"] != "blocked"
                ):
                    downstream["status"] = "ready"
        history_keys = {item["source_key"] for item in path.get("history", [])}
        for item in matching:
            historical = copy.deepcopy(item)
            historical["status"] = (
                "completed" if criterion["support_status"] == "verified" else "removed"
            )
            historical["updated_at"] = timestamp
            if historical["source_key"] not in history_keys:
                path["history"].append(historical)
        path["history"].sort(key=lambda item: (item["created_at"], item["id"]))
        if path["recommended_next_id"] in removed_ids:
            path["recommended_next_id"] = None
        return True

    def _with_derived_state(
        self, state: CanonicalState, criterion: StateObject
    ) -> StateObject:
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        criterion["evidence_details"] = [
            {
                "id": evidence_id,
                "classification": evidence_by_id[evidence_id]["classification"],
                "status": evidence_by_id[evidence_id]["status"],
            }
            for evidence_id in criterion["supporting_evidence"]
            if evidence_id in evidence_by_id
        ]
        active_sources = {
            item["source_key"] for item in state["critical_path"]["items"]
        }
        criterion["on_critical_path"] = any(
            source in active_sources
            for source in (
                f"milestone:{criterion['id']}",
                f"verification:{criterion['id']}:observed-support",
            )
        )
        criterion["explicitly_evaluated"] = bool(criterion["evaluation_history"])
        return criterion
