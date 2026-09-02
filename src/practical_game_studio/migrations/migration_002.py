"""Scaffold 1.1 -> 1.2: give milestones stable ids separate from their titles.

A milestone used to be identified by its display title. Renaming "Clarify the
game idea" therefore silently orphaned every criterion, critical-path snapshot,
and history entry that named the old string, and nothing could detect it.

After this migration `milestone.json` carries a registry of milestones with
`MS-####` ids, and every reference records the id alongside the title. Titles
stay exactly where they are and stay the thing humans read: the id is what
survives a rename.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

from ..state import CanonicalState
from .registry import Migration, MigrationError

ID_PREFIX = "MS-"
ID_WIDTH = 4


def format_milestone_id(number: int) -> str:
    """Render a milestone number as its canonical `MS-####` id."""

    return f"{ID_PREFIX}{number:0{ID_WIDTH}d}"


def _titles_in_reference_order(state: CanonicalState) -> Iterator[str]:
    """Yield every milestone title, current one first, then in a stable order.

    Order decides which title gets MS-0001, so it must not depend on dict
    iteration luck: the same project must migrate to the same ids on every
    machine.
    """

    milestone = state["milestone"]
    project = state["project"]
    critical_path = state["critical_path"]

    yield project.get("current_milestone")
    yield milestone.get("milestone")
    yield critical_path.get("current_milestone")
    yield milestone.get("next_milestone")

    trailing: set[str] = set()
    for criterion in milestone.get("criteria_results", []):
        for title in (criterion.get("milestone"), *_history_titles(criterion)):
            if isinstance(title, str) and title:
                trailing.add(title)
    yield from sorted(trailing)


def _history_titles(criterion: dict[str, Any]) -> Iterator[str]:
    for entry in criterion.get("milestone_history", []):
        yield entry.get("from")
        yield entry.get("to")


def assign_milestone_ids(state: CanonicalState) -> dict[str, str]:
    """Map each milestone title in the project to a newly allocated stable id."""

    ids: dict[str, str] = {}
    for title in _titles_in_reference_order(state):
        if not isinstance(title, str) or not title or title in ids:
            continue
        ids[title] = format_milestone_id(len(ids) + 1)
    if not ids:
        raise MigrationError(
            "migration_002", "project state names no milestone to assign an id to"
        )
    return ids


def _registry_entry(
    identifier: str, title: str, *, current_title: str | None, timestamp: str
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "status": "current" if title == current_title else "known",
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _earliest_timestamp(state: CanonicalState) -> str:
    """Reuse the oldest recorded criterion timestamp so ids are not back-dated
    to the moment of the upgrade, which would misrepresent project history."""

    stamps = [
        criterion["created_at"]
        for criterion in state["milestone"].get("criteria_results", [])
        if isinstance(criterion.get("created_at"), str)
    ]
    return min(stamps) if stamps else "1970-01-01T00:00:00Z"


def migrate(state: CanonicalState) -> CanonicalState:
    """Add the milestone registry and stable id references."""

    migrated = copy.deepcopy(state)
    milestone = migrated["milestone"]
    if "milestones" in milestone:
        return migrated

    ids = assign_milestone_ids(migrated)
    current_title = milestone.get("milestone")
    timestamp = _earliest_timestamp(migrated)

    milestone["milestones"] = [
        _registry_entry(
            ids[title], title, current_title=current_title, timestamp=timestamp
        )
        for title in sorted(ids, key=lambda item: ids[item])
    ]
    milestone["milestone_id"] = ids.get(current_title)
    next_title = milestone.get("next_milestone")
    milestone["next_milestone_id"] = ids.get(next_title) if next_title else None
    for criterion in milestone.get("criteria_results", []):
        criterion["milestone_id"] = ids.get(criterion.get("milestone"))
    milestone["schema_version"] = "3.2"

    project = migrated["project"]
    project["current_milestone_id"] = ids.get(project.get("current_milestone"))
    project["schema_version"] = "1.2"

    critical_path = migrated["critical_path"]
    critical_path["current_milestone_id"] = ids.get(
        critical_path.get("current_milestone")
    )
    critical_path["schema_version"] = "3.1"
    return migrated


MIGRATION = Migration(
    id="002",
    from_version="1.1",
    to_version="1.2",
    summary=(
        "Add MS-#### milestone ids and a milestone registry so milestone "
        "references survive a title rename."
    ),
    migrate=migrate,
    state_files=("milestone", "project", "critical_path"),
    destructive=False,
    manual_actions=(
        (
            "Review `.studio/state/milestone.json` -> `milestones` and confirm "
            "each assigned id names the milestone you expect."
        ),
    ),
    compatibility_impact=(
        "Milestone titles are unchanged and remain the displayed value. "
        "Reports and `studio status` gain the id alongside the title."
    ),
    scaffold_paths=(
        ".studio/schemas/milestone.schema.json",
        ".studio/schemas/project.schema.json",
        ".studio/schemas/critical-path.schema.json",
    ),
)
