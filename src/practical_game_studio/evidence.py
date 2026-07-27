"""Evidence-domain operations backed by canonical PGS state."""

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
from .state import StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

EVIDENCE_ID_PATTERN = re.compile(r"^EVD-(\d{3,})$")
ISSUE_ID_PATTERN = re.compile(r"^ISS-(\d{3,})$")
CLASSIFICATIONS = ("observed", "user-reported", "inferred", "unknown")
SOURCE_TYPES = (
    "runtime",
    "human-playtest",
    "screenshot",
    "video",
    "telemetry",
    "test-output",
    "build-log",
    "source-review",
    "spec-review",
    "user-note",
    "external-report",
    "other",
)
SOURCE_OPTIONAL_TYPES = {
    "runtime",
    "human-playtest",
    "user-note",
    "source-review",
    "spec-review",
}
CONFIDENCES = ("low", "medium", "high")
STATUSES = ("active", "superseded", "retracted")
DEFAULT_CONFIDENCE = {
    "observed": "medium",
    "user-reported": "medium",
    "inferred": "low",
    "unknown": "low",
}
CLASSIFICATION_PRIORITY = {
    "observed": 0,
    "user-reported": 1,
    "inferred": 2,
    "unknown": 3,
}

Clock = Callable[[], datetime]


class EvidenceError(ValueError):
    """Base class for actionable evidence-domain errors."""


class EvidenceInputError(EvidenceError):
    """Evidence input is missing or invalid."""


class EvidenceNotFoundError(EvidenceError):
    """The requested evidence record does not exist."""


@dataclass(frozen=True, slots=True)
class EvidenceCreateRequest:
    title: str
    claim: str
    classification: str
    source_type: str
    source: str | None = None
    description: str | None = None
    related_hypothesis: str | None = None
    related_issues: tuple[str, ...] = ()
    confidence: str | None = None
    limitations: tuple[str, ...] = ()
    captured_at: str | None = None


