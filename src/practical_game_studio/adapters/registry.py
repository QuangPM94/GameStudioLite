"""Finding the adapter that fits a project.

Adapters register themselves here, and resolution picks the one that most
confidently recognises the project. Confidence is compared rather than
first-match-wins so that adding a second engine adapter cannot silently change
which one an existing project resolves to.

Resolving to nothing is a supported answer. The framework must stay usable on a
planning-only project with no engine installed, so "no adapter recognises this"
is reported, never raised as a failure of the project.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import AdapterError, DetectionResult, EngineAdapter

_REGISTRY: dict[str, EngineAdapter] = {}


class AdapterNotFoundError(AdapterError):
    """A named adapter is not registered."""


@dataclass(frozen=True, slots=True)
class AdapterMatch:
    """One adapter's answer about whether it recognises a project."""

    adapter: EngineAdapter
    detection: DetectionResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter.id,
            "display_name": self.adapter.display_name,
            "engine": self.adapter.engine,
            "detection": self.detection.to_dict(),
        }


def register_adapter(adapter: EngineAdapter, *, replace: bool = False) -> None:
    """Add an adapter to the registry."""

    if adapter.id in _REGISTRY and not replace:
        raise AdapterError(f"adapter {adapter.id} is already registered")
    _REGISTRY[adapter.id] = adapter


def unregister_adapter(adapter_id: str) -> None:
    """Remove an adapter, mainly so tests can install a fake one and clean up."""

    _REGISTRY.pop(adapter_id, None)


def discover_adapters() -> tuple[EngineAdapter, ...]:
    """Every registered adapter, in a stable order.

    Importing the built-in adapters here rather than at module import keeps the
    registry usable in a project that has no engine at all.
    """

    _load_builtin_adapters()
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def _load_builtin_adapters() -> None:
    from . import godot  # noqa: F401  (registers on import)


def get_adapter(adapter_id: str) -> EngineAdapter:
    """Return one adapter by id, naming what is available when it is missing."""

    _load_builtin_adapters()
    if adapter_id not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise AdapterNotFoundError(
            f"unknown adapter {adapter_id!r}; registered adapters: {known}"
        )
    return _REGISTRY[adapter_id]


def detect_adapters(root: Path) -> tuple[AdapterMatch, ...]:
    """Ask every adapter whether it recognises this project, best match first."""

    matches = [
        AdapterMatch(adapter=adapter, detection=adapter.detect(root))
        for adapter in discover_adapters()
    ]
    matches.sort(
        key=lambda match: (match.detection.detected, match.detection.confidence),
        reverse=True,
    )
    return tuple(matches)


def resolve_adapter(
    root: Path, *, adapter_id: str | None = None
) -> EngineAdapter | None:
    """Return the adapter for a project, or None when none recognises it.

    An explicit `adapter_id` is honoured even if that adapter does not detect
    the project: a developer overriding detection is making a deliberate claim
    the framework should not second-guess.
    """

    if adapter_id is not None:
        return get_adapter(adapter_id)
    for match in detect_adapters(root):
        if match.detection.detected:
            return match.adapter
    return None


def probe_adapter(root: Path, *, adapter_id: str | None = None) -> Any:
    """Probe the resolved adapter, or return None when there is none."""

    adapter = resolve_adapter(root, adapter_id=adapter_id)
    return adapter.probe(root) if adapter is not None else None


def get_capabilities(root: Path, *, adapter_id: str | None = None) -> tuple[str, ...]:
    """Capabilities the resolved adapter reports as ready on this machine."""

    probe = probe_adapter(root, adapter_id=adapter_id)
    return probe.available_capabilities if probe is not None else ()


def registered_ids() -> tuple[str, ...]:
    """Ids currently in the registry, without triggering built-in imports."""

    return tuple(sorted(_REGISTRY))


def reset_registry(adapters: Iterable[EngineAdapter] = ()) -> None:
    """Replace the registry contents. For tests only."""

    _REGISTRY.clear()
    for adapter in adapters:
        _REGISTRY[adapter.id] = adapter
