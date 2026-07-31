"""Safe lightweight project bootstrap service."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .initialization import InitRequest, initialize_project, is_placeholder_project
from .models import MutationResult
from .scaffold import (
    FRAMEWORK_MANIFEST_PATH,
    FRAMEWORK_NAME,
    MANAGED_PATHS,
    SCAFFOLD_VERSION,
    STARTER_BRIEF_PATH,
    is_protected_path,
    is_replaceable_path,
    load_scaffold_files,
    sha256_bytes,
)
from .transaction import _replace_file
from .validation import validate_project

Clock = Callable[[], datetime]


class BootstrapError(RuntimeError):
    """Bootstrap failed at a named safe-write stage."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


class BootstrapConflictError(BootstrapError):
    """Existing managed files conflict with the packaged scaffold."""

    def __init__(self, conflicts: Iterable[str]) -> None:
        self.conflicts = tuple(sorted(conflicts))
        listing = "\n".join(f"- {path}" for path in self.conflicts)
        super().__init__(
            "conflict",
            "managed scaffold files differ from the packaged scaffold:\n"
            f"{listing}\n"
            "Review the files, or use --force --yes to replace only "
            "framework-managed files.",
        )


class BootstrapConcurrentModificationError(BootstrapError):
    """A target file changed after the complete write plan was calculated."""


@dataclass(frozen=True, slots=True)
class BootstrapRequest:
    """Inputs for attaching PGS to one target game repository."""

    name: str | None = None
    engine: str | None = None
    engine_version: str | None = None
    platform: str | None = None
    genre: str | None = None
    review_mode: str | None = None
    force: bool = False
    dry_run: bool = False
    acknowledged: bool = False

    @property
    def has_identity(self) -> bool:
        return any(
            value is not None
            for value in (
                self.name,
                self.engine,
                self.engine_version,
                self.platform,
                self.genre,
                self.review_mode,
            )
        )


@dataclass(frozen=True, slots=True)
class BootstrapPlan:
    """Complete deterministic classification before any target write."""

    created: tuple[str, ...]
    updated: tuple[str, ...]
    preserved: tuple[str, ...]
    conflicts: tuple[str, ...]
    target_hashes: dict[str, str | None]


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


