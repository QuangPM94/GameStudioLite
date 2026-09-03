"""What a criterion's evidence actually supports, and what is still missing.

`studio criterion support MC-###` answers "could this criterion be marked
verified, and on what?" It is strictly **read-only**. It never evaluates, never
marks anything passed, and never writes state.

The separation is the point. A command that both advised and decided would let a
milestone advance because the framework talked itself into it. Here the framework
lays out the policy, the evidence it found, the evidence it did not, and its
recommendation — and a person or an agent still has to run
`studio criterion evaluate` to make the call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .criteria import (
    AUTOMATED_TEST_SOURCE_TYPES,
    DOCUMENT_REVIEW_SOURCE_TYPES,
    PLAYER_BEHAVIOR_SOURCE_TYPES,
    RUNTIME_SOURCE_TYPES,
    find_criterion,
)
from .state import StateObject, StateRepository

#: What each policy will accept as support, stated in the same terms the
#: evaluation rules enforce, so advice and enforcement cannot drift apart.
POLICY_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "observed-player-behavior": {
        "summary": (
            "Active evidence classified `observed`, sourced from a human "
            "playtest, video, or runtime session."
        ),
        "classifications": {"observed"},
        "source_types": PLAYER_BEHAVIOR_SOURCE_TYPES,
    },
    "observed-runtime": {
        "summary": (
            "Active evidence classified `observed`, sourced from runtime, "
            "video, telemetry, test output, a build log, or a screenshot."
        ),
        "classifications": {"observed"},
        "source_types": RUNTIME_SOURCE_TYPES,
    },
    "automated-test": {
        "summary": (
            "Active evidence classified `observed`, sourced from test output "
            "or a build log."
        ),
        "classifications": {"observed"},
        "source_types": AUTOMATED_TEST_SOURCE_TYPES,
    },
    "document-review": {
        "summary": (
            "Active document evidence (spec review, user note, external "
            "report, or other), and an evaluation reason naming it."
        ),
        "classifications": None,
        "source_types": DOCUMENT_REVIEW_SOURCE_TYPES,
    },
    "source-review": {
        "summary": (
            "Active evidence classified `observed` or `inferred`, sourced from "
            "a source review."
        ),
        "classifications": {"observed", "inferred"},
        "source_types": {"source-review"},
    },
    "manual-approval": {
        "summary": "Active supporting evidence, or a referenced decision.",
        "classifications": None,
        "source_types": None,
    },
    "mixed": {
        "summary": "Any active supporting evidence, plus an explicit reason.",
        "classifications": None,
        "source_types": None,
    },
}


@dataclass(frozen=True, slots=True)
class SupportAssessment:
    """A read-only view of how well a criterion's evidence meets its policy."""

    criterion_id: str
    description: str
    policy: str
    required_policy: str
    support_status: str
    lifecycle_status: str
    qualifying_evidence: tuple[dict[str, Any], ...]
    non_qualifying_evidence: tuple[dict[str, Any], ...]
    conflicting_evidence: tuple[dict[str, Any], ...]
    missing: tuple[str, ...]
    limitations: tuple[str, ...]
    recommendation: str
    recommended_command: str

    @property
    def could_be_verified(self) -> bool:
        """Whether the policy's evidence requirement is currently satisfied.

        Not a verdict. It says the evidence exists, not that the criterion is
        met — the completion condition is a judgement no rule here can make.
        """

        return not self.missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "verification_policy": self.policy,
            "required_policy": self.required_policy,
            "support_status": self.support_status,
            "lifecycle_status": self.lifecycle_status,
            "available_evidence": list(self.qualifying_evidence),
            "non_qualifying_evidence": list(self.non_qualifying_evidence),
            "conflicting_evidence": list(self.conflicting_evidence),
            "missing_evidence": list(self.missing),
            "limitations": list(self.limitations),
            "recommended_evaluation": self.recommendation,
            "recommended_next_command": self.recommended_command,
            "evidence_requirement_satisfied": self.could_be_verified,
        }


def _summarize(record: StateObject, *, why: str = "") -> dict[str, Any]:
    summary = {
        "id": record["id"],
        "title": record["title"],
        "classification": record["classification"],
        "source_type": record["source_type"],
        "status": record["status"],
        "limitations": list(record.get("limitations", [])),
        "related_runs": list(record.get("related_runs", [])),
        "related_artifacts": list(record.get("related_artifacts", [])),
    }
    if why:
        summary["reason"] = why
    return summary


def _qualifies(record: StateObject, requirement: dict[str, Any]) -> bool:
    classifications = requirement["classifications"]
    source_types = requirement["source_types"]
    if classifications is not None and record["classification"] not in classifications:
        return False
    return not (source_types is not None and record["source_type"] not in source_types)


