"""Verification levels: how much has actually been established, and how.

`studio verify` answers one question at a stated depth. The levels exist because
"is it working?" is not one question, and collapsing them is exactly how a
project ends up believing a green build means a playable game.

| Level | Establishes | Does not establish |
| --- | --- | --- |
| `static` | The project's own state is coherent | Anything about the engine |
| `smoke` | The engine starts and does not immediately die | Anything about gameplay |
| `runtime` | Tests the project defines pass | That the game is enjoyable |
| `gameplay` | *Nothing automatically* | — requires human or provider observation |
| `release` | A packaged build was produced | That the package runs |

Two rules hold across all of them:

A level that could not be checked reports `unknown`, never `passed` and never
`failed`. A missing test framework has not shown the project to be broken, and
it has not shown it to be sound either.

No level asserts evidence. Verification produces runs, artifacts, and a
*proposal* a person or agent may accept. `gameplay` in particular can never pass
on its own, because no process result observes a player.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import (
    AdapterOperationResult,
    BuildOptions,
    OperationAuthorization,
    RunOptions,
    TestOptions,
    resolve_adapter,
)
from .validation import validate_project

#: Ordered from least to most demanding. A level implies the ones before it.
LEVELS = ("static", "smoke", "runtime", "gameplay", "release")

#: Per-check outcome. `skipped` means the check does not apply here; `unknown`
#: means it applies and could not be answered.
CHECK_STATUSES = ("passed", "failed", "unknown", "skipped")

#: Worst-first, so a report's overall status is the worst of its checks.
_SEVERITY = {"failed": 0, "unknown": 1, "skipped": 2, "passed": 3}


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    """One thing that was checked, and what it did or did not establish."""

    name: str
    status: str
    detail: str
    run_id: str | None = None
    artifacts: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "run_id": self.run_id,
            "artifacts": list(self.artifacts),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class EvidenceProposal:
    """A claim the observed facts would support, for a human or agent to accept.

    A proposal is not evidence. It exists so the framework can offer the
    strongest *honest* wording for what it saw, with the limitations attached,
    rather than either staying silent or asserting something itself.
    """

    claim: str
    classification: str
    source_type: str
    limitations: tuple[str, ...]
    related_runs: tuple[str, ...] = ()
    related_artifacts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "classification": self.classification,
            "source_type": self.source_type,
            "limitations": list(self.limitations),
            "related_runs": list(self.related_runs),
            "related_artifacts": list(self.related_artifacts),
        }

    def as_command(self, title: str) -> str:
        """Render the `studio evidence add` an operator would run to accept it."""

        parts = [
            "studio evidence add",
            f'--title "{title}"',
            f'--claim "{self.claim}"',
            f"--classification {self.classification}",
            f"--source-type {self.source_type}",
        ]
        parts.extend(f"--run {run_id}" for run_id in self.related_runs)
        parts.extend(f"--artifact {item}" for item in self.related_artifacts)
        parts.extend(f'--limitation "{item}"' for item in self.limitations)
        return " \\\n  ".join(parts)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Everything one `studio verify` established, and everything it did not."""

    level: str
    checks: tuple[VerificationCheck, ...]
    adapter_id: str | None = None
    proposals: tuple[EvidenceProposal, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        """The worst outcome among the checks; `unknown` when there are none."""

        if not self.checks:
            return "unknown"
        return min(self.checks, key=lambda check: _SEVERITY[check.status]).status

    @property
    def limitations(self) -> tuple[str, ...]:
        seen: list[str] = []
        for check in self.checks:
            for item in check.limitations:
                if item not in seen:
                    seen.append(item)
        return tuple(seen)

    @property
    def run_ids(self) -> tuple[str, ...]:
        return tuple(check.run_id for check in self.checks if check.run_id is not None)

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for check in self.checks:
            for item in check.artifacts:
                if item not in seen:
                    seen.append(item)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "status": self.status,
            "adapter_id": self.adapter_id,
            "checks": [check.to_dict() for check in self.checks],
            "limitations": list(self.limitations),
            "runs": list(self.run_ids),
            "artifacts": list(self.artifact_ids),
            "evidence_proposals": [item.to_dict() for item in self.proposals],
        }


def _from_operation(name: str, operation: AdapterOperationResult) -> VerificationCheck:
    """Map an adapter result onto a check without upgrading its status.

    `unsupported` becomes `unknown`: an operation the adapter could not attempt
    tells us nothing about the project, which is different from a failure.
    """

    status = {
        "unsupported": "unknown",
        "cancelled": "unknown",
    }.get(operation.status, operation.status)
    return VerificationCheck(
        name=name,
        status=status if status in CHECK_STATUSES else "unknown",
        detail=operation.detail,
        run_id=operation.run_id,
        artifacts=tuple(operation.artifacts),
        limitations=tuple(operation.limitations),
    )


