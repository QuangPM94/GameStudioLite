"""Turning a finished process into the records the framework stores.

This is the one place where an execution becomes canonical state. It exists as a
separate module so the rule it enforces is visible in one file: a process result
becomes a RUN and possibly some ARTs, and never anything more. It does not
create evidence, does not touch criteria, and does not decide that a build
working means a game working.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactCreateRequest, ArtifactService
from ..models import MutationResult
from ..runs import RunCreateRequest, RunResult, RunService
from .models import ProcessResult
from .runner import redact_command

#: Where captured logs are written before being registered as artifacts. Inside
#: the project so they travel with it, but under a single directory a developer
#: can add to `.gitignore` wholesale.
LOG_DIRECTORY = ".studio/logs"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """A completed execution and everything it wrote into state."""

    run_id: str
    status: str
    process: ProcessResult
    artifact_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether the process reported success. Not a claim about the game."""

        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "artifacts": list(self.artifact_ids),
            "process": self.process.to_dict(),
            "limitations": list(self.process.limitations),
        }


def write_log(root: Path, run_id: str, process: ProcessResult) -> Path | None:
    """Write the full captured output to a log file, or None if there was none.

    The full stream lives here rather than in `runs.json`, so that canonical
    state stays reviewable in a diff while nothing captured is actually lost.
    """

    body = _log_body(process)
    if not body.strip():
        return None
    directory = root / LOG_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id.lower()}.log"
    path.write_text(body, encoding="utf-8")
    return path


def _log_body(process: ProcessResult) -> str:
    sections = [
        f"$ {' '.join(redact_command(process.command))}",
        f"# outcome: {process.outcome}, exit code: {process.exit_code}",
        f"# started: {process.started_at}  completed: {process.completed_at}",
        "",
    ]
    if process.stdout:
        sections.extend(["--- stdout ---", process.stdout])
    if process.stderr:
        sections.extend(["--- stderr ---", process.stderr])
    if process.stdout_truncated or process.stderr_truncated:
        sections.append(
            "--- note: output exceeded the capture limit and was truncated ---"
        )
    return "\n".join(sections) + "\n"


def create_execution_record(
    root: Path,
    *,
    action: str,
    command: Sequence[str],
    adapter: str | None = None,
    provider: str | None = None,
    working_directory: str | None = None,
    revision: str | None = None,
    engine: str | None = None,
    engine_version: str | None = None,
    platform: str | None = None,
    limitations: Sequence[str] = (),
    risk_level: str = "low",
    authorization: str = "risk-below-threshold",
) -> str:
    """Open a run record before the process starts, returning its id."""

    result = RunService(root).create(
        RunCreateRequest(
            action=action,
            command=redact_command(command),
            adapter=adapter,
            provider=provider,
            working_directory=working_directory,
            revision=revision,
            engine=engine,
            engine_version=engine_version,
            platform=platform,
            limitations=limitations,
            risk_level=risk_level,
            authorization=authorization,
        )
    )
    return result.details["run_id"]


def complete_execution_record(
    root: Path,
    run_id: str,
    process: ProcessResult,
    *,
    capture_log: bool = True,
    extra_limitations: Sequence[str] = (),
    artifact_description: str | None = None,
) -> ExecutionRecord:
    """Close a run with its result, registering the captured log as an artifact.

    The status comes from :attr:`ProcessResult.run_status`, which maps a timeout
    or a startup failure to `unknown` rather than `failed`. A program the
    framework killed did not fail; nothing was learned about it either way.
    """

    artifact_ids: list[str] = []
    if capture_log:
        log_path = write_log(root, run_id, process)
        if log_path is not None:
            registered = ArtifactService(root).add(
                ArtifactCreateRequest(
                    type="log",
                    path=str(log_path),
                    source_run=run_id,
                    description=artifact_description or f"Captured output of {run_id}.",
                )
            )
            artifact_ids.append(registered.details["artifact_id"])

    RunService(root).complete(
        run_id,
        RunResult(
            status=process.run_status,
            exit_code=process.exit_code,
            stdout_summary=process.stdout or None,
            stderr_summary=process.stderr or None,
            duration_ms=process.duration_ms,
            artifacts=artifact_ids,
            limitations=(*process.limitations, *extra_limitations),
        ),
    )
    return ExecutionRecord(
        run_id=run_id,
        status=process.run_status,
        process=process,
        artifact_ids=tuple(artifact_ids),
    )


def fail_execution_record(
    root: Path, run_id: str, reason: str, *, status: str = "unknown"
) -> MutationResult:
    """Close a run that produced no process result at all.

    Defaults to `unknown` rather than `failed`: if the framework could not run
    the program, the program has not been shown to be broken.
    """

    return RunService(root).complete(
        run_id, RunResult(status=status, limitations=(reason,))
    )