def _why_not(record: StateObject, requirement: dict[str, Any]) -> str:
    classifications = requirement["classifications"]
    source_types = requirement["source_types"]
    if classifications is not None and record["classification"] not in classifications:
        return (
            f"classification is {record['classification']}; this policy needs "
            + " or ".join(sorted(classifications))
        )
    if source_types is not None and record["source_type"] not in source_types:
        return (
            f"source type is {record['source_type']}; this policy needs one of "
            + ", ".join(sorted(source_types))
        )
    return "does not meet the policy"


def find_supporting_evidence(
    criterion: StateObject, evidence: list[StateObject]
) -> tuple[list[StateObject], list[StateObject]]:
    """Split a criterion's linked evidence into qualifying and non-qualifying."""

    requirement = POLICY_REQUIREMENTS[criterion["verification_policy"]]
    linked = [
        record
        for record in evidence
        if record["id"] in criterion["supporting_evidence"]
        and record["status"] == "active"
    ]
    qualifying = [record for record in linked if _qualifies(record, requirement)]
    non_qualifying = [record for record in linked if record not in qualifying]
    return qualifying, non_qualifying


def find_conflicting_evidence(
    criterion: StateObject, evidence: list[StateObject]
) -> list[StateObject]:
    """Return linked evidence that has been retracted or superseded.

    A criterion still pointing at withdrawn evidence is the exact situation
    where a stale `verified` would go unnoticed, so it is surfaced rather than
    filtered out.
    """

    return [
        record
        for record in evidence
        if record["id"] in criterion["supporting_evidence"]
        and record["status"] in {"retracted", "superseded"}
    ]


def summarize_evidence_limitations(evidence: list[StateObject]) -> tuple[str, ...]:
    """Collect the caveats attached to the evidence, without deduplicating away
    which record each came from."""

    limitations: list[str] = []
    for record in evidence:
        for item in record.get("limitations", []):
            entry = f"{record['id']}: {item}"
            if entry not in limitations:
                limitations.append(entry)
    return tuple(limitations)


def assess_support(root: Path, criterion_id: str) -> SupportAssessment:
    """Report what a criterion's evidence supports. Writes nothing."""

    repository = StateRepository(root)
    milestone = repository.load_milestone()
    evidence = repository.load_evidence()["evidence"]
    criterion = find_criterion(milestone["criteria_results"], criterion_id)

    policy = criterion["verification_policy"]
    requirement = POLICY_REQUIREMENTS[policy]
    qualifying, non_qualifying = find_supporting_evidence(criterion, evidence)
    conflicting = find_conflicting_evidence(criterion, evidence)

    missing: list[str] = []
    if not qualifying:
        missing.append(requirement["summary"])
    if policy == "document-review" and qualifying:
        missing.append(
            "An evaluation reason that names the supporting evidence ID, "
            "document, or artifact."
        )
    if policy in {"manual-approval", "mixed"} and not qualifying:
        missing.append("An explicit evaluation reason recording the judgement.")

    return SupportAssessment(
        criterion_id=criterion["id"],
        description=criterion["description"],
        policy=policy,
        required_policy=requirement["summary"],
        support_status=criterion["support_status"],
        lifecycle_status=criterion["lifecycle_status"],
        qualifying_evidence=tuple(_summarize(record) for record in qualifying),
        non_qualifying_evidence=tuple(
            _summarize(record, why=_why_not(record, requirement))
            for record in non_qualifying
        ),
        conflicting_evidence=tuple(
            _summarize(record, why=f"evidence is {record['status']}")
            for record in conflicting
        ),
        missing=tuple(missing),
        limitations=summarize_evidence_limitations(qualifying),
        recommendation=_recommend(criterion, qualifying, conflicting, missing),
        recommended_command=_recommended_command(criterion, missing),
    )


def _recommend(
    criterion: StateObject,
    qualifying: list[StateObject],
    conflicting: list[StateObject],
    missing: list[str],
) -> str:
    """Say what an evaluator should consider — never what the answer is."""

    if criterion["lifecycle_status"] == "retired":
        return "This criterion is retired; no evaluation applies."
    if conflicting:
        return (
            "Resolve the retracted or superseded evidence before evaluating. "
            "A criterion resting on withdrawn evidence would carry a stale "
            "verdict."
        )
    if missing:
        return (
            "The policy's evidence requirement is not met. `unsupported` or "
            "`partially-supported` is what the current record shows; capture "
            "the missing evidence before considering `verified`."
        )
    limitations = summarize_evidence_limitations(qualifying)
    if limitations:
        return (
            "The evidence requirement is met. Read the limitations below before "
            "deciding: they state what the evidence does not cover, and a "
            "`verified` evaluation should record any that still apply."
        )
    return (
        "The evidence requirement is met. Whether the completion condition is "
        "actually satisfied is still your judgement to record."
    )


def _recommended_command(criterion: StateObject, missing: list[str]) -> str:
    if criterion["lifecycle_status"] == "retired":
        return "studio criterion show " + criterion["id"]
    if missing:
        return "studio evidence add --classification observed ..."
    return (
        f'studio criterion evaluate {criterion["id"]} --support verified --reason "..."'
    )
