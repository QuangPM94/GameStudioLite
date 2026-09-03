"""Scaffold 1.4 -> 1.5: bounded work packets.

Autonomous work needs a boundary that exists *before* the work does. A packet
states what to change, which files may be touched, what must be true at the end,
and which commands prove it — written down where the framework can check it,
rather than agreed in a conversation nobody can re-read.

This migration only creates the document. It does not convert existing issues or
critical-path items into packets: turning a description of a problem into a
contract about how to fix it is a judgement, and guessing it for someone would
produce boundaries nobody agreed to.
"""

from __future__ import annotations

import copy

from ..state import CanonicalState
from .registry import Migration

WORK_DOCUMENT = {"schema_version": "1.0", "work": []}


def migrate(state: CanonicalState) -> CanonicalState:
    """Add the work-packet document."""

    migrated = copy.deepcopy(state)
    migrated.setdefault("work", copy.deepcopy(WORK_DOCUMENT))
    return migrated


MIGRATION = Migration(
    id="005",
    from_version="1.4",
    to_version="1.5",
    summary=(
        "Add work.json so bounded autonomous work has a contract the framework "
        "can check."
    ),
    migrate=migrate,
    state_files=("work",),
    destructive=False,
    manual_actions=(
        (
            "Existing issues and critical-path items are not converted into work "
            "packets. Create packets deliberately with `studio work add`, stating "
            "the file scope and verification each one is held to."
        ),
    ),
    compatibility_impact=(
        "One new state document is created empty. No existing record changes."
    ),
    scaffold_paths=(".studio/schemas/work.schema.json",),
)
