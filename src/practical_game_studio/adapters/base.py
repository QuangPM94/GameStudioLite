"""The engine adapter contract.

An adapter is how the framework talks to one engine. The contract is built around
*capabilities* rather than a fixed method list, because engines differ in what
they can actually be asked to do from a command line, and the framework must be
able to say "I cannot take a screenshot here" instead of pretending or crashing.

Two rules shape everything below.

An adapter never claims a capability it has not probed. `detect` says whether
this adapter recognises the project; `probe` says what it can do *on this
machine, right now* — which is not the same question, because an adapter can
recognise a Godot project on a machine with no Godot installed.

An adapter reports facts, never verdicts. It returns runs and artifacts. It does
not decide that a build working means a game working; that judgement is made
explicitly, by a person or an agent creating evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..execution import ExecutionRecord

#: What an adapter may be able to do. Membership in an adapter's capability set
#: is a probed claim, not a declared intention.
CAPABILITIES = (
    "RUN",
    "HEADLESS",
    "TEST",
    "BUILD",
    "EXPORT",
    "LOG_CAPTURE",
    "SCREENSHOT",
    "RUNTIME_INSPECT",
    "INPUT_INJECTION",
    "PROFILE",
    "EDITOR_INSPECT",
    "EDITOR_MODIFY",
)

#: How much damage an operation could do, used by the execution-safety layer to
#: decide what needs human approval.
RISK_LEVELS = ("safe", "low", "medium", "high")

#: Default risk for each capability. An adapter may raise a level but should not
#: lower one: the framework's default assumption about an unfamiliar operation
#: should be the cautious one.
CAPABILITY_RISK = {
    "RUN": "low",
    "HEADLESS": "low",
    "TEST": "low",
    "LOG_CAPTURE": "safe",
    "SCREENSHOT": "low",
    "RUNTIME_INSPECT": "low",
    "PROFILE": "low",
    "BUILD": "medium",
    "EXPORT": "medium",
    "EDITOR_MODIFY": "medium",
    "INPUT_INJECTION": "medium",
    "EDITOR_INSPECT": "safe",
}


class AdapterError(RuntimeError):
    """An adapter could not carry out what was asked of it."""


class UnsupportedOperationError(AdapterError):
    """An operation was requested that this adapter cannot perform here.

    Carries what was asked, what the adapter can do, and what to try instead, so
    an agent reading the message can choose a different action rather than
    retrying the same one.
    """

    def __init__(
        self,
        adapter_id: str,
        capability: str,
        *,
        available: Sequence[str] = (),
        reason: str | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.capability = capability
        self.available = tuple(available)
        self.reason = reason
        detail = f" ({reason})" if reason else ""
        offer = (
            "; this adapter reports: " + ", ".join(sorted(self.available))
            if self.available
            else "; this adapter reports no capabilities on this machine"
        )
        super().__init__(f"{adapter_id} cannot perform {capability}{detail}{offer}")


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Whether an adapter recognises a project, and on what grounds.

    `confidence` is reported rather than reduced to a boolean so two adapters
    that both match a directory can be ranked without either having to know
    about the other.
    """

    detected: bool
    confidence: int = 0
    #: The concrete files or markers that led to this answer.
    indicators: tuple[str, ...] = ()
    detail: str = ""
    project_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "indicators": list(self.indicators),
            "detail": self.detail,
            "project_path": self.project_path,
        }


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """One capability's readiness, as probed on this machine.

    `readiness` distinguishes `unavailable` from `unknown` on purpose: "we looked
    and it is not there" and "we could not tell" lead a person to different next
    actions, and merging them would let the framework imply it had checked
    something it had not.
    """

    capability: str
    readiness: str
    detail: str
    risk: str = "low"

    @property
    def available(self) -> bool:
        return self.readiness == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "readiness": self.readiness,
            "detail": self.detail,
            "risk": self.risk,
        }


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What an adapter can actually do here, right now."""

    adapter_id: str
    engine: str
    engine_version: str | None
    executable: str | None
    capabilities: tuple[CapabilityReport, ...] = ()
    limitations: tuple[str, ...] = ()

    def capability(self, name: str) -> CapabilityReport | None:
        for report in self.capabilities:
            if report.capability == name:
                return report
        return None

    def supports(self, name: str) -> bool:
        """Whether a capability was probed and found ready.

        An unprobed capability is not supported. Silence is never a yes.
        """

        report = self.capability(name)
        return report is not None and report.available

    @property
    def available_capabilities(self) -> tuple[str, ...]:
        return tuple(
            report.capability for report in self.capabilities if report.available
        )

    def require(self, name: str) -> None:
        """Raise a useful error unless this capability is ready."""

        report = self.capability(name)
        if report is not None and report.available:
            return
        raise UnsupportedOperationError(
            self.adapter_id,
            name,
            available=self.available_capabilities,
            reason=report.detail if report else "not probed",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "executable": self.executable,
            "capabilities": [report.to_dict() for report in self.capabilities],
            "available_capabilities": list(self.available_capabilities),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class OperationAuthorization:
    """How the caller was permitted to ask for an operation.

    Carried on every options object so the adapter records what the safety
    layer actually decided. Defaults describe an operation that needed no
    approval; an adapter must never invent a stronger authorisation than it
    was handed.
    """

    risk_level: str = "low"
    authorization: str = "risk-below-threshold"


@dataclass(frozen=True, slots=True)
class RunOptions:
    """What `studio run` asks an adapter for."""

    headless: bool = False
    scene: str | None = None
    timeout_seconds: float | None = None
    capture_log: bool = True
    extra_args: tuple[str, ...] = ()
    authorization: OperationAuthorization = field(
        default_factory=OperationAuthorization
    )


@dataclass(frozen=True, slots=True)
class TestOptions:
    """What `studio test` asks an adapter for."""

    #: `unit`, `scene`, `integration`, or `all`.
    suite: str = "all"
    timeout_seconds: float | None = None
    extra_args: tuple[str, ...] = ()
    authorization: OperationAuthorization = field(
        default_factory=OperationAuthorization
    )


@dataclass(frozen=True, slots=True)
class BuildOptions:
    """What `studio build` and `studio export` ask an adapter for."""

    target: str | None = None
    profile: str = "debug"
    output: str | None = None
    timeout_seconds: float | None = None
    extra_args: tuple[str, ...] = ()
    authorization: OperationAuthorization = field(
        default_factory=OperationAuthorization
    )


@dataclass(frozen=True, slots=True)
class AdapterOperationResult:
    """The outcome of one adapter operation.

    Wraps the execution record rather than replacing it, so that whatever an
    adapter concludes, the underlying run and artifacts stay inspectable.
    """

    record: ExecutionRecord | None
    #: `passed`, `failed`, `unknown`, `skipped`, or `unsupported`.
    status: str
    detail: str
    limitations: tuple[str, ...] = field(default_factory=tuple)
    artifacts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def run_id(self) -> str | None:
        return self.record.run_id if self.record else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "run_id": self.run_id,
            "artifacts": list(self.artifacts),
            "limitations": list(self.limitations),
            "record": self.record.to_dict() if self.record else None,
        }


@runtime_checkable
class EngineAdapter(Protocol):
    """What every engine adapter must provide.

    Only `detect` and `probe` are mandatory in practice: an adapter that cannot
    build declares no BUILD capability, and the base class below turns the
    attempt into a clear `UnsupportedOperationError` rather than an
    `AttributeError` an agent cannot act on.
    """

    id: str
    display_name: str
    engine: str

    def detect(self, root: Path) -> DetectionResult: ...

    def probe(self, root: Path) -> ProbeResult: ...


class BaseEngineAdapter:
    """Shared behaviour for adapters: capability gating and friendly refusals.

    Subclasses override only the operations they can genuinely perform. Every
    other operation refuses by name, listing what this adapter *can* do, so an
    agent can pick a different action instead of retrying a wall.
    """

    id: str = "base"
    display_name: str = "Base adapter"
    engine: str = "unknown"

    def detect(self, root: Path) -> DetectionResult:
        raise NotImplementedError

    def probe(self, root: Path) -> ProbeResult:
        raise NotImplementedError

    def _refuse(self, root: Path, capability: str) -> AdapterOperationResult:
        probe = self.probe(root)
        report = probe.capability(capability)
        return AdapterOperationResult(
            record=None,
            status="unsupported",
            detail=UnsupportedOperationError(
                self.id,
                capability,
                available=probe.available_capabilities,
                reason=report.detail if report else "not probed",
            ).args[0],
            limitations=(
                f"{capability} was not attempted, so nothing about it is known.",
            ),
        )

    def run(self, root: Path, options: RunOptions) -> AdapterOperationResult:
        return self._refuse(root, "RUN")

    def test(self, root: Path, options: TestOptions) -> AdapterOperationResult:
        return self._refuse(root, "TEST")

    def build(self, root: Path, options: BuildOptions) -> AdapterOperationResult:
        return self._refuse(root, "BUILD")

    def export(self, root: Path, options: BuildOptions) -> AdapterOperationResult:
        return self._refuse(root, "EXPORT")

    def capture_screenshot(self, root: Path) -> AdapterOperationResult:
        return self._refuse(root, "SCREENSHOT")

    def inspect_runtime(self, root: Path) -> AdapterOperationResult:
        return self._refuse(root, "RUNTIME_INSPECT")

    def inject_input(self, root: Path, script: str) -> AdapterOperationResult:
        return self._refuse(root, "INPUT_INJECTION")

    def profile(self, root: Path, options: RunOptions) -> AdapterOperationResult:
        return self._refuse(root, "PROFILE")
