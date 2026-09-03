"""Optional capability providers.

    EngineAdapter  = required abstraction
    Provider       = optional capability source

A provider adds capabilities an engine's command line cannot offer — screenshots,
scene inspection, input injection. It never becomes required for one, and the
framework stays fully usable with no provider configured at all.

Providers are sources of observations, never of verdicts.
"""

from __future__ import annotations

from .base import (
    HEALTH,
    PROVIDER_CAPABILITIES,
    STABILITY,
    BaseProvider,
    Provider,
    ProviderCapability,
    ProviderError,
    ProviderHealth,
    ProviderProbe,
)
from .registry import (
    ProviderNotFoundError,
    configured_providers,
    discover_providers,
    get_provider,
    probe_providers,
    provider_capabilities,
    register_provider,
    registered_ids,
    reset_registry,
    unregister_provider,
)

__all__ = [
    "HEALTH",
    "PROVIDER_CAPABILITIES",
    "STABILITY",
    "BaseProvider",
    "Provider",
    "ProviderCapability",
    "ProviderError",
    "ProviderHealth",
    "ProviderNotFoundError",
    "ProviderProbe",
    "configured_providers",
    "discover_providers",
    "get_provider",
    "probe_providers",
    "provider_capabilities",
    "register_provider",
    "registered_ids",
    "reset_registry",
    "unregister_provider",
]
