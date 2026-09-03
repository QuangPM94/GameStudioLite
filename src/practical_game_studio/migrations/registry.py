"""The ordered chain of scaffold migrations and how to resolve a path through it.

A project records the scaffold version it was written for in
`.studio/framework.json`. The installed package declares the version it can
produce (:data:`practical_game_studio.scaffold.SCAFFOLD_VERSION`). A migration
carries a project's canonical state across exactly one version step, so the work
of upgrading is resolving the chain between those two versions and running each
step in order.

Registering a migration is the only supported way to change the shape of
canonical state. A release that changes state without one leaves existing
projects unupgradeable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..state import CanonicalState

#: A migration receives the whole canonical state and returns the migrated copy.
#: It must not read or write the filesystem: the engine owns staging, validation,
#: and rollback, and a migration that touched disk could not be dry-run.
MigrationFunction = Callable[[CanonicalState], CanonicalState]


class MigrationInputError(ValueError):
    """An upgrade was requested in a way the caller must correct.

    Separate from :class:`MigrationError`, which reports that a migration
    itself could not be resolved or applied. This one maps to the CLI's
    usage exit code, the same as every other command's input error.
    """


class MigrationError(RuntimeError):
    """A migration chain could not be resolved or applied."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


@dataclass(frozen=True, slots=True)
class Migration:
    """One version step, described well enough to review before running it."""

    id: str
    from_version: str
    to_version: str
    summary: str
    migrate: MigrationFunction
    #: Canonical state documents this step rewrites, as `STATE_FILES` keys.
    state_files: tuple[str, ...] = ()
    #: True when the step drops information that cannot be reconstructed.
    destructive: bool = False
    #: Work a person must do; the engine never performs these.
    manual_actions: tuple[str, ...] = ()
    #: What downstream consumers should expect to break or keep working.
    compatibility_impact: str = "No externally observable behaviour changes."
    #: Framework-managed paths this step depends on being refreshed.
    scaffold_paths: tuple[str, ...] = field(default_factory=tuple)


def _load_migrations() -> tuple[Migration, ...]:
    from . import (
        migration_001,
        migration_002,
        migration_003,
        migration_004,
    )

    return (
        migration_001.MIGRATION,
        migration_002.MIGRATION,
        migration_003.MIGRATION,
        migration_004.MIGRATION,
    )


def list_available_migrations() -> tuple[Migration, ...]:
    """Every registered migration, ordered from oldest source version."""

    migrations = _load_migrations()
    _assert_chain_is_well_formed(migrations)
    return migrations


def _assert_chain_is_well_formed(migrations: tuple[Migration, ...]) -> None:
    seen_ids: set[str] = set()
    for index, migration in enumerate(migrations):
        if migration.id in seen_ids:
            raise MigrationError("registry", f"duplicate migration id {migration.id}")
        seen_ids.add(migration.id)
        if migration.from_version == migration.to_version:
            raise MigrationError(
                "registry",
                f"migration {migration.id} does not change the scaffold version",
            )
        if index and migrations[index - 1].to_version != migration.from_version:
            raise MigrationError(
                "registry",
                f"migration {migration.id} starts at {migration.from_version} but "
                f"{migrations[index - 1].id} ends at {migrations[index - 1].to_version}",
            )


def known_versions() -> tuple[str, ...]:
    """Every scaffold version the installed package can recognize, in order."""

    migrations = list_available_migrations()
    if not migrations:
        return ()
    return (migrations[0].from_version, *(step.to_version for step in migrations))


def resolve_migration_chain(
    current_version: str, target_version: str
) -> tuple[Migration, ...]:
    """Return the migrations that carry `current_version` to `target_version`.

    An empty chain means the project is already at the target. A version the
    package does not know, or a project newer than the installed package, is an
    error rather than a silent no-op: guessing either way risks corrupting state.
    """

    versions = known_versions()
    if current_version == target_version:
        if current_version not in versions:
            raise MigrationError(
                "resolve",
                f"unknown scaffold version {current_version!r}; this package knows "
                + ", ".join(versions),
            )
        return ()
    if current_version not in versions:
        raise MigrationError(
            "resolve",
            f"unknown scaffold version {current_version!r}; this package knows "
            + ", ".join(versions),
        )
    if target_version not in versions:
        raise MigrationError(
            "resolve",
            f"unknown target scaffold version {target_version!r}; this package knows "
            + ", ".join(versions),
        )
    if versions.index(current_version) > versions.index(target_version):
        raise MigrationError(
            "resolve",
            f"project scaffold version {current_version} is newer than the installed "
            f"package target {target_version}; upgrade practical-game-studio instead "
            "of downgrading the project",
        )

    chain: list[Migration] = []
    version = current_version
    for migration in list_available_migrations():
        if migration.from_version != version:
            continue
        chain.append(migration)
        version = migration.to_version
        if version == target_version:
            break
    if version != target_version:
        raise MigrationError(
            "resolve",
            f"no migration chain reaches {target_version} from {current_version}",
        )
    return tuple(chain)
