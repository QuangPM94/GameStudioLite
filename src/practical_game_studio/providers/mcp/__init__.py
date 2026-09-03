"""MCP-backed capability providers.

MCP is an optional capability source. Importing this package registers the
providers the framework knows how to *detect*; it never opens a connection, and
nothing here is required for the framework to work.
"""

from __future__ import annotations

from ..registry import register_provider
from .godot import PROVIDER, GodotMcpProvider

register_provider(PROVIDER, replace=True)

__all__ = ["PROVIDER", "GodotMcpProvider"]