def verify_static(root: Path) -> VerificationCheck:
    """Check that the project's own canonical state is coherent.

    Establishes nothing whatsoever about the engine or the game.
    """

    result = validate_project(root)
    if result.ok:
        return VerificationCheck(
            name="static",
            status="passed",
            detail="Project scaffold, schemas, state, and references are valid.",
            limitations=(
                (
                    "Static validation examines project state only; the game was "
                    "not built or run."
                ),
            ),
        )
    return VerificationCheck(
        name="static",
        status="failed",
        detail=f"{len(result.errors)} validation error(s): "
        + "; ".join(result.errors[:5]),
    )


def verify_smoke(root: Path, *, adapter_id: str | None = None) -> VerificationCheck:
    """Launch the game headless and observe whether it starts and stays up."""

    adapter = resolve_adapter(root, adapter_id=adapter_id)
    if adapter is None:
        return VerificationCheck(
            name="smoke",
            status="unknown",
            detail="No engine adapter recognises this project.",
            limitations=("The game was not launched.",),
        )
    operation = adapter.run(
        root,
        RunOptions(
            headless=True,
            authorization=OperationAuthorization(risk_level="low"),
        ),
    )
    check = _from_operation("smoke", operation)
    # A headless game with a main loop is *supposed* to keep running. Being
    # stopped by the timeout is the successful smoke outcome, not a failure.
    if operation.record is not None and operation.record.process.outcome == "timeout":
        return VerificationCheck(
            name="smoke",
            status="passed",
            detail=operation.detail,
            run_id=operation.run_id,
            artifacts=tuple(operation.artifacts),
            limitations=(
                (
                    "The engine started and stayed running; no gameplay, input, or "
                    "player experience was observed."
                ),
            ),
        )
    return check


def verify_runtime(root: Path, *, adapter_id: str | None = None) -> VerificationCheck:
    """Run whatever tests the project defines."""

    adapter = resolve_adapter(root, adapter_id=adapter_id)
    if adapter is None:
        return VerificationCheck(
            name="runtime",
            status="unknown",
            detail="No engine adapter recognises this project.",
            limitations=("No tests were run.",),
        )
    operation = adapter.test(
        root,
        TestOptions(authorization=OperationAuthorization(risk_level="low")),
    )
    if operation.status == "skipped":
        # No test framework is not a failing project. It is a project whose
        # test result is unknown, which the caller must be free to accept.
        return VerificationCheck(
            name="runtime",
            status="unknown",
            detail=operation.detail,
            limitations=tuple(operation.limitations),
        )
    return _from_operation("runtime", operation)


def verify_gameplay(root: Path, *, adapter_id: str | None = None) -> VerificationCheck:
    """Report that gameplay cannot be verified by the CLI, and say what would.

    This check never passes on its own. Nothing a process reports observes a
    player, and a framework that let `gameplay` go green from an exit code would
    be lying about the only thing that actually matters.
    """

    adapter = resolve_adapter(root, adapter_id=adapter_id)
    probe = adapter.probe(root) if adapter is not None else None
    if probe is not None and probe.supports("INPUT_INJECTION"):
        detail = (
            "This adapter reports input injection, but driving inputs is still "
            "not observing a player."
        )
    else:
        detail = "No adapter here can observe gameplay."
    return VerificationCheck(
        name="gameplay",
        status="unknown",
        detail=(
            f"{detail} Record a human playtest with "
            "`studio evidence add --classification user-reported`, or attach a "
            "captured session as an artifact."
        ),
        limitations=(
            (
                "Gameplay, difficulty, clarity, and enjoyment cannot be established "
                "by any process result."
            ),
        ),
    )


def verify_release(root: Path, *, adapter_id: str | None = None) -> VerificationCheck:
    """Produce a release build, without claiming the package runs."""

    adapter = resolve_adapter(root, adapter_id=adapter_id)
    if adapter is None:
        return VerificationCheck(
            name="release",
            status="unknown",
            detail="No engine adapter recognises this project.",
            limitations=("No build was produced.",),
        )
    operation = adapter.build(
        root,
        BuildOptions(
            profile="release",
            # `studio verify --level release` is itself gated by the caller;
            # the build inherits that decision rather than claiming its own.
            authorization=OperationAuthorization(risk_level="medium"),
        ),
    )
    check = _from_operation("release", operation)
    return VerificationCheck(
        name=check.name,
        status=check.status,
        detail=check.detail,
        run_id=check.run_id,
        artifacts=check.artifacts,
        limitations=(
            *check.limitations,
            "A produced package has not been launched or smoke-tested.",
        ),
    )


