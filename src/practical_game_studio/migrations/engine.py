"""Planning and applying a scaffold upgrade.

An upgrade is two things at once: framework-managed files are refreshed from the
installed package, and canonical state is carried forward by the migration chain.
Both must land together or not at all, because migrated state is only valid
against the refreshed schemas.

The order here is deliberate. State is migrated in memory and validated against
the *new* schemas staged in a temporary directory before anything in the project
is touched, so a migration that would produce invalid state fails while the
project is still untouched. Only then are managed files replaced, and only then
is state written through :class:`~practical_game_studio.transaction.StateTransaction`,
which renders reports and replaces files atomically. Anything that fails after
the first byte is written restores the snapshot taken beforehand.
"""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import __version__
from ..models import MutationResult, ValidationResult
from ..scaffold import (
    FRAMEWORK_MANIFEST_PATH,
    SCAFFOLD_VERSION,
    ScaffoldResourceError,
    is_protected_path,
    load_scaffold_files,
    render_framework_manifest,
)
from ..state import (
    STATE_FILES,
    CanonicalState,
    StateReadError,
    StateRepository,
    load_json,
)
from ..transaction import StateTransaction, _replace_file, deterministic_json
from ..validation import validate_state
from .registry import Migration, MigrationError, resolve_migration_chain

OPERATION = "framework.upgrade"


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Everything a reviewer needs before agreeing to an upgrade."""

    root: Path
    source_version: str
    target_version: str
    migrations: tuple[Migration, ...]
    affected_files: tuple[str, ...]
    destructive_changes: tuple[str, ...]
    manual_actions: tuple[str, ...]
    compatibility_impact: tuple[str, ...]

    @property
    def up_to_date(self) -> bool:
        """Whether the project already sits at the installed target version."""

        return not self.migrations

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON shape `studio upgrade plan --json` emits."""

        return {
            "root": str(self.root),
            "source_version": self.source_version,
            "target_version": self.target_version,
            "up_to_date": self.up_to_date,
            "migrations": [
                {
                    "id": migration.id,
                    "from_version": migration.from_version,
                    "to_version": migration.to_version,
                    "summary": migration.summary,
                    "destructive": migration.destructive,
                    "state_files": list(migration.state_files),
                }
                for migration in self.migrations
            ],
            "affected_files": list(self.affected_files),
            "destructive_changes": list(self.destructive_changes),
            "manual_actions": list(self.manual_actions),
            "compatibility_impact": list(self.compatibility_impact),
        }


def get_current_version(root: Path) -> str:
    """Read the scaffold version a project was written for."""

    path = root.resolve() / FRAMEWORK_MANIFEST_PATH
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        raise MigrationError("read", f"{path}: expected a JSON object")
    version = manifest.get("scaffold_version")
    if not isinstance(version, str) or not version:
        raise MigrationError("read", f"{path}: missing a scaffold_version string")
    return version


def get_target_version() -> str:
    """The scaffold version the installed package produces."""

    return SCAFFOLD_VERSION


def validate_migrated_state(root: Path, state: CanonicalState) -> ValidationResult:
    """Validate migrated state against the schemas staged under `root`."""

    return validate_state(root, state)


def _managed_scaffold_files(root: Path) -> dict[str, bytes]:
    """Packaged framework files an upgrade refreshes, with the manifest rendered
    for this project so `bootstrapped_at` survives."""

    packaged = load_scaffold_files()
    files = {
        relative: content
        for relative, content in packaged.items()
        if not is_protected_path(relative)
    }
    files[FRAMEWORK_MANIFEST_PATH] = render_framework_manifest(
        packaged[FRAMEWORK_MANIFEST_PATH],
        bootstrapped_at=_bootstrapped_at(root),
        installed_from_version=__version__,
    )
    return files


def _bootstrapped_at(root: Path) -> str:
    path = root / FRAMEWORK_MANIFEST_PATH
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    existing = manifest.get("bootstrapped_at") if isinstance(manifest, dict) else None
    if isinstance(existing, str) and existing:
        return existing
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _apply_chain(
    state: CanonicalState, migrations: tuple[Migration, ...]
) -> CanonicalState:
    migrated = copy.deepcopy(state)
    for migration in migrations:
        try:
            migrated = migration.migrate(migrated)
        except MigrationError:
            raise
        except Exception as exc:
            raise MigrationError(
                f"migration_{migration.id}", f"migration failed: {exc}"
            ) from exc
    return migrated


