"""Scaffold and canonical-state migrations.

A project pinned to an older scaffold version must be upgradeable without
force-replacing its files, because those files hold the project's own history.
This package resolves the chain of version steps between what a project has and
what the installed package produces, and applies it as one validated, reversible
operation.

`studio upgrade check | plan | apply` is the entry point; see
:mod:`practical_game_studio.commands.upgrade`.
"""

from __future__ import annotations

from .engine import (
    MigrationPlan,
    apply_migration,
    get_current_version,
    get_target_version,
    plan_migration,
    rollback_migration,
    validate_migrated_state,
)
from .registry import (
    Migration,
    MigrationError,
    MigrationInputError,
    known_versions,
    list_available_migrations,
    resolve_migration_chain,
)

__all__ = [
    "Migration",
    "MigrationError",
    "MigrationInputError",
    "MigrationPlan",
    "apply_migration",
    "get_current_version",
    "get_target_version",
    "known_versions",
    "list_available_migrations",
    "plan_migration",
    "resolve_migration_chain",
    "rollback_migration",
    "validate_migrated_state",
]
