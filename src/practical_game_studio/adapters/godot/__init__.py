"""The Godot reference adapter.

Godot is the reference engine because it can do the whole basic loop — detect,
run headless, test, build, export — from a command line, with no editor
automation and no MCP. That makes it the right engine to prove the framework's
execution layer against; it does not make the framework Godot-specific.
"""

from __future__ import annotations

from ..registry import register_adapter
from .cli import GodotCliAdapter
from .detector import (
    GodotExecutable,
    GodotProject,
    detect_godot_executable,
    detect_godot_project,
    get_godot_version,
)

ADAPTER = GodotCliAdapter()
register_adapter(ADAPTER, replace=True)

__all__ = [
    "ADAPTER",
    "GodotCliAdapter",
    "GodotExecutable",
    "GodotProject",
    "detect_godot_executable",
    "detect_godot_project",
    "get_godot_version",
]