def plan_migration(root: Path) -> MigrationPlan:
    """Describe the upgrade from a project's recorded version to the target."""

    root = root.resolve()
    source = get_current_version(root)
    target = get_target_version()
    chain = resolve_migration_chain(source, target)

    affected: set[str] = set()
    destructive: list[str] = []
    manual: list[str] = []
    impact: list[str] = []
    for migration in chain:
        affected.update(migration.scaffold_paths)
        affected.update(
            f".studio/state/{_state_filename(name)}" for name in migration.state_files
        )
        if migration.destructive:
            destructive.append(f"{migration.id}: {migration.summary}")
        manual.extend(migration.manual_actions)
        impact.append(f"{migration.id}: {migration.compatibility_impact}")
    if chain:
        affected.add(FRAMEWORK_MANIFEST_PATH)
        affected.update(_refreshed_managed_paths(root))

    return MigrationPlan(
        root=root,
        source_version=source,
        target_version=target,
        migrations=chain,
        affected_files=tuple(sorted(affected)),
        destructive_changes=tuple(destructive),
        manual_actions=tuple(dict.fromkeys(manual)),
        compatibility_impact=tuple(impact),
    )


def _state_filename(name: str) -> str:
    return STATE_FILES[name]


def _state_path(name: str) -> str:
    return f".studio/state/{STATE_FILES[name]}"


def _load_state_for_migration(root: Path) -> CanonicalState:
    """Load canonical state tolerantly, skipping documents that do not exist yet.

    A scaffold version that introduces a state document meets projects that
    predate it, where the file is legitimately absent. Its migration is what
    creates the document, so refusing to load would make the document
    uncreatable. Every other read path still treats a missing state file as an
    error.
    """

    repository = StateRepository(root)
    state: CanonicalState = {}
    for name in STATE_FILES:
        try:
            state[name] = repository.load_one(name)
        except StateReadError as exc:
            if not (root / _state_path(name)).exists():
                continue
            raise MigrationError("load", str(exc)) from exc
    return state


def _assert_complete(state: CanonicalState) -> None:
    """Every state document must exist once the chain has run."""

    missing = sorted(set(STATE_FILES) - set(state))
    if missing:
        raise MigrationError(
            "migration",
            "migrated state is missing document(s): " + ", ".join(missing),
        )


def _missing_state_paths(root: Path) -> dict[str, str]:
    """State files the upgrade must create, mapped to their state name."""

    return {
        _state_path(name): name
        for name in STATE_FILES
        if not (root / _state_path(name)).exists()
    }


def _refreshed_managed_paths(root: Path) -> tuple[str, ...]:
    """Managed files whose packaged bytes differ from what the project has."""

    try:
        managed = _managed_scaffold_files(root)
    except ScaffoldResourceError as exc:
        raise MigrationError("resource", str(exc)) from exc
    changed: list[str] = []
    for relative, content in managed.items():
        try:
            actual = (root / relative).read_bytes()
        except FileNotFoundError:
            changed.append(relative)
            continue
        except OSError as exc:
            raise MigrationError("read", f"{relative}: {exc}") from exc
        if actual != content:
            changed.append(relative)
    return tuple(sorted(changed))


