"""Command modules for the `studio` CLI.

Each module owns one command noun: it registers that command's arguments and
turns service results into human or JSON output. :mod:`practical_game_studio.cli`
only routes — it builds the parser from these modules and maps a parsed command
to the module that handles it. Domain rules and state mutation stay in the
service modules, never here.
"""

from __future__ import annotations

from . import (
    artifact,
    bootstrap,
    criterion,
    decision,
    dependency,
    doctor,
    evidence,
    execute,
    execution,
    framework,
    issue,
    path,
    project,
    report,
    upgrade,
)

__all__ = [
    "artifact",
    "bootstrap",
    "criterion",
    "decision",
    "dependency",
    "doctor",
    "evidence",
    "execute",
    "execution",
    "framework",
    "issue",
    "path",
    "project",
    "report",
    "upgrade",
]
