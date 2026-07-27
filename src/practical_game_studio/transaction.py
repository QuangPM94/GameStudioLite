"""Validated copy-on-write transactions for canonical PGS state."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from .models import MutationResult
from .reporting import REPORT_RENDERERS, render_report_contents
from .state import (
    STATE_FILES,
    CanonicalState,
    StateObject,
    StateReadError,
    StateRepository,
)
from .validation import validate_state

ReportRenderer = Callable[[CanonicalState], dict[str, str]]
WINDOWS_REPLACE_ATTEMPTS = 5
WINDOWS_REPLACE_DELAY_SECONDS = 0.01


class TransactionError(RuntimeError):
    """A transaction failed at a named stage."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


class ConcurrentModificationError(TransactionError):
    """Canonical state changed after the transaction loaded it."""


def deterministic_json(value: StateObject) -> bytes:
    """Serialize canonical JSON with stable ordering and a final newline."""

    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _replace_file(source: Path, target: Path) -> None:
    """Replace a file, tolerating brief Windows scanner/indexer locks."""

    for attempt in range(WINDOWS_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 == WINDOWS_REPLACE_ATTEMPTS:
                raise
            time.sleep(WINDOWS_REPLACE_DELAY_SECONDS)


class StateTransaction:
    """Validate, render, stage, and replace a local multi-file state mutation."""

    def __init__(
        self,
        root: Path,
        *,
        operation: str = "state-mutation",
        dry_run: bool = False,
        report_renderer: ReportRenderer = render_report_contents,
    ) -> None:
        self.root = root.resolve()
        self.operation = operation
        self.dry_run = dry_run
        self._report_renderer = report_renderer
        self._repository = StateRepository(self.root)
        self._original: CanonicalState | None = None
        self._working: CanonicalState | None = None
        self._state_hashes: dict[Path, str] = {}
        self._dirty: set[str] = set()
        self._temporary_paths: set[Path] = set()
        self._committed = False

    def __enter__(self) -> Self:
        try:
            before_load = self._snapshot_state_hashes()
            self._original = self._repository.load_all()
            self._working = copy.deepcopy(self._original)
            after_load = self._snapshot_state_hashes()
            if before_load != after_load:
                changed = next(
                    path
                    for path in before_load
                    if before_load[path] != after_load[path]
                )
                raise ConcurrentModificationError(
                    "concurrent-modification",
                    f"{changed} changed while the transaction loaded state. "
                    "Reload and retry.",
                )
            self._state_hashes = after_load
        except (OSError, StateReadError) as exc:
            raise TransactionError("load", str(exc)) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._cleanup_temporaries()

    @property
    def state(self) -> CanonicalState:
        """Return an isolated copy of the proposed state."""

        self._require_entered()
        return copy.deepcopy(self._working)

    def _set(self, name: str, value: StateObject) -> None:
        self._require_entered()
        if not isinstance(value, dict):
            raise TypeError(f"{name} state must be a dictionary")
        self._working[name] = copy.deepcopy(value)
        self._dirty.add(name)

    def set_project(self, value: StateObject) -> None:
        self._set("project", value)

    def set_issues(self, value: StateObject) -> None:
        self._set("issues", value)

    def set_decisions(self, value: StateObject) -> None:
        self._set("decisions", value)

    def set_dependencies(self, value: StateObject) -> None:
        self._set("dependencies", value)

    def set_critical_path(self, value: StateObject) -> None:
        self._set("critical_path", value)

    def set_evidence(self, value: StateObject) -> None:
        self._set("evidence", value)

    def set_milestone(self, value: StateObject) -> None:
        self._set("milestone", value)

    def commit(
        self,
        *,
        warnings: Iterable[str] = (),
        changed_fields: dict[str, dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> MutationResult:
        """Commit the proposed state or return its dry-run result."""

        self._require_entered()
        if self._committed:
            raise TransactionError("commit", "transaction has already been committed")

        self._assert_state_unchanged()
        validation = validate_state(self.root, self._working)
        if not validation.ok:
            joined = "; ".join(validation.errors)
            raise TransactionError("validation", joined)

        try:
            reports = self._report_renderer(copy.deepcopy(self._working))
            expected_names = set(REPORT_RENDERERS)
            if set(reports) != expected_names:
                missing = sorted(expected_names - set(reports))
                extra = sorted(set(reports) - expected_names)
                raise ValueError(
                    f"report set mismatch; missing={missing}, extra={extra}"
                )
            report_bytes = {
                name: content.encode("utf-8") for name, content in reports.items()
            }
        except Exception as exc:
            raise TransactionError("report-render", str(exc)) from exc

        outputs = self._build_outputs(report_bytes)
        changed = [
            path for path, content in outputs if self._read_optional(path) != content
        ]
        all_paths = self._all_managed_paths()
        changed_set = set(changed)
        unchanged = [path for path in all_paths if path not in changed_set]
        report_paths = {
            self.root / ".studio" / "reports" / name for name in REPORT_RENDERERS
        }
        result = MutationResult(
            success=True,
            operation=self.operation,
            changed_files=tuple(self._relative(path) for path in changed),
            unchanged_files=tuple(self._relative(path) for path in unchanged),
            warnings=tuple(warnings),
            validation_summary={
                "schemas": len(STATE_FILES),
                "relationships": "passed",
                "errors": 0,
            },
            report_summary={
                "rendered": len(REPORT_RENDERERS),
                "changed": sum(path in report_paths for path in changed),
                "unchanged": sum(path in report_paths for path in unchanged),
            },
            dry_run=self.dry_run,
            changed_fields=changed_fields or {},
            details=details or {},
        )

        if self.dry_run or not changed:
            self._committed = True
            return result

        originals = {path: self._read_optional(path) for path in changed}
        staged: dict[Path, Path] = {}
        try:
            for target, content in outputs:
                if target in changed_set:
                    staged[target] = self._write_temporary(target, content)
            self._assert_state_unchanged()
            self._replace_with_rollback(staged, originals)
        except ConcurrentModificationError:
            raise
        except TransactionError:
            raise
        except Exception as exc:
            raise TransactionError("stage", str(exc)) from exc
        finally:
            self._cleanup_temporaries()

        self._committed = True
        return result

    def _require_entered(self) -> None:
        if self._working is None or self._original is None:
            raise TransactionError(
                "transaction", "use StateTransaction as a context manager"
            )

    def _state_path(self, name: str) -> Path:
        return self.root / ".studio" / "state" / STATE_FILES[name]

    def _snapshot_state_hashes(self) -> dict[Path, str]:
        snapshots: dict[Path, str] = {}
        for name in STATE_FILES:
            path = self._state_path(name)
            try:
                snapshots[path] = _digest(path.read_bytes())
            except OSError as exc:
                raise StateReadError(
                    f"{path}: could not snapshot state: {exc}"
                ) from exc
        return snapshots

    def _assert_state_unchanged(self) -> None:
        for path, expected in self._state_hashes.items():
            try:
                actual = _digest(path.read_bytes())
            except OSError as exc:
                raise ConcurrentModificationError(
                    "concurrent-modification",
                    f"{path} became unreadable or missing: {exc}. Reload and retry.",
                ) from exc
            if actual != expected:
                raise ConcurrentModificationError(
                    "concurrent-modification",
                    f"{path} changed after the transaction loaded it. Reload and retry.",
                )

    def _build_outputs(
        self, report_bytes: dict[str, bytes]
    ) -> list[tuple[Path, bytes]]:
        outputs = [
            (self._state_path(name), deterministic_json(self._working[name]))
            for name in STATE_FILES
            if name in self._dirty
        ]
        if self._dirty:
            outputs.extend(
                (
                    self.root / ".studio" / "reports" / name,
                    report_bytes[name],
                )
                for name in REPORT_RENDERERS
            )
        return outputs

    def _all_managed_paths(self) -> list[Path]:
        paths = [self._state_path(name) for name in STATE_FILES]
        paths.extend(
            self.root / ".studio" / "reports" / name for name in REPORT_RENDERERS
        )
        return paths

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def _read_optional(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise TransactionError("read-output", f"{path}: {exc}") from exc

    def _write_temporary(self, target: Path, content: bytes) -> Path:
        try:
            descriptor, raw_path = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.pgs-",
                suffix=".tmp",
            )
            path = Path(raw_path)
            self._temporary_paths.add(path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return path
        except OSError as exc:
            raise TransactionError("temporary-write", f"{target}: {exc}") from exc

    def _replace_with_rollback(
        self, staged: dict[Path, Path], originals: dict[Path, bytes | None]
    ) -> None:
        replaced: list[Path] = []
        try:
            for target, temporary in staged.items():
                _replace_file(temporary, target)
                self._temporary_paths.discard(temporary)
                replaced.append(target)
        except OSError as exc:
            rollback_errors: list[str] = []
            for target in reversed(replaced):
                try:
                    self._restore_target(target, originals[target])
                except (OSError, TransactionError) as rollback_exc:
                    rollback_errors.append(f"{target}: {rollback_exc}")
            if rollback_errors:
                raise TransactionError(
                    "rollback",
                    f"replace failed ({exc}); rollback also failed: "
                    + "; ".join(rollback_errors),
                ) from exc
            raise TransactionError(
                "replace", f"{exc}; previously replaced outputs were rolled back"
            ) from exc

    def _restore_target(self, target: Path, original: bytes | None) -> None:
        if original is None:
            target.unlink(missing_ok=True)
            return
        temporary = self._write_temporary(target, original)
        _replace_file(temporary, target)
        self._temporary_paths.discard(temporary)

    def _cleanup_temporaries(self) -> None:
        for path in tuple(self._temporary_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            self._temporary_paths.discard(path)
