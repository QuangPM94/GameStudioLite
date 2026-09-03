"""Scaffold 1.2 -> 1.3: record what the framework ran and what it produced.

Until now the framework could describe a project's intentions but not its
executions. Nothing in state could answer "did the game actually launch?", so
every runtime claim rested on someone's memory of a terminal.

This migration adds two canonical documents — `runs.json` and `artifacts.json` —
and gives evidence somewhere to point at them. It creates empty documents rather
than inventing history: an upgraded project has no past runs, and pretending
otherwise would be exactly the kind of unfounded claim the framework exists to
prevent.
"""

from __future__ import annotations

import copy

from ..state import CanonicalState
from .registry import Migration

RUNS_DOCUMENT = {"runs": [], "schema_version": "1.0"}
ARTIFACTS_DOCUMENT = {"artifacts": [], "schema_version": "1.0"}


def migrate(state: CanonicalState) -> CanonicalState:
    """Add the execution documents and evidence provenance fields."""

    migrated = copy.deepcopy(state)
    migrated.setdefault("runs", copy.deepcopy(RUNS_DOCUMENT))
    migrated.setdefault("artifacts", copy.deepcopy(ARTIFACTS_DOCUMENT))

    evidence = migrated["evidence"]
    for record in evidence.get("evidence", []):
        record.setdefault("related_runs", [])
        record.setdefault("related_artifacts", [])
    evidence["schema_version"] = "2.1"
    return migrated


MIGRATION = Migration(
    id="003",
    from_version="1.2",
    to_version="1.3",
    summary=(
        "Add runs.json and artifacts.json, and let evidence reference the runs "
        "and artifacts that support it."
    ),
    migrate=migrate,
    state_files=("runs", "artifacts", "evidence"),
    destructive=False,
    manual_actions=(
        (
            "Existing evidence keeps its recorded classification; nothing is "
            "reclassified. Attach runs or artifacts with "
            "`studio evidence update --add-run/--add-artifact` where the provenance "
            "is real."
        ),
    ),
    compatibility_impact=(
        "Two new state documents are created empty. Existing evidence gains two "
        "empty reference lists and is otherwise unchanged."
    ),
    scaffold_paths=(
        ".studio/schemas/runs.schema.json",
        ".studio/schemas/artifacts.schema.json",
        ".studio/schemas/evidence.schema.json",
    ),
)