class BootstrapService:
    """Plan, stage, validate, and safely install a lightweight PGS scaffold."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Clock | None = None,
        scaffold_loader: Callable[[], dict[str, bytes]] = load_scaffold_files,
    ) -> None:
        self.root = root.expanduser().resolve()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._scaffold_loader = scaffold_loader

    def bootstrap(self, request: BootstrapRequest) -> MutationResult:
        if not self.root.is_dir():
            raise BootstrapError(
                "root",
                f"bootstrap root does not exist or is not a directory: {self.root}",
            )

        try:
            packaged = self._scaffold_loader()
        except Exception as exc:
            raise BootstrapError(
                "resource", f"could not load packaged scaffold resources: {exc}"
            ) from exc
        proposed = dict(packaged)
        proposed[FRAMEWORK_MANIFEST_PATH] = self._manifest_content(
            packaged[FRAMEWORK_MANIFEST_PATH]
        )
        proposed[STARTER_BRIEF_PATH] = packaged[".studio/templates/game-brief.md"]
        initial_plan = self._plan(proposed, request)
        if initial_plan.conflicts:
            raise BootstrapConflictError(initial_plan.conflicts)
        if (
            initial_plan.updated
            and request.force
            and not request.dry_run
            and not request.acknowledged
        ):
            raise BootstrapError(
                "confirmation",
                "non-interactive replacement of managed scaffold files requires "
                "--force --yes",
            )

        with tempfile.TemporaryDirectory(
            dir=self.root.parent,
            prefix=f".{self.root.name}.pgs-bootstrap-",
        ) as temporary:
            stage = Path(temporary) / "project"
            stage.mkdir()
            self._build_staged_tree(stage, proposed, initial_plan)

            init_result: MutationResult | None = None
            if request.has_identity:
                staged_project = json.loads(
                    (stage / ".studio/state/project.json").read_text(encoding="utf-8")
                )
                try:
                    init_result = initialize_project(
                        stage,
                        InitRequest(
                            name=request.name,
                            engine=request.engine,
                            engine_version=request.engine_version,
                            platform=request.platform,
                            genre=request.genre,
                            review_mode=request.review_mode,
                            force=request.force
                            and not is_placeholder_project(staged_project),
                            dry_run=False,
                            acknowledged=request.acknowledged,
                        ),
                    )
                except Exception as exc:
                    raise BootstrapError("initialization", str(exc)) from exc

            validation = validate_project(stage)
            if not validation.ok:
                raise BootstrapError(
                    "validation",
                    "staged scaffold is invalid: " + "; ".join(validation.errors),
                )

            final_files = {
                relative: (stage / relative).read_bytes()
                for relative in sorted(proposed)
            }
            final_plan = self._plan_final(final_files)
            if not request.dry_run and (final_plan.created or final_plan.updated):
                self._assert_initial_plan_unchanged(initial_plan)
                self._apply_outputs(final_files, final_plan)

        project = json.loads(final_files[".studio/state/project.json"].decode("utf-8"))
        initialized = not is_placeholder_project(project)
        next_command = (
            "studio status" if initialized else 'studio init --name "Project Name"'
        )
        warnings = tuple(init_result.warnings) if init_result else ()
        return MutationResult(
            success=True,
            operation="project.bootstrap",
            changed_files=(*final_plan.created, *final_plan.updated),
            unchanged_files=final_plan.preserved,
            warnings=warnings,
            validation_summary={
                "project": "passed",
                "errors": 0,
                "conflicts": 0,
            },
            report_summary={
                "rendered": 5 if init_result else 0,
                "validated": 5,
            },
            dry_run=request.dry_run,
            changed_fields=init_result.changed_fields if init_result else {},
            details={
                "root": str(self.root),
                "starter_brief_path": str(self.root / STARTER_BRIEF_PATH),
                "created_count": len(final_plan.created),
                "updated_count": len(final_plan.updated),
                "preserved_count": len(final_plan.preserved),
                "conflict_count": 0,
                "initialized": initialized,
                "recommended_next_command": next_command,
            },
        )

    def _manifest_content(self, template: bytes) -> bytes:
        try:
            packaged = json.loads(template.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError(
                "resource", f"invalid packaged framework manifest: {exc}"
            ) from exc
        if not isinstance(packaged, dict):
            raise BootstrapError(
                "resource", "packaged framework manifest must be a JSON object"
            )
        existing_path = self.root / FRAMEWORK_MANIFEST_PATH
        bootstrapped_at: str | None = None
        if existing_path.is_file():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if isinstance(existing, dict) and isinstance(
                existing.get("bootstrapped_at"), str
            ):
                bootstrapped_at = existing["bootstrapped_at"]
        packaged.update(
            {
                "framework": FRAMEWORK_NAME,
                "scaffold_version": SCAFFOLD_VERSION,
                "installed_from_version": __version__,
                "bootstrapped_at": bootstrapped_at or _utc_timestamp(self._clock()),
                "managed_paths": list(MANAGED_PATHS),
            }
        )
        return _json_bytes(packaged)

    def _plan(
        self, proposed: dict[str, bytes], request: BootstrapRequest
    ) -> BootstrapPlan:
        created: list[str] = []
        updated: list[str] = []
        preserved: list[str] = []
        conflicts: list[str] = []
        hashes: dict[str, str | None] = {}
        for relative in sorted(proposed):
            path = self.root / relative
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                actual = None
            except OSError as exc:
                raise BootstrapError("inspection", f"{path}: {exc}") from exc
            hashes[relative] = sha256_bytes(actual) if actual is not None else None
            if actual is None:
                created.append(relative)
            elif actual == proposed[relative] or is_protected_path(relative):
                preserved.append(relative)
            elif request.force and is_replaceable_path(relative):
                updated.append(relative)
            else:
                conflicts.append(relative)
        return BootstrapPlan(
            tuple(created),
            tuple(updated),
            tuple(preserved),
            tuple(conflicts),
            hashes,
        )

    def _build_staged_tree(
        self,
        stage: Path,
        proposed: dict[str, bytes],
        plan: BootstrapPlan,
    ) -> None:
        preserved = set(plan.preserved)
        for relative in sorted(proposed):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source = self.root / relative
            try:
                content = (
                    source.read_bytes() if relative in preserved else proposed[relative]
                )
                target.write_bytes(content)
            except OSError as exc:
                raise BootstrapError("stage", f"{relative}: {exc}") from exc
        self._copy_engine_indicators(stage)

    def _copy_engine_indicators(self, stage: Path) -> None:
        for directory in ("Assets", "ProjectSettings"):
            if (self.root / directory).is_dir():
                (stage / directory).mkdir(exist_ok=True)
        for source in [
            self.root / "project.godot",
            *sorted(self.root.glob("*.uproject"), key=lambda path: path.name),
        ]:
            if source.is_file():
                try:
                    (stage / source.name).write_bytes(source.read_bytes())
                except OSError as exc:
                    raise BootstrapError(
                        "stage", f"could not copy engine indicator {source.name}: {exc}"
                    ) from exc

    def _plan_final(self, final_files: dict[str, bytes]) -> BootstrapPlan:
        created: list[str] = []
        updated: list[str] = []
        preserved: list[str] = []
        hashes: dict[str, str | None] = {}
        for relative in sorted(final_files):
            path = self.root / relative
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                actual = None
            except OSError as exc:
                raise BootstrapError("inspection", f"{path}: {exc}") from exc
            hashes[relative] = sha256_bytes(actual) if actual is not None else None
            if actual is None:
                created.append(relative)
            elif actual == final_files[relative]:
                preserved.append(relative)
            else:
                updated.append(relative)
        return BootstrapPlan(
            tuple(created),
            tuple(updated),
            tuple(preserved),
            (),
            hashes,
        )

    def _assert_initial_plan_unchanged(self, plan: BootstrapPlan) -> None:
        for relative, expected in plan.target_hashes.items():
            path = self.root / relative
            try:
                actual_content = path.read_bytes()
            except FileNotFoundError:
                actual_content = None
            except OSError as exc:
                raise BootstrapConcurrentModificationError(
                    "concurrent-modification",
                    f"{relative} became unreadable: {exc}. Reload and retry.",
                ) from exc
            actual = (
                sha256_bytes(actual_content) if actual_content is not None else None
            )
            if actual != expected:
                raise BootstrapConcurrentModificationError(
                    "concurrent-modification",
                    f"{relative} changed after the bootstrap plan was calculated. "
                    "Reload and retry.",
                )

    def _apply_outputs(
        self, final_files: dict[str, bytes], plan: BootstrapPlan
    ) -> None:
        changed = (*plan.created, *plan.updated)
        originals: dict[str, bytes | None] = {}
        for relative in changed:
            try:
                originals[relative] = (self.root / relative).read_bytes()
            except FileNotFoundError:
                originals[relative] = None
            except OSError as exc:
                raise BootstrapError("read-output", f"{relative}: {exc}") from exc

        replaced: list[str] = []
        temporary_paths: set[Path] = set()
        created_directories: set[Path] = set()
        try:
            for relative in changed:
                target = self.root / relative
                self._create_parent_directories(target.parent, created_directories)
                expected_original = originals[relative]
                try:
                    current = target.read_bytes()
                except FileNotFoundError:
                    current = None
                if current != expected_original:
                    raise BootstrapConcurrentModificationError(
                        "concurrent-modification",
                        f"{relative} changed before replacement. Reload and retry.",
                    )
                temporary = self._write_temporary(target, final_files[relative])
                temporary_paths.add(temporary)
                _replace_file(temporary, target)
                temporary_paths.discard(temporary)
                replaced.append(relative)
        except Exception as exc:
            rollback_errors = self._rollback(
                replaced, originals, temporary_paths, created_directories
            )
            if rollback_errors:
                raise BootstrapError(
                    "rollback",
                    f"bootstrap write failed ({exc}); rollback also failed: "
                    + "; ".join(rollback_errors),
                ) from exc
            if isinstance(exc, BootstrapError):
                raise
            raise BootstrapError(
                "replace",
                f"{exc}; newly created files were removed and replaced managed "
                "files were restored",
            ) from exc
        finally:
            for path in temporary_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _create_parent_directories(
        parent: Path, created_directories: set[Path]
    ) -> None:
        missing: list[Path] = []
        current = parent
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir()
            created_directories.add(directory)

    @staticmethod
    def _write_temporary(target: Path, content: bytes) -> Path:
        try:
            descriptor, raw_path = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.pgs-bootstrap-",
                suffix=".tmp",
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return Path(raw_path)
        except OSError as exc:
            raise BootstrapError("temporary-write", f"{target}: {exc}") from exc

    def _rollback(
        self,
        replaced: list[str],
        originals: dict[str, bytes | None],
        temporary_paths: set[Path],
        created_directories: set[Path],
    ) -> list[str]:
        errors: list[str] = []
        for path in tuple(temporary_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
            temporary_paths.discard(path)
        for relative in reversed(replaced):
            target = self.root / relative
            original = originals[relative]
            try:
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    temporary = self._write_temporary(target, original)
                    _replace_file(temporary, target)
            except (OSError, BootstrapError) as exc:
                errors.append(f"{relative}: {exc}")
        for directory in sorted(
            created_directories, key=lambda path: len(path.parts), reverse=True
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        return errors
