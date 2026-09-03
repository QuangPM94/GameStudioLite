"""Finding the capability providers configured for a project.

Providers are optional by construction. An empty registry, or a registry where
nothing is reachable, is a completely normal state — the framework must stay
fully usable without MCP, so "no providers" is an answer, never an error.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .base import Provider, ProviderError, ProviderProbe

_REGISTRY: dict[str, Provider] = {}


class ProviderNotFoundError(ProviderError):
    """A named provider is not registered."""


def register_provider(provider: Provider, *, replace: bool = False) -> None:
    """Add a provider to the registry."""

    if provider.id in _REGISTRY and not replace:
        raise ProviderError(f"provider {provider.id} is already registered")
    _REGISTRY[provider.id] = provider


def unregister_provider(provider_id: str) -> None:
    """Remove a provider, mainly so tests can install a fake one and clean up."""

    _REGISTRY.pop(provider_id, None)


def _load_builtin_providers() -> None:
    from .mcp import godot  # noqa: F401  (registers on import)


def discover_providers() -> tuple[Provider, ...]:
    """Every registered provider, in a stable order."""

    _load_builtin_providers()
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def get_provider(provider_id: str) -> Provider:
    """Return one provider by id, naming what is available when it is missing."""

    _load_builtin_providers()
    if provider_id not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise ProviderNotFoundError(
            f"unknown provider {provider_id!r}; registered providers: {known}"
        )
    return _REGISTRY[provider_id]


def probe_providers(root: Path) -> tuple[ProviderProbe, ...]:
    """Probe every registered provider against a project."""

    return tuple(provider.probe(root) for provider in discover_providers())


def configured_providers(root: Path) -> tuple[ProviderProbe, ...]:
    """Only the providers this project has actually set up."""

    return tuple(
        probe
        for probe in probe_providers(root)
        if probe.health.status != "not-configured"
    )


def provider_capabilities(root: Path) -> tuple[str, ...]:
    """Capabilities usable through providers right now.

    Almost always empty in practice, because a CLI cannot hold an MCP
    connection. That is the honest answer, and callers must fall back to what
    the engine adapter can do rather than waiting for a provider to appear.
    """

    seen: list[str] = []
    for probe in probe_providers(root):
        for name in probe.available_capabilities:
            if name not in seen:
                seen.append(name)
    return tuple(seen)


def registered_ids() -> tuple[str, ...]:
    """Ids currently in the registry, without triggering built-in imports."""

    return tuple(sorted(_REGISTRY))


def reset_registry(providers: Iterable[Provider] = ()) -> None:
    """Replace the registry contents. For tests only."""

    _REGISTRY.clear()
    for provider in providers:
        _REGISTRY[provider.id] = provider
