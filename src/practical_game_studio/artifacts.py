"""Artifact records: files a run produced, and whether they are still what they were.

An artifact is a file the framework can point at — a build log, an export, a
screenshot, a test report. Registering one records its hash and size, so a later
check can tell three different things apart: the file is unchanged, the file was
edited, or the file is gone. A screenshot that silently changed is worse than a
missing one, because only the missing one is obvious.

Like runs, artifacts are facts, not claims. A screenshot proves a frame was
rendered. It does not prove a player understood it.
"""

from __future__ import annotations

import copy
import hashlib
import mimetypes
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MutationResult
from .state import StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

ARTIFACT_ID_PATTERN = re.compile(r"^ART-(\d{4,})$")
ARTIFACT_ID_WIDTH = 4

ARTIFACT_TYPES = (
    "log",
    "build",
    "screenshot",
    "video",
    "test-report",
    "telemetry",
    "profile",
    "export",
    "text",
    "json",
    "other",
)

#: `unverified` means nobody has checked since registration; it is not a claim
#: that the file is fine.
STATUSES = ("present", "missing", "modified", "unverified")

#: Files are hashed in chunks so registering a multi-gigabyte export does not
#: require holding it in memory.
HASH_CHUNK_BYTES = 1024 * 1024


class ArtifactError(ValueError):
    """Base class for a rejected artifact operation."""


class ArtifactInputError(ArtifactError):
    """An artifact was requested with values the caller must correct."""


class ArtifactNotFoundError(ArtifactError):
    """A referenced artifact does not exist."""


@dataclass(frozen=True, slots=True)
class ArtifactCreateRequest:
    """What must be known to register a file as an artifact."""

    type: str
    path: str
    source_run: str | None = None
    description: str | None = None
    revision: str | None = None
    captured_at: str | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ArtifactFilter:
    """Narrowing applied by `studio artifact list`."""

    type: str | None = None
    status: str | None = None
    source_run: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    """The outcome of re-checking one registered artifact against the file."""

    artifact_id: str
    path: str
    status: str
    recorded_sha256: str | None
    actual_sha256: str | None
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "present"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "status": self.status,
            "recorded_sha256": self.recorded_sha256,
            "actual_sha256": self.actual_sha256,
            "detail": self.detail,
        }


def format_artifact_id(number: int) -> str:
    """Render an artifact number as its canonical `ART-####` id."""

    return f"ART-{number:0{ARTIFACT_ID_WIDTH}d}"