def apply_migration(root: Path, *, dry_run: bool = False) -> MutationResult:
    """Run the resolved migration chain, or describe what running it would do.

    A dry run stages and validates the full result and writes nothing. A real
    run replaces managed files and state, restoring the pre-upgrade snapshot if
    any step fails.
    """

    root = root.resolve()
    plan = plan_migration(root)
    if plan.up_to_date:
        return MutationResult(
            success=True,
            operation=OPERATION,
            changed_files=(),
            unchanged_files=(),
            warnings=(),
            validation_summary={"upgrade": "skipped", "errors": 0},
            report_summary={"rendered": 0, "changed": 0, "unchanged": 0},
            dry_run=dry_run,
            details=plan.to_dict(),
        )

    current_state = _load_state_for_migration(root)
    migrated_state = _apply_chain(current_state, plan.migrations)
    _assert_complete(migrated_state)

    try:
        managed = _managed_scaffold_files(root)
    except ScaffoldResourceError as exc:
        raise MigrationError("resource", str(exc)) from exc

    _validate_against_staged_scaffold(root, managed, migrated_state)

    if dry_run:
        return MutationResult(
            success=True,
            operation=OPERATION,
            changed_files=plan.affected_files,
            unchanged_files=(),
            warnings=(),
            validation_summary={"upgrade": "passed", "errors": 0},
            report_summary={"rendered": 0, "changed": 0, "unchanged": 0},
            dry_run=True,
            details=plan.to_dict(),
        )

    changed_managed = _refreshed_managed_paths(root)
    created_state = _missing_state_paths(root)
    snapshot = {
        relative: _read_optional(root / relative)
        for relative in (*changed_managed, *created_state)
    }
    try:
        for relative in changed_managed:
            _write_managed(root / relative, managed[relative])
        # A migration that introduces a state document must create the file
        # before StateTransaction runs: the transaction snapshots and validates
        # the complete set of state files and cannot open against a missing one.
        # These are in the snapshot as None, so a rollback deletes them.
        for relative, name in created_state.items():
            _write_managed(root / relative, deterministic_json(migrated_state[name]))
        result = _commit_state(root, migrated_state, plan)
    except Exception:
        _restore(root, snapshot)
        raise

    return MutationResult(
        success=True,
        operation=OPERATION,
        changed_files=tuple(sorted({*changed_managed, *result.changed_files})),
        unchanged_files=result.unchanged_files,
        warnings=result.warnings,
        validation_summary=result.validation_summary,
        report_summary=result.report_summary,
        dry_run=False,
        details=plan.to_dict(),
    )


def _validate_against_staged_scaffold(
    root: Path, managed: dict[str, bytes], state: CanonicalState
) -> None:
    """Validate migrated state against the schemas the upgrade will install."""

    with tempfile.TemporaryDirectory(prefix="pgs-upgrade-") as raw:
        staging = Path(raw)
        for relative, content in managed.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        result = validate_migrated_state(staging, state)
    if not result.ok:
        raise MigrationError(
            "validation",
            "migrated state does not satisfy the upgraded schemas: "
            + "; ".join(result.errors),
        )


def _commit_state(
    root: Path, state: CanonicalState, plan: MigrationPlan
) -> MutationResult:
    with StateTransaction(root, operation=OPERATION) as transaction:
        transaction.set_project(state["project"])
        transaction.set_issues(state["issues"])
        transaction.set_decisions(state["decisions"])
        transaction.set_dependencies(state["dependencies"])
        transaction.set_critical_path(state["critical_path"])
        transaction.set_evidence(state["evidence"])
        transaction.set_milestone(state["milestone"])
        transaction.set_runs(state["runs"])
        transaction.set_artifacts(state["artifacts"])
        transaction.set_work(state["work"])
        return transaction.commit(
            warnings=plan.manual_actions,
            details=plan.to_dict(),
        )


def rollback_migration(
    root: Path, snapshot: dict[str, bytes | None]
) -> tuple[str, ...]:
    """Restore files captured before an upgrade, returning what was restored.

    :func:`apply_migration` calls this itself when a step fails. It is public so
    that a caller holding its own snapshot can undo an upgrade the same way.
    """

    return _restore(root.resolve(), snapshot)


def _restore(root: Path, snapshot: dict[str, bytes | None]) -> tuple[str, ...]:
    restored: list[str] = []
    for relative, content in snapshot.items():
        target = root / relative
        if content is None:
            target.unlink(missing_ok=True)
        else:
            _write_managed(target, content)
        restored.append(relative)
    return tuple(sorted(restored))


def _read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MigrationError("read", f"{path}: {exc}") from exc


def _write_managed(target: Path, content: bytes) -> None:
    """Write a managed file through a temporary file so a crash cannot leave a
    half-written schema behind."""

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent,
        prefix=f".{target.name}.pgs-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        temporary = Path(handle.name)
    try:
        _replace_file(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise MigrationError("write", f"{target}: {exc}") from exc
