"""Scaffold 1.3 -> 1.4: record how each execution was authorised.

Once an AI agent can start processes on a developer's machine, "who agreed to
this build?" has to be answerable from the record rather than from anyone's
recollection. A run that carries no authorisation is indistinguishable from one
that was never approved.

Runs now carry the risk class they were assigned and how they were authorised.
Runs that predate this migration are marked `unrecorded` rather than backfilled
with a plausible-looking value: inventing an approval nobody gave would defeat
the entire point of keeping the record.
"""

from __future__ import annotations

import copy

from ..state import CanonicalState
from .registry import Migration

#: What a run written before this migration gets. It is deliberately not one of
#: the real authorisation values.
UNRECORDED = "unrecorded"


def migrate(state: CanonicalState) -> CanonicalState:
    """Add risk and authorisation fields to every run record."""

    migrated = copy.deepcopy(state)
    runs = migrated["runs"]
    for record in runs.get("runs", []):
        record.setdefault("risk_level", "low")
        record.setdefault("authorization", UNRECORDED)
    runs["schema_version"] = "1.1"
    return migrated


MIGRATION = Migration(
    id="004",
    from_version="1.3",
    to_version="1.4",
    summary=(
        "Record the risk class and authorisation of every execution run, so "
        "who approved an operation is answerable from the record."
    ),
    migrate=migrate,
    state_files=("runs",),
    destructive=False,
    manual_actions=(
        (
            "Runs recorded before this upgrade are marked authorization="
            f"'{UNRECORDED}'. They are not backfilled, because inventing an "
            "approval nobody gave would defeat the audit trail."
        ),
    ),
    compatibility_impact=(
        "Existing runs keep every recorded field and gain two. Medium-risk "
        "commands (`studio build`, `studio artifact add`, `studio upgrade "
        "apply`) now require confirmation or --yes under guided and strict "
        "review modes."
    ),
    scaffold_paths=(".studio/schemas/runs.schema.json",),
)