def allocate_artifact_id(artifacts: Sequence[StateObject]) -> str:
    """Return the next unused artifact id, never reusing a number."""

    highest = 0
    for artifact in artifacts:
        match = ARTIFACT_ID_PATTERN.match(str(artifact.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return format_artifact_id(highest + 1)


def hash_artifact(path: Path) -> str:
    """Return the SHA-256 of a file, read in chunks."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact(root: Path, stored_path: str) -> Path:
    """Resolve a stored artifact path against the project root.

    Paths are stored relative to the root where possible so a project stays
    portable between machines; an absolute stored path is honoured as given.
    """

    candidate = Path(stored_path)
    return candidate if candidate.is_absolute() else (root / candidate)


def relative_to_root(root: Path, path: Path) -> str:
    """Store a path relative to the project root when it lives inside it."""

    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def verify_artifact(root: Path, artifact: StateObject) -> ArtifactVerification:
    """Re-check one artifact, distinguishing missing from modified.

    A registration made without a hash can only report `unverified`: claiming
    `present` would assert something never checked.
    """

    stored_path = str(artifact.get("path", ""))
    path = resolve_artifact(root, stored_path)
    recorded = artifact.get("sha256")
    if not path.is_file():
        return ArtifactVerification(
            artifact_id=artifact["id"],
            path=stored_path,
            status="missing",
            recorded_sha256=recorded,
            actual_sha256=None,
            detail=f"no file at {path}",
        )
    try:
        actual = hash_artifact(path)
    except OSError as exc:
        return ArtifactVerification(
            artifact_id=artifact["id"],
            path=stored_path,
            status="unverified",
            recorded_sha256=recorded,
            actual_sha256=None,
            detail=f"could not read {path}: {exc}",
        )
    if recorded is None:
        return ArtifactVerification(
            artifact_id=artifact["id"],
            path=stored_path,
            status="unverified",
            recorded_sha256=None,
            actual_sha256=actual,
            detail="registered without a hash; nothing to compare against",
        )
    if actual != recorded:
        return ArtifactVerification(
            artifact_id=artifact["id"],
            path=stored_path,
            status="modified",
            recorded_sha256=recorded,
            actual_sha256=actual,
            detail="file contents changed since registration",
        )
    return ArtifactVerification(
        artifact_id=artifact["id"],
        path=stored_path,
        status="present",
        recorded_sha256=recorded,
        actual_sha256=actual,
        detail="file matches the recorded hash",
    )


def find_artifact(state: StateObject, artifact_id: str) -> StateObject:
    """Return one artifact record or say which id was missing."""

    for artifact in state.get("artifacts", []):
        if artifact.get("id") == artifact_id:
            return artifact
    raise ArtifactNotFoundError(f"artifact {artifact_id} does not exist")


def filter_artifacts(
    artifacts: Sequence[StateObject], criteria: ArtifactFilter
) -> list[StateObject]:
    """Apply list filters, newest first."""

    selected = [
        artifact
        for artifact in artifacts
        if (criteria.type is None or artifact.get("type") == criteria.type)
        and (criteria.status is None or artifact.get("status") == criteria.status)
        and (
            criteria.source_run is None
            or artifact.get("source_run") == criteria.source_run
        )
    ]
    selected.sort(key=lambda artifact: artifact.get("id", ""), reverse=True)
    if criteria.limit is not None:
        selected = selected[: criteria.limit]
    return selected


def _timestamp(clock: Any = None) -> str:
    now = clock() if clock else datetime.now(UTC)
    return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = True) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise ArtifactInputError(f"{field_name} is required")
        return None
    return str(value).strip()


class ArtifactService:
    """Register, inspect, and verify artifacts inside validated transactions."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Any = None,
        report_renderer: ReportRenderer | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repository = StateRepository(self.root)
        self.clock = clock
        self._report_renderer = report_renderer

    def _transaction(self, operation: str, *, dry_run: bool) -> StateTransaction:
        kwargs: dict[str, Any] = {"operation": operation, "dry_run": dry_run}
        if self._report_renderer is not None:
            kwargs["report_renderer"] = self._report_renderer
        return StateTransaction(self.root, **kwargs)

    def add(
        self, request: ArtifactCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        """Register a file, hashing it when it exists.

        A file that is not there is registered as `missing` rather than refused:
        recording that a build was supposed to produce something it did not is
        more useful than recording nothing.
        """

        with self._transaction("artifact.add", dry_run=dry_run) as transaction:
            state = transaction.state
            timestamp = _timestamp(self.clock)
            record = self._build(request, state, timestamp)
            artifacts = copy.deepcopy(state["artifacts"])
            artifacts["artifacts"].append(record)
            transaction.set_artifacts(artifacts)

            details: dict[str, Any] = {
                "artifact": record,
                "artifact_id": record["id"],
                "recommended_next_command": (f"studio artifact show {record['id']}"),
            }
            if record["source_run"] is not None:
                runs = copy.deepcopy(state["runs"])
                for run in runs["runs"]:
                    if run["id"] == record["source_run"]:
                        if record["id"] not in run["artifacts"]:
                            run["artifacts"].append(record["id"])
                        break
                transaction.set_runs(runs)
            return transaction.commit(details=details)

    def verify(
        self, artifact_id: str | None = None
    ) -> tuple[ArtifactVerification, ...]:
        """Re-check one artifact or all of them. Read-only by design.

        Verification reports what it found; it does not rewrite `status`, because
        a check is an observation at a moment, not a new fact about the record.
        `studio artifact verify --record` is the explicit way to store the result.
        """

        state = self.repository.load_artifacts()
        records = (
            [find_artifact(state, artifact_id)]
            if artifact_id is not None
            else list(state["artifacts"])
        )
        return tuple(verify_artifact(self.root, record) for record in records)

    def record_verification(self, *, dry_run: bool = False) -> MutationResult:
        """Store the current verification status of every artifact."""

        with self._transaction("artifact.verify", dry_run=dry_run) as transaction:
            state = transaction.state
            artifacts = copy.deepcopy(state["artifacts"])
            results = []
            for record in artifacts["artifacts"]:
                verification = verify_artifact(self.root, record)
                record["status"] = verification.status
                if verification.status == "present":
                    record["sha256"] = verification.actual_sha256
                results.append(verification.to_dict())
            transaction.set_artifacts(artifacts)
            return transaction.commit(
                details={
                    "verifications": results,
                    "checked": len(results),
                    "problems": sum(item["status"] != "present" for item in results),
                }
            )

    def _build(
        self,
        request: ArtifactCreateRequest,
        state: dict[str, StateObject],
        timestamp: str,
    ) -> StateObject:
        artifact_type = request.type
        if artifact_type not in ARTIFACT_TYPES:
            raise ArtifactInputError(
                f"unsupported artifact type {artifact_type!r}; expected one of "
                + ", ".join(ARTIFACT_TYPES)
            )
        raw_path = _text(request.path, field_name="path")
        source_run = _text(request.source_run, field_name="source run", required=False)
        if source_run is not None:
            known = {run["id"] for run in state["runs"]["runs"]}
            if source_run not in known:
                raise ArtifactInputError(f"unknown source run {source_run}")

        path = resolve_artifact(self.root, raw_path)
        exists = path.is_file()
        return {
            "id": allocate_artifact_id(state["artifacts"]["artifacts"]),
            "type": artifact_type,
            "path": relative_to_root(self.root, path),
            "mime_type": (
                _text(request.mime_type, field_name="mime type", required=False)
                or mimetypes.guess_type(path.name)[0]
            ),
            "sha256": hash_artifact(path) if exists else None,
            "size_bytes": path.stat().st_size if exists else None,
            "source_run": source_run,
            "created_at": timestamp,
            "captured_at": request.captured_at or (timestamp if exists else None),
            "revision": _text(request.revision, field_name="revision", required=False),
            "status": "present" if exists else "missing",
            "description": _text(
                request.description, field_name="description", required=False
            ),
            "metadata": dict(request.metadata or {}),
        }
