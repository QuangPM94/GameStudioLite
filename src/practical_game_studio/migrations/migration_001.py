"""Scaffold 1.0 -> 1.1: store workflow ids, not slash-command aliases.

Canonical state used to record the recommended next workflow as the string a
human types (`"/start"`). That made presentation syntax load-bearing: the
`GS:<workflow>` invocation form could not be introduced without either
rewriting state or carrying two spellings of the same fact.

After this migration state records the workflow id (`"start"`). `/start` and
`GS:start` are two renderings of that one id, and adding a third costs nothing.
"""

from __future__ import annotations

import copy

from ..state import CanonicalState
from .registry import Migration, MigrationError

LEGACY_FIELD = "recommended_next_playbook"
FIELD = "recommended_next_workflow"


def _workflow_id(value: str) -> str:
    """Return the workflow id for a stored alias, id, or canonical command."""

    candidate = value.strip()
    for prefix in ("GS:", "/"):
        candidate = candidate.removeprefix(prefix)
    return candidate


def migrate(state: CanonicalState) -> CanonicalState:
    """Replace the project's stored alias with the workflow id it names."""

    migrated = copy.deepcopy(state)
    project = migrated["project"]
    if LEGACY_FIELD not in project and FIELD in project:
        return migrated
    if LEGACY_FIELD not in project:
        raise MigrationError(
            "migration_001",
            f"project state has neither {LEGACY_FIELD} nor {FIELD}",
        )
    value = project.pop(LEGACY_FIELD)
    if not isinstance(value, str) or not _workflow_id(value):
        raise MigrationError(
            "migration_001",
            f"{LEGACY_FIELD} must name a workflow; found {value!r}",
        )
    project[FIELD] = _workflow_id(value)
    project["schema_version"] = "1.1"
    return migrated


MIGRATION = Migration(
    id="001",
    from_version="1.0",
    to_version="1.1",
    summary=(
        "Store the recommended next workflow as a workflow id "
        "(recommended_next_workflow) instead of a slash alias "
        "(recommended_next_playbook)."
    ),
    migrate=migrate,
    state_files=("project",),
    destructive=False,
    manual_actions=(
        (
            "Update any external tooling that reads "
            "`.studio/state/project.json` -> `recommended_next_playbook`."
        ),
    ),
    compatibility_impact=(
        "`studio status` prints the same recommended command. `/start` and "
        "`GS:start` both continue to work as agent invocations."
    ),
    scaffold_paths=(".studio/schemas/project.schema.json",),
)