#: Which checks each level runs, cumulatively.
_LEVEL_CHECKS: dict[str, tuple[str, ...]] = {
    "static": ("static",),
    "smoke": ("static", "smoke"),
    "runtime": ("static", "smoke", "runtime"),
    "gameplay": ("static", "smoke", "runtime", "gameplay"),
    "release": ("static", "smoke", "runtime", "release"),
}

#: Every entry takes `(root, adapter_id)` so the dispatch loop below stays a
#: loop rather than a chain of special cases.
_CHECK_FUNCTIONS = {
    "static": lambda root, adapter_id: verify_static(root),
    "smoke": lambda root, adapter_id: verify_smoke(root, adapter_id=adapter_id),
    "runtime": lambda root, adapter_id: verify_runtime(root, adapter_id=adapter_id),
    "gameplay": lambda root, adapter_id: verify_gameplay(root, adapter_id=adapter_id),
    "release": lambda root, adapter_id: verify_release(root, adapter_id=adapter_id),
}


def verify(
    root: Path, level: str = "smoke", *, adapter_id: str | None = None
) -> VerificationReport:
    """Run every check a level requires and report what was established."""

    if level not in LEVELS:
        raise ValueError(
            f"unknown verification level {level!r}; expected one of "
            + ", ".join(LEVELS)
        )
    adapter = resolve_adapter(root, adapter_id=adapter_id)
    checks: list[VerificationCheck] = []
    for name in _LEVEL_CHECKS[level]:
        checks.append(_CHECK_FUNCTIONS[name](root, adapter_id))
        # A project whose own state is incoherent cannot support conclusions
        # drawn from running it, so stop rather than pile results on sand.
        if checks[-1].name == "static" and checks[-1].status == "failed":
            break
    report = VerificationReport(
        level=level,
        checks=tuple(checks),
        adapter_id=adapter.id if adapter is not None else None,
    )
    return VerificationReport(
        level=report.level,
        checks=report.checks,
        adapter_id=report.adapter_id,
        proposals=propose_evidence(report),
    )


def propose_evidence(report: VerificationReport) -> tuple[EvidenceProposal, ...]:
    """Offer the strongest honest claim the observed checks would support.

    The framework may propose. It must not invent gameplay claims, and it must
    never propose a claim about fun, clarity, or difficulty, because no process
    result is capable of supporting one.
    """

    proposals: list[EvidenceProposal] = []
    for check in report.checks:
        if check.status != "passed" or check.run_id is None:
            continue
        if check.name == "smoke":
            proposals.append(
                EvidenceProposal(
                    claim=(
                        "The current build launches the engine without an "
                        "immediate runtime crash."
                    ),
                    classification="observed",
                    source_type="runtime",
                    limitations=(
                        (
                            "No player input, gameplay loop, or player experience "
                            "was verified."
                        ),
                    ),
                    related_runs=(check.run_id,),
                    related_artifacts=check.artifacts,
                )
            )
        elif check.name == "runtime":
            proposals.append(
                EvidenceProposal(
                    claim=(
                        "The project's automated tests pass against the current "
                        "revision."
                    ),
                    classification="observed",
                    source_type="test-output",
                    limitations=(
                        (
                            "Passing tests describe the code under test; they say "
                            "nothing about whether the game is enjoyable or clear."
                        ),
                    ),
                    related_runs=(check.run_id,),
                    related_artifacts=check.artifacts,
                )
            )
        elif check.name == "release":
            proposals.append(
                EvidenceProposal(
                    claim="A release package was produced from the current revision.",
                    classification="observed",
                    source_type="build-log",
                    limitations=(
                        "The produced package has not been launched or smoke-tested.",
                    ),
                    related_runs=(check.run_id,),
                    related_artifacts=check.artifacts,
                )
            )
    return tuple(proposals)


def summarize_levels() -> Sequence[tuple[str, str]]:
    """Return each level with what it does and does not establish."""

    return (
        ("static", "project state is coherent; nothing about the engine"),
        ("smoke", "the engine starts and stays up; nothing about gameplay"),
        ("runtime", "the project's tests pass; nothing about enjoyment"),
        ("gameplay", "never automatic; requires human or provider observation"),
        ("release", "a package was produced; not that it runs"),
    )
