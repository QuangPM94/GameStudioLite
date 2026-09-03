"""The milestone registry: stable `MS-####` ids for milestone titles.

A milestone is a thing a project works toward, and its title is how people talk
about it. Those are not the same fact. Before this registry existed the title
was also the identifier, so renaming a milestone silently detached every
criterion, critical-path snapshot, and history entry that named the old string.

`milestone.json` now carries a `milestones` list mapping each title to an id
allocated once and never reused. References record the id; displays keep showing
the title. Anything that needs to name a milestone in state goes through
:func:`resolve_milestone_id`, which registers a title the first time it is seen.
"""

from __future__ import annotations

import re
from typing import Any

from .state import StateObject

ID_PREFIX = "MS-"
ID_WIDTH = 4
ID_PATTERN = re.compile(r"^MS-(\d{4,})$")

MilestoneRecord = dict[str, Any]


def format_milestone_id(number: int) -> str:
    """Render a milestone number as its canonical `MS-####` id."""

    return f"{ID_PREFIX}{number:0{ID_WIDTH}d}"


def allocate_milestone_id(records: list[MilestoneRecord]) -> str:
    """Return the next unused id, continuing past the highest ever allocated.

    Ids are never reused, even when a milestone is retired, so a stale reference
    fails to resolve instead of silently pointing at a different milestone.
    """

    highest = 0
    for record in records:
        match = ID_PATTERN.match(str(record.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return format_milestone_id(highest + 1)


def find_milestone_id(records: list[MilestoneRecord], title: str) -> str | None:
    """Return the id registered for `title`, or None when it is not registered."""

    for record in records:
        if record.get("title") == title:
            identifier = record.get("id")
            return identifier if isinstance(identifier, str) else None
    return None


def resolve_milestone_id(
    milestone_state: StateObject, title: str, *, timestamp: str
) -> str:
    """Return the id for `title`, registering it if this is its first mention.

    Mutates `milestone_state["milestones"]` in place: callers are already inside
    a :class:`~practical_game_studio.transaction.StateTransaction` working copy,
    so registering a milestone is part of the same validated write.
    """

    records = milestone_state.setdefault("milestones", [])
    existing = find_milestone_id(records, title)
    if existing is not None:
        return existing
    identifier = allocate_milestone_id(records)
    records.append(
        {
            "id": identifier,
            "title": title,
            "status": "known",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    return identifier


def milestone_title(milestone_state: StateObject, identifier: str | None) -> str | None:
    """Return the display title an id names, or None when it is unregistered."""

    if identifier is None:
        return None
    for record in milestone_state.get("milestones", []):
        if record.get("id") == identifier:
            title = record.get("title")
            return title if isinstance(title, str) else None
    return None


def set_current_milestone(
    milestone_state: StateObject, title: str, *, timestamp: str
) -> str:
    """Mark `title` as the project's current milestone and return its id."""

    identifier = resolve_milestone_id(milestone_state, title, timestamp=timestamp)
    for record in milestone_state.get("milestones", []):
        was_current = record.get("status") == "current"
        is_current = record.get("id") == identifier
        if was_current == is_current:
            continue
        record["status"] = "current" if is_current else "known"
        record["updated_at"] = timestamp
    milestone_state["milestone_id"] = identifier
    return identifier
