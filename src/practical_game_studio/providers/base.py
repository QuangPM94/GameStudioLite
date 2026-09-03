"""Optional capability sources that augment an engine adapter.

A provider is something that can do more with an engine than its command line
can — an editor plugin, an MCP server, a debug bridge. Screenshots, scene-tree
inspection, and input injection live here because no engine CLI offers them.

The relationship with adapters is deliberately asymmetric:

    EngineAdapter  = required abstraction
    Provider       = optional capability source

A provider may *add* capabilities. It may never be required for one, and it may
never remove one an adapter already has. Every operation that a provider can
accelerate must still have a CLI answer, even if that answer is "this cannot be
observed here" — otherwise configuring MCP would quietly become mandatory, which
the framework's non-goals rule out.

One more rule, and it is the important one for evidence integrity: a provider is
a *source of observations*, not a source of verdicts. A screenshot captured
through a provider is an artifact. Whether it shows a player understanding the
game is a claim somebody has to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: What a provider may be able to do. Names match the adapter capability
#: vocabulary so `studio doctor` can merge both into one readiness table.
PROVIDER_CAPABILITIES = (
    "EDITOR_INSPECT",
    "EDITOR_MODIFY",
    "SCENE_INSPECT",
    "SCENE_MODIFY",
    "LAUNCH",
    "SCREENSHOT",
    "RUNTIME_INSPECT",
    "INPUT_INJECTION",
    "PROFILE",
    "REPLAY",
)

#: How much a capability can be relied on. `experimental` is not a lesser
#: `stable`: it means results may change between provider versions, which a
#: reader weighing evidence needs to know.
STABILITY = ("stable", "experimental", "unknown")

#: A provider is reachable, unreachable, or was never set up. The three are
#: distinguished because they call for different actions: fix it, start it, or
#: configure it.
HEALTH = ("healthy", "unreachable", "not-configured", "unknown")


class ProviderError(RuntimeError):
    """A provider could not do what was asked of it."""


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    """One capability a provider claims, with how far it can be trusted."""

    capability: str
    readiness: str
    stability: str
    detail: str
    #: What a caller must accept when using results from this capability.
    limitations: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.readiness == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "readiness": self.readiness,
            "stability": self.stability,
            "detail": self.detail,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Whether a provider is actually usable right now."""

    status: str
    detail: str
    #: Where the configuration was found, so a reader can go look at it.
    configuration: str | None = None

    @property
    def healthy(self) -> bool:
        return self.status == "healthy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "configuration": self.configuration,
        }


@dataclass(frozen=True, slots=True)
class ProviderProbe:
    """Everything known about one provider for a project."""

    provider_id: str
    display_name: str
    engine: str | None
    health: ProviderHealth
    capabilities: tuple[ProviderCapability, ...] = ()
    #: How results obtained through this provider must be treated.
    evidence_policy: tuple[str, ...] = ()

    def capability(self, name: str) -> ProviderCapability | None:
        for item in self.capabilities:
            if item.capability == name:
                return item
        return None

    def supports(self, name: str) -> bool:
        """Whether a capability is both claimed and reachable.

        A provider that is configured but unreachable supports nothing. Its
        claims describe what it could do if it were running, and acting on them
        would mean acting on an assumption.
        """

        if not self.health.healthy:
            return False
        item = self.capability(name)
        return item is not None and item.available

    @property
    def available_capabilities(self) -> tuple[str, ...]:
        return tuple(
            item.capability
            for item in self.capabilities
            if self.supports(item.capability)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "engine": self.engine,
            "health": self.health.to_dict(),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "available_capabilities": list(self.available_capabilities),
            "evidence_policy": list(self.evidence_policy),
        }


@runtime_checkable
class Provider(Protocol):
    """What every capability provider must offer."""

    id: str
    display_name: str

    def detect(self, root: Path) -> bool: ...

    def probe(self, root: Path) -> ProviderProbe: ...

    def health(self, root: Path) -> ProviderHealth: ...


class BaseProvider:
    """Shared behaviour: capability gating and honest refusals.

    Subclasses implement `detect`, `health`, and `capabilities`. Optional
    operations refuse by name rather than raising `AttributeError`, so an agent
    gets something it can act on.
    """

    id: str = "base"
    display_name: str = "Base provider"
    engine: str | None = None
    evidence_policy: tuple[str, ...] = ()

    def detect(self, root: Path) -> bool:
        raise NotImplementedError

    def health(self, root: Path) -> ProviderHealth:
        raise NotImplementedError

    def capabilities(self, root: Path) -> tuple[ProviderCapability, ...]:
        return ()

    def probe(self, root: Path) -> ProviderProbe:
        """Report health and capabilities together.

        Capabilities are still reported when the provider is unreachable, so a
        reader can see what configuring it would buy. `supports()` remains False
        for all of them, so nothing can act on that list by mistake.
        """

        return ProviderProbe(
            provider_id=self.id,
            display_name=self.display_name,
            engine=self.engine,
            health=self.health(root),
            capabilities=self.capabilities(root),
            evidence_policy=self.evidence_policy,
        )

    def unsupported(self, root: Path, capability: str) -> ProviderError:
        """Build the error for an operation this provider cannot perform here."""

        probe = self.probe(root)
        item = probe.capability(capability)
        reason = item.detail if item else "the provider does not offer it"
        offer = (
            "; this provider offers: " + ", ".join(sorted(probe.available_capabilities))
            if probe.available_capabilities
            else "; this provider offers nothing right now"
        )
        return ProviderError(f"{self.id} cannot perform {capability} ({reason}){offer}")
