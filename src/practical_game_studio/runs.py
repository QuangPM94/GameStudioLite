"""Execution run records: what the framework actually ran, and what happened.

A RUN is a factual record of one process the framework executed on the project's
behalf — a build, a test suite, a headless launch. It says what command ran, when,
where, and how it ended.

A RUN is deliberately *not* evidence. "The engine exited 0" is a fact about a
process; "the prototype is playable" is a claim about a game. Turning the first
into the second is a judgement an agent or a person makes explicitly, by creating
evidence that references the run. Nothing in this module makes that leap.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import MutationResult
from .state import StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

RUN_ID_PATTERN = re.compile(r"^RUN-(\d{4,})$")
RUN_ID_WIDTH = 4

#: What the framework was trying to do. Kept closed so reports and readiness
#: checks can reason about a run without parsing its command line.
ACTIONS = (
    "doctor",
    "run",
    "test",
    "build",
    "verify",
    "export",
    "capture",
    "custom",
)

#: `unknown` is not a synonym for `failed`. A run whose result could not be
#: determined must stay distinguishable from one that determined a failure,
#: because only the second is grounds for an issue.
STATUSES = ("pending", "running", "passed", "failed", "cancelled", "unknown")
TERMINAL_STATUSES = ("passed", "failed", "cancelled", "unknown")

#: Long output belongs in an artifact, not in canonical state. Summaries are
#: truncated so `runs.json` stays reviewable in a diff.
SUMMARY_LIMIT = 2000


class RunError(ValueError):
    """Base class for a rejected run-record operation."""


class RunInputError(RunError):
    """A run record was requested with values the caller must correct."""


class RunNotFoundError(RunError):
    """A referenced run does not exist."""


@dataclass(frozen=True, slots=True)
class RunCreateRequest:
    """The facts known when a run starts, before its result exists."""

    action: str
    command: Sequence[str] = ()
    adapter: str | None = None
    provider: str | None = None
    working_directory: str | None = None
    revision: str | None = None
    engine: str | None = None
    engine_version: str | None = None
    platform: str | None = None
    limitations: Sequence[str] = ()
    #: How this execution was classified and authorised. Defaults describe
    #: an operation that needed no approval; a caller that gated the run
    #: passes what the safety layer actually decided.
    risk_level: str = "low"
    authorization: str = "risk-below-threshold"


@dataclass(frozen=True, slots=True)
class RunResult:
    """The facts known when a run ends."""

    status: str
    exit_code: int | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    duration_ms: int | None = None
    artifacts: Sequence[str] = ()
    limitations: Sequence[str] = ()
    completed_at: str | None = None


@dataclass(frozen=True, slots=True)
class RunFilter:
    """Narrowing applied by `studio execution list`."""

    action: str | None = None
    status: str | None = None
    adapter: str | None = None
    limit: int | None = None


def format_run_id(number: int) -> str:
    """Render a run number as its canonical `RUN-####` id."""

    return f"RUN-{number:0{RUN_ID_WIDTH}d}"


def allocate_run_id(runs: Sequence[StateObject]) -> str:
    """Return the next unused run id, never reusing a retired number."""

    highest = 0
    for run in runs:
        match = RUN_ID_PATTERN.match(str(run.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return format_run_id(highest + 1)


def summarize_output(text: str | None, *, limit: int = SUMMARY_LIMIT) -> str | None:
    """Truncate captured output for state, naming the truncation in the text.

    Silently cutting output would let a reader mistake a fragment for the whole
    thing, so the marker is part of the stored value.
    """

    if text is None:
        return None
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return text[:limit] + f"\n... [{dropped} characters truncated; see run artifacts]"


def _timestamp(clock: Any = None) -> str:
    now = clock() if clock else datetime.now(UTC)
    return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = True) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise RunInputError(f"{field_name} is required")
        return None
    return str(value).strip()


def _unique_strings(values: Sequence[str], *, field_name: str) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = _text(value, field_name=field_name)
        if text is not None and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _action(value: str) -> str:
    if value not in ACTIONS:
        raise RunInputError(
            f"unsupported action {value!r}; expected one of " + ", ".join(ACTIONS)
        )
    return value


def _status(value: str) -> str:
    if value not in STATUSES:
        raise RunInputError(
            f"unsupported status {value!r}; expected one of " + ", ".join(STATUSES)
        )
    return value


def find_run(state: StateObject, run_id: str) -> StateObject:
    """Return one run record or say which id was missing."""

    for run in state.get("runs", []):
        if run.get("id") == run_id:
            return run
    raise RunNotFoundError(f"run {run_id} does not exist")


def filter_runs(runs: Sequence[StateObject], criteria: RunFilter) -> list[StateObject]:
    """Apply list filters, newest first."""

    selected = [
        run
        for run in runs
        if (criteria.action is None or run.get("action") == criteria.action)
        and (criteria.status is None or run.get("status") == criteria.status)
        and (criteria.adapter is None or run.get("adapter") == criteria.adapter)
    ]
    selected.sort(key=lambda run: run.get("id", ""), reverse=True)
    if criteria.limit is not None:
        selected = selected[: criteria.limit]
    return selected


class RunService:
    """Create and complete run records inside validated state transactions."""

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

    def create(
        self, request: RunCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        """Open a run record in `running` state before the process starts.

        The record exists before the result does on purpose: a process that is
        killed, hangs, or crashes the host still leaves a trace saying what was
        attempted.
        """

        with self._transaction("execution.create", dry_run=dry_run) as transaction:
            state = transaction.state
            timestamp = _timestamp(self.clock)
            record = self._build(request, timestamp, state["runs"]["runs"])
            runs = copy.deepcopy(state["runs"])
            runs["runs"].append(record)
            transaction.set_runs(runs)
            return transaction.commit(
                details={
                    "run": record,
                    "run_id": record["id"],
                    "recommended_next_command": f"studio execution show {record['id']}",
                }
            )

    def complete(
        self, run_id: str, result: RunResult, *, dry_run: bool = False
    ) -> MutationResult:
        """Record how a run ended, including a result nobody could determine."""

        with self._transaction("execution.complete", dry_run=dry_run) as transaction:
            state = transaction.state
            runs = copy.deepcopy(state["runs"])
            record = find_run(runs, run_id)
            if record["status"] in TERMINAL_STATUSES:
                raise RunInputError(
                    f"{run_id} already completed with status {record['status']}"
                )
            timestamp = result.completed_at or _timestamp(self.clock)
            self._apply_result(record, result, timestamp)
            transaction.set_runs(runs)
            return transaction.commit(
                details={
                    "run": record,
                    "run_id": run_id,
                    "status": record["status"],
                    "recommended_next_command": f"studio execution show {run_id}",
                }
            )

    def _apply_result(
        self, record: StateObject, result: RunResult, timestamp: str
    ) -> None:
        record["status"] = _status(result.status)
        record["exit_code"] = result.exit_code
        record["stdout_summary"] = summarize_output(result.stdout_summary)
        record["stderr_summary"] = summarize_output(result.stderr_summary)
        record["completed_at"] = timestamp
        record["duration_ms"] = self._duration(record, result, timestamp)
        record["artifacts"] = _unique_strings(
            list(record["artifacts"]) + list(result.artifacts), field_name="artifact"
        )
        record["limitations"] = _unique_strings(
            list(record["limitations"]) + list(result.limitations),
            field_name="limitation",
        )

    @staticmethod
    def _duration(
        record: StateObject, result: RunResult, completed_at: str
    ) -> int | None:
        if result.duration_ms is not None:
            return max(0, int(result.duration_ms))
        started = record.get("started_at")
        if not isinstance(started, str):
            return None
        try:
            start = datetime.fromisoformat(started)
            end = datetime.fromisoformat(completed_at)
        except ValueError:
            return None
        return max(0, int((end - start).total_seconds() * 1000))

    def _build(
        self,
        request: RunCreateRequest,
        timestamp: str,
        existing: Sequence[StateObject],
    ) -> StateObject:
        command = [str(part) for part in request.command]
        return {
            "id": allocate_run_id(existing),
            "action": _action(request.action),
            "adapter": _text(request.adapter, field_name="adapter", required=False),
            "provider": _text(request.provider, field_name="provider", required=False),
            "command": command,
            "working_directory": _text(
                request.working_directory,
                field_name="working directory",
                required=False,
            ),
            "started_at": timestamp,
            "completed_at": None,
            "duration_ms": None,
            "exit_code": None,
            "status": "running",
            "stdout_summary": None,
            "stderr_summary": None,
            "revision": _text(request.revision, field_name="revision", required=False),
            "engine": _text(request.engine, field_name="engine", required=False),
            "engine_version": _text(
                request.engine_version, field_name="engine version", required=False
            ),
            "platform": _text(request.platform, field_name="platform", required=False),
            "artifacts": [],
            "limitations": _unique_strings(
                request.limitations, field_name="limitation"
            ),
            "created_at": timestamp,
            "risk_level": request.risk_level,
            "authorization": request.authorization,
        }

    def attach_artifacts(
        self, run_id: str, artifact_ids: Sequence[str], *, dry_run: bool = False
    ) -> MutationResult:
        """Link already-registered artifacts to the run that produced them."""

        with self._transaction("execution.attach", dry_run=dry_run) as transaction:
            state = transaction.state
            runs = copy.deepcopy(state["runs"])
            record = find_run(runs, run_id)
            known = {item["id"] for item in state["artifacts"]["artifacts"]}
            missing = sorted(set(artifact_ids) - known)
            if missing:
                raise RunInputError("unknown artifact(s): " + ", ".join(missing))
            record["artifacts"] = _unique_strings(
                list(record["artifacts"]) + list(artifact_ids), field_name="artifact"
            )
            transaction.set_runs(runs)
            return transaction.commit(details={"run": record, "run_id": run_id})


@dataclass(frozen=True, slots=True)
class RunProjection:
    """A run flattened for display, with its artifact records resolved."""

    run: StateObject
    artifacts: tuple[StateObject, ...] = field(default_factory=tuple)


def project_run(state: dict[str, StateObject], run_id: str) -> RunProjection:
    """Return a run with the artifact records it names, for show output."""

    record = find_run(state["runs"], run_id)
    by_id = {item["id"]: item for item in state["artifacts"]["artifacts"]}
    return RunProjection(
        run=record,
        artifacts=tuple(
            by_id[identifier]
            for identifier in record.get("artifacts", [])
            if identifier in by_id
        ),
    )