@dataclass(frozen=True, slots=True)
class EvidencePatch:
    values: Mapping[str, Any] = field(default_factory=dict)
    add_limitations: tuple[str, ...] = ()
    remove_limitations: tuple[str, ...] = ()
    add_issues: tuple[str, ...] = ()
    remove_issues: tuple[str, ...] = ()
    supersedes: str | None = None

    @property
    def requested(self) -> bool:
        return bool(
            self.values
            or self.add_limitations
            or self.remove_limitations
            or self.add_issues
            or self.remove_issues
            or self.supersedes is not None
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(clock: Clock) -> str:
    return _normalize_timestamp(clock())


def _normalize_timestamp(value: str | datetime) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise EvidenceInputError(
                f"invalid timestamp '{value}'; use ISO 8601"
            ) from exc
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text(
    value: str | None,
    *,
    field_name: str,
    required: bool = False,
) -> str | None:
    normalized = value.strip() if value is not None else ""
    if required and not normalized:
        raise EvidenceInputError(f"{field_name} cannot be empty")
    return normalized or None


def _enum(value: str, allowed: Iterable[str], *, field_name: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    if normalized not in allowed:
        choices = ", ".join(allowed)
        raise EvidenceInputError(
            f"invalid {field_name} '{value}'; expected one of: {choices}"
        )
    return normalized


def _deduplicate_text(values: Iterable[str], *, field_name: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise EvidenceInputError(f"{field_name} values cannot be empty")
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _canonical_issue_id(value: str) -> str:
    normalized = value.strip().upper()
    if not ISSUE_ID_PATTERN.fullmatch(normalized):
        raise EvidenceInputError(
            f"invalid issue ID '{value}'; expected a value such as ISS-0001"
        )
    return normalized


def _canonical_evidence_id(value: str) -> str:
    normalized = value.strip().upper()
    if not EVIDENCE_ID_PATTERN.fullmatch(normalized):
        raise EvidenceInputError(
            f"invalid evidence ID '{value}'; expected a value such as EVD-0001"
        )
    return normalized


def _deduplicate_issue_ids(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _canonical_issue_id(value)
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def allocate_evidence_id(evidence: Iterable[Mapping[str, Any]]) -> str:
    """Allocate after the greatest historical numeric evidence ID."""

    highest = 0
    for record in evidence:
        match = EVIDENCE_ID_PATTERN.fullmatch(str(record.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"EVD-{highest + 1:04d}"


def derive_issue_evidence_type(
    references: Iterable[str], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> str:
    """Return the strongest active classification for an issue."""

    classifications = [
        evidence_by_id[reference]["classification"]
        for reference in references
        if reference in evidence_by_id
        and evidence_by_id[reference]["status"] == "active"
    ]
    if not classifications:
        return "UNKNOWN"
    strongest = min(classifications, key=CLASSIFICATION_PRIORITY.__getitem__)
    return strongest.replace("-", "_").upper()


def _find_evidence(evidence: list[StateObject], evidence_id: str) -> StateObject:
    canonical = _canonical_evidence_id(evidence_id)
    for record in evidence:
        if record["id"] == canonical:
            return record
    raise EvidenceNotFoundError(
        f"evidence {canonical} was not found; run 'studio evidence list'"
    )


def _sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    captured = datetime.fromisoformat(record["captured_at"]).timestamp()
    created = datetime.fromisoformat(record["created_at"]).timestamp()
    return (-captured, -created, record["id"])


class EvidenceService:
    """Create, query, and update evidence without terminal presentation logic."""

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

    def preview_evidence(self, request: EvidenceCreateRequest) -> StateObject:
        state = self.repository.load_all()
        return self._build_evidence(state, request, timestamp=_timestamp(self.clock))

    def create_evidence(
        self,
        request: EvidenceCreateRequest,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        with StateTransaction(
            self.root,
            operation="evidence.add",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            timestamp = _timestamp(self.clock)
            record = self._build_evidence(state, request, timestamp=timestamp)
            state["evidence"]["evidence"].append(record)
            issue_changes = self._link_issues(
                state, record["id"], additions=record["related_issues"], removals=()
            )
            self._synchronize_issue_types(state, record["related_issues"])
            transaction.set_evidence(state["evidence"])
            if issue_changes:
                transaction.set_issues(state["issues"])
            return transaction.commit(
                changed_fields={"evidence": {"old": None, "new": record["id"]}},
                details={
                    "evidence": copy.deepcopy(record),
                    "recommended_next_workflow": self._recommended_workflow(),
                },
            )

    def get_evidence(self, evidence_id: str) -> StateObject:
        evidence = self.repository.load_evidence()["evidence"]
        record = copy.deepcopy(_find_evidence(evidence, evidence_id))
        record["superseded_by"] = sorted(
            item["id"] for item in evidence if item["supersedes"] == record["id"]
        )
        return record

    def list_evidence(
        self,
        *,
        classification: str | None = None,
        source_type: str | None = None,
        confidence: str | None = None,
        status: str | None = None,
        issue_id: str | None = None,
        include_all: bool = False,
    ) -> list[StateObject]:
        if classification is not None:
            classification = _enum(
                classification, CLASSIFICATIONS, field_name="classification"
            )
        if source_type is not None:
            source_type = _enum(source_type, SOURCE_TYPES, field_name="source type")
        if confidence is not None:
            confidence = _enum(confidence, CONFIDENCES, field_name="confidence")
        if status is not None:
            status = _enum(status, STATUSES, field_name="status")
        canonical_issue: str | None = None
        if issue_id is not None:
            canonical_issue = _canonical_issue_id(issue_id)
            issue_ids = {
                issue["id"] for issue in self.repository.load_issues()["issues"]
            }
            if canonical_issue not in issue_ids:
                raise EvidenceInputError(
                    f"referenced issue {canonical_issue} does not exist"
                )

        matches: list[StateObject] = []
        for record in self.repository.load_evidence()["evidence"]:
            if not include_all and status is None and record["status"] != "active":
                continue
            if (
                classification is not None
                and record["classification"] != classification
            ):
                continue
            if source_type is not None and record["source_type"] != source_type:
                continue
            if confidence is not None and record["confidence"] != confidence:
                continue
            if status is not None and record["status"] != status:
                continue
            if (
                canonical_issue is not None
                and canonical_issue not in record["related_issues"]
            ):
                continue
            matches.append(copy.deepcopy(record))
        return sorted(matches, key=_sort_key)

    def update_evidence(
        self,
        evidence_id: str,
        patch: EvidencePatch,
        *,
        dry_run: bool = False,
    ) -> MutationResult:
        if not patch.requested:
            raise EvidenceInputError("at least one evidence update must be requested")
        canonical_id = _canonical_evidence_id(evidence_id)
        warnings: list[str] = []
        with StateTransaction(
            self.root,
            operation="evidence.update",
            dry_run=dry_run,
            report_renderer=self.report_renderer,
        ) as transaction:
            state = transaction.state
            records = state["evidence"]["evidence"]
            record = _find_evidence(records, canonical_id)
            before = copy.deepcopy(record)
            timestamp = _timestamp(self.clock)
            affected_issue_ids = set(record["related_issues"])

            self._apply_values(record, patch.values)
            self._apply_limitations(record, patch, warnings)
            links_changed = self._apply_issue_links(state, record, patch, warnings)
            affected_issue_ids.update(record["related_issues"])
            superseded_record = self._apply_supersession(
                records, record, patch.supersedes, timestamp
            )
            if superseded_record is not None:
                affected_issue_ids.update(superseded_record["related_issues"])
            self._validate_acyclic(records)
            self._validate_status(records, record)
            self._validate_source(record)

            changed_fields = self._changes(before, record)
            evidence_changed = bool(changed_fields or superseded_record is not None)
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
            if evidence_changed:
                transaction.set_evidence(state["evidence"])
            support_changed = any(
                field_name in changed_fields
                for field_name in ("classification", "status")
            )
            if links_changed or superseded_record is not None or support_changed:
                self._synchronize_issue_types(state, affected_issue_ids)
                transaction.set_issues(state["issues"])
            criterion_state_changed = False
            if evidence_changed:
                affected_evidence_ids = {record["id"]}
                if superseded_record is not None:
                    affected_evidence_ids.add(superseded_record["id"])
                criterion_state_changed = self._mark_criterion_evaluations_stale(
                    state, affected_evidence_ids
                )
                if criterion_state_changed:
                    transaction.set_milestone(state["milestone"])
                    transaction.set_critical_path(state["critical_path"])
            return transaction.commit(
                warnings=warnings,
                changed_fields=changed_fields,
                details={
                    "evidence": copy.deepcopy(record),
                    "recommended_next_workflow": self._recommended_workflow(),
                    "no_op": not evidence_changed and not links_changed,
                    "criterion_evaluations_stale": criterion_state_changed,
                },
            )

    def _build_evidence(
        self,
        state: dict[str, StateObject],
        request: EvidenceCreateRequest,
        *,
        timestamp: str,
    ) -> StateObject:
        title = _text(request.title, field_name="title", required=True)
        claim = _text(request.claim, field_name="claim", required=True)
        classification = _enum(
            request.classification, CLASSIFICATIONS, field_name="classification"
        )
        source_type = _enum(request.source_type, SOURCE_TYPES, field_name="source type")
        source = _text(request.source, field_name="source")
        description = _text(request.description, field_name="description")
        hypothesis = _text(request.related_hypothesis, field_name="related hypothesis")
        confidence = (
            _enum(request.confidence, CONFIDENCES, field_name="confidence")
            if request.confidence
            else DEFAULT_CONFIDENCE[classification]
        )
        issue_ids = _deduplicate_issue_ids(request.related_issues)
        known_issues = {issue["id"] for issue in state["issues"]["issues"]}
        for issue_id in issue_ids:
            if issue_id not in known_issues:
                raise EvidenceInputError(f"referenced issue {issue_id} does not exist")
        limitations = _deduplicate_text(request.limitations, field_name="limitation")
        captured_at = (
            _normalize_timestamp(request.captured_at)
            if request.captured_at
            else timestamp
        )
        record = {
            "id": allocate_evidence_id(state["evidence"]["evidence"]),
            "title": title,
            "claim": claim,
            "classification": classification,
            "source_type": source_type,
            "source": source,
            "description": description,
            "related_hypothesis": hypothesis,
            "related_issues": issue_ids,
            "confidence": confidence,
            "limitations": limitations,
            "captured_at": captured_at,
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": "active",
            "supersedes": None,
        }
        self._validate_source(record)
        return record

    def _apply_values(self, record: StateObject, values: Mapping[str, Any]) -> None:
        required_text = {"title", "claim"}
        optional_text = {"source", "description", "related_hypothesis"}
        enum_fields = {
            "classification": CLASSIFICATIONS,
            "source_type": SOURCE_TYPES,
            "confidence": CONFIDENCES,
            "status": STATUSES,
        }
        for field_name, value in values.items():
            if field_name in required_text:
                record[field_name] = _text(
                    value, field_name=field_name.replace("_", " "), required=True
                )
            elif field_name in optional_text:
                record[field_name] = _text(
                    value, field_name=field_name.replace("_", " ")
                )
            elif field_name in enum_fields:
                record[field_name] = _enum(
                    value, enum_fields[field_name], field_name=field_name
                )
            elif field_name == "captured_at":
                record[field_name] = _normalize_timestamp(value)
            else:
                raise EvidenceInputError(f"unsupported evidence field '{field_name}'")

    def _apply_limitations(
        self,
        record: StateObject,
        patch: EvidencePatch,
        warnings: list[str],
    ) -> None:
        current = list(record["limitations"])
        for limitation in _deduplicate_text(
            patch.add_limitations, field_name="limitation"
        ):
            if limitation not in current:
                current.append(limitation)
            else:
                warnings.append(f"limitation is already recorded: {limitation}")
        for limitation in _deduplicate_text(
            patch.remove_limitations, field_name="limitation"
        ):
            if limitation in current:
                current.remove(limitation)
            else:
                warnings.append(f"limitation is not recorded: {limitation}")
        record["limitations"] = current

    def _apply_issue_links(
        self,
        state: dict[str, StateObject],
        record: StateObject,
        patch: EvidencePatch,
        warnings: list[str],
    ) -> bool:
        additions = _deduplicate_issue_ids(patch.add_issues)
        removals = _deduplicate_issue_ids(patch.remove_issues)
        current = list(record["related_issues"])
        known_issues = {issue["id"] for issue in state["issues"]["issues"]}
        for issue_id in (*additions, *removals):
            if issue_id not in known_issues:
                raise EvidenceInputError(f"referenced issue {issue_id} does not exist")
        for issue_id in additions:
            if issue_id not in current:
                current.append(issue_id)
            else:
                warnings.append(f"{issue_id} is already linked")
        for issue_id in removals:
            if issue_id in current:
                current.remove(issue_id)
            else:
                warnings.append(f"{issue_id} is not linked")
        record["related_issues"] = current
        return self._link_issues(
            state, record["id"], additions=additions, removals=removals
        )

    def _link_issues(
        self,
        state: dict[str, StateObject],
        evidence_id: str,
        *,
        additions: Iterable[str],
        removals: Iterable[str],
    ) -> bool:
        addition_set = set(additions)
        removal_set = set(removals)
        changed = False
        for issue in state["issues"]["issues"]:
            references = issue["evidence_references"]
            if issue["id"] in addition_set and evidence_id not in references:
                references.append(evidence_id)
                changed = True
            if issue["id"] in removal_set and evidence_id in references:
                references.remove(evidence_id)
                changed = True
        return changed

    def _apply_supersession(
        self,
        records: list[StateObject],
        record: StateObject,
        requested: str | None,
        timestamp: str,
    ) -> StateObject | None:
        if requested is None:
            return None
        target_id = _canonical_evidence_id(requested)
        if target_id == record["id"]:
            raise EvidenceInputError("evidence cannot supersede itself")
        try:
            target = _find_evidence(records, target_id)
        except EvidenceNotFoundError as exc:
            raise EvidenceInputError(
                f"superseded evidence {target_id} does not exist"
            ) from exc
        if record["supersedes"] not in {None, target_id}:
            raise EvidenceInputError(
                "an existing supersedes relationship cannot be replaced in B3"
            )
        if record["status"] != "active":
            raise EvidenceInputError(
                "only active evidence can supersede another record"
            )
        other_replacements = [
            item["id"]
            for item in records
            if item["id"] != record["id"] and item["supersedes"] == target_id
        ]
        if other_replacements:
            raise EvidenceInputError(
                f"{target_id} is already superseded by " + ", ".join(other_replacements)
            )
        record["supersedes"] = target_id
        if target["status"] == "superseded":
            return None
        target["_previous_status"] = target["status"]
        target["status"] = "superseded"
        target["updated_at"] = timestamp
        return target

    def _validate_status(self, records: list[StateObject], record: StateObject) -> None:
        incoming = [item for item in records if item["supersedes"] == record["id"]]
        if record["status"] == "superseded" and not incoming:
            raise EvidenceInputError(
                "status superseded requires another evidence record to supersede it"
            )
        if record["status"] == "active" and incoming:
            replacement_ids = ", ".join(item["id"] for item in incoming)
            raise EvidenceInputError(
                f"{record['id']} cannot be active while superseded by {replacement_ids}"
            )

    @staticmethod
    def _validate_source(record: Mapping[str, Any]) -> None:
        if record["source"] is not None:
            return
        if record["source_type"] not in SOURCE_OPTIONAL_TYPES:
            raise EvidenceInputError(
                f"source is required for source type {record['source_type']}"
            )
        if not record["description"]:
            raise EvidenceInputError(
                f"description is required when {record['source_type']} evidence "
                "has no source"
            )

    @staticmethod
    def _validate_acyclic(records: list[StateObject]) -> None:
        next_by_id = {
            record["id"]: record["supersedes"]
            for record in records
            if record["supersedes"] is not None
        }
        for start in next_by_id:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise EvidenceInputError(
                        f"circular supersession chain detected at {current}"
                    )
                seen.add(current)
                current = next_by_id.get(current)

    def _synchronize_issue_types(
        self, state: dict[str, StateObject], issue_ids: Iterable[str]
    ) -> None:
        affected = set(issue_ids)
        evidence_by_id = {item["id"]: item for item in state["evidence"]["evidence"]}
        for issue in state["issues"]["issues"]:
            if issue["id"] in affected:
                issue["evidence_type"] = derive_issue_evidence_type(
                    issue["evidence_references"], evidence_by_id
                )

    @staticmethod
    def _changes(
        before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return {
            key: {"old": copy.deepcopy(before[key]), "new": copy.deepcopy(value)}
            for key, value in after.items()
            if key != "updated_at" and before[key] != value
        }

    def _recommended_workflow(self) -> str:
        project = self.repository.load_project()
        return (
            "/issue-map"
            if (self.root / ".studio" / "playbooks" / "issue-map.md").is_file()
            else project["recommended_next_playbook"]
        )

    @staticmethod
    def _mark_criterion_evaluations_stale(
        state: dict[str, StateObject], evidence_ids: set[str]
    ) -> bool:
        changed = False
        for criterion in state["milestone"]["criteria_results"]:
            if not criterion["evaluation_history"]:
                continue
            latest_ids = {
                item["id"]
                for item in criterion["evaluation_history"][-1]["evidence_snapshot"]
            }
            if not latest_ids.intersection(evidence_ids):
                continue
            reason = (
                "Evidence used by the latest explicit evaluation changed "
                "classification or lifecycle."
            )
            reasons = list(criterion["evaluation_freshness"]["reasons"])
            if reason not in reasons:
                reasons.append(reason)
            criterion["evaluation_freshness"] = {
                "status": "stale",
                "reasons": reasons,
            }
            changed = True
        if changed:
            reasons = list(
                state["critical_path"].get("freshness", {}).get("reasons", [])
            )
            reason = "Criterion evaluation evidence changed materially."
            if reason not in reasons:
                reasons.append(reason)
            state["critical_path"]["freshness"] = {
                "status": "stale",
                "reasons": reasons,
            }
        return changed
