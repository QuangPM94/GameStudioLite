"""Engine adapters: how the framework talks to a game engine.

The adapter layer is the framework's required abstraction. An engine is
supported when an adapter can *probe* what it is able to do on this machine and
carry out those operations, reporting runs and artifacts.

Two things this layer refuses to do, deliberately:

It never claims a capability it has not probed. Recognising a project and being
able to run it are different questions, and the framework must be able to say
"this is a Godot project and I cannot run it".

It never turns a process result into a claim about the game. Adapters return
facts. Evidence is created explicitly, by a person or an agent.
"""

from __future__ import annotations

from .base import (
    CAPABILITIES,
    CAPABILITY_RISK,
    RISK_LEVELS,
    AdapterError,
    AdapterOperationResult,
    BaseEngineAdapter,
    BuildOptions,
    CapabilityReport,
    DetectionResult,
    EngineAdapter,
    OperationAuthorization,
    ProbeResult,
    RunOptions,
    TestOptions,
    UnsupportedOperationError,
)
from .registry import (
    AdapterMatch,
    AdapterNotFoundError,
    detect_adapters,
    discover_adapters,
    get_adapter,
    get_capabilities,
    probe_adapter,
    register_adapter,
    registered_ids,
    reset_registry,
    resolve_adapter,
    unregister_adapter,
)

__all__ = [
    "CAPABILITIES",
    "CAPABILITY_RISK",
    "RISK_LEVELS",
    "AdapterError",
    "AdapterMatch",
    "AdapterNotFoundError",
    "AdapterOperationResult",
    "BaseEngineAdapter",
    "BuildOptions",
    "CapabilityReport",
    "DetectionResult",
    "EngineAdapter",
    "OperationAuthorization",
    "ProbeResult",
    "RunOptions",
    "TestOptions",
    "UnsupportedOperationError",
    "detect_adapters",
    "discover_adapters",
    "get_adapter",
    "get_capabilities",
    "probe_adapter",
    "register_adapter",
    "registered_ids",
    "reset_registry",
    "resolve_adapter",
    "unregister_adapter",
]
