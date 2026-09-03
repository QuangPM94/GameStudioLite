"""What a piece of media is allowed to be evidence *of*.

A screenshot proves a frame was rendered. A video proves a session was recorded.
Neither proves a player understood anything, and the gap between those is where
a project deceives itself most easily — a folder of screenshots feels like proof
of a working game while establishing nothing about whether it is playable.

So media entering the framework carries a provenance question: **who or what
produced this, and does that support the claim being made?** These rules answer
it. They are advisory by design — the framework proposes the strongest honest
classification and refuses to assert a stronger one, but a person who watched a
playtest can always record what they saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Who or what produced an artifact. This is the fact that decides what may be
#: claimed from it; everything else here follows from it.
CAPTURE_SOURCES = (
    "human-playtest",
    "developer-session",
    "automated-run",
    "provider-capture",
    "external-report",
    "unknown",
)

#: The strongest classification each capture source can support on its own, and
#: what it can never support no matter how much of it there is.
_SOURCE_RULES: dict[str, dict[str, Any]] = {
    "human-playtest": {
        "strongest": "observed",
        "supports_player_behavior": True,
        "reason": (
            "A recorded human playtest can show player behaviour, because a "
            "player was actually playing."
        ),
    },
    "developer-session": {
        "strongest": "observed",
        "supports_player_behavior": False,
        "reason": (
            "A developer driving their own game is observing the software, not "
            "a player. Someone who built the thing cannot be surprised by it."
        ),
    },
    "automated-run": {
        "strongest": "observed",
        "supports_player_behavior": False,
        "reason": (
            "An automated run shows what the engine did. Nobody was playing, so "
            "nothing about player experience was observed."
        ),
    },
    "provider-capture": {
        "strongest": "observed",
        "supports_player_behavior": False,
        "reason": (
            "A provider capture shows what the engine rendered or reported. "
            "Injected input is not player behaviour."
        ),
    },
    "external-report": {
        "strongest": "user-reported",
        "supports_player_behavior": True,
        "reason": (
            "A report from outside the project is what someone said happened. "
            "It can describe player behaviour, but it was not observed here."
        ),
    },
    "unknown": {
        "strongest": "unknown",
        "supports_player_behavior": False,
        "reason": (
            "Media with no recorded provenance supports no classification. "
            "Record how it was captured before drawing anything from it."
        ),
    },
}

#: Ordered by how much they assert, so a proposed classification can be compared
#: against what the provenance actually supports.
_CLASSIFICATION_STRENGTH = {
    "unknown": 0,
    "inferred": 1,
    "user-reported": 2,
    "observed": 3,
}

#: Artifact types that are media a person might mistake for proof of play.
MEDIA_TYPES = ("screenshot", "video", "telemetry", "profile")


@dataclass(frozen=True, slots=True)
class ProvenanceAssessment:
    """Whether a proposed claim is supported by how the media was captured."""

    capture_source: str
    proposed_classification: str
    strongest_supported: str
    supported: bool
    reason: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_source": self.capture_source,
            "proposed_classification": self.proposed_classification,
            "strongest_supported": self.strongest_supported,
            "supported": self.supported,
            "reason": self.reason,
            "limitations": list(self.limitations),
        }


def capture_source(artifact: dict[str, Any]) -> str:
    """Read an artifact's recorded capture source, defaulting to `unknown`.

    Defaulting to `unknown` rather than guessing from the file type is the whole
    point: a `.png` says nothing about who was at the keyboard.
    """

    metadata = artifact.get("metadata") or {}
    value = metadata.get("capture_source")
    return value if value in CAPTURE_SOURCES else "unknown"


def strongest_supported_classification(source: str) -> str:
    """The most a given capture source can support on its own."""

    return _SOURCE_RULES.get(source, _SOURCE_RULES["unknown"])["strongest"]


def supports_player_behavior(source: str) -> bool:
    """Whether this capture source can support a claim about player behaviour."""

    return bool(
        _SOURCE_RULES.get(source, _SOURCE_RULES["unknown"])["supports_player_behavior"]
    )


def limitations_for(source: str, artifact_type: str) -> tuple[str, ...]:
    """The caveats that must travel with evidence drawn from this media."""

    rule = _SOURCE_RULES.get(source, _SOURCE_RULES["unknown"])
    limitations = [rule["reason"]]
    if artifact_type == "screenshot":
        limitations.append(
            "A screenshot is a single frame. It shows what was rendered at one "
            "moment, not how the game behaves over time."
        )
    elif artifact_type == "video":
        limitations.append(
            "A recording shows what happened on screen. What the player "
            "understood or intended is not visible in it."
        )
    elif artifact_type == "telemetry":
        limitations.append(
            "Telemetry counts events. Why a player did something is not in the numbers."
        )
    return tuple(limitations)


def assess(
    artifact: dict[str, Any], proposed_classification: str
) -> ProvenanceAssessment:
    """Check a proposed classification against how the artifact was captured."""

    source = capture_source(artifact)
    strongest = strongest_supported_classification(source)
    proposed_strength = _CLASSIFICATION_STRENGTH.get(proposed_classification, 0)
    supported = proposed_strength <= _CLASSIFICATION_STRENGTH[strongest]
    rule = _SOURCE_RULES.get(source, _SOURCE_RULES["unknown"])
    reason = (
        rule["reason"]
        if supported
        else (
            f"{artifact.get('id', 'this artifact')} was captured as "
            f"{source!r}, which supports at most {strongest!r}. "
            f"{rule['reason']}"
        )
    )
    return ProvenanceAssessment(
        capture_source=source,
        proposed_classification=proposed_classification,
        strongest_supported=strongest,
        supported=supported,
        reason=reason,
        limitations=limitations_for(source, str(artifact.get("type", "other"))),
    )


def describe_rules() -> tuple[tuple[str, str, str], ...]:
    """Return (source, strongest classification, player-behaviour) for display."""

    return tuple(
        (
            source,
            rule["strongest"],
            "yes" if rule["supports_player_behavior"] else "no",
        )
        for source, rule in _SOURCE_RULES.items()
    )
