"""Typed inputs and outputs for running an external process.

These types are deliberately free of project state. A process result says what a
program did; deciding what that means for a game is somebody else's job, further
up. Keeping the boundary here is what stops "exit code 0" from quietly becoming
"the prototype works".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: How a process ended. `timeout` and `error` are separate from `completed`
#: because neither produced a result the caller may reason about: a program the
#: framework killed proved nothing, and a program it could not start proved less.
OUTCOMES = ("completed", "timeout", "cancelled", "error")

#: Mapping from a process outcome to the run status it justifies. A timeout maps
#: to `unknown`, not `failed`: the framework stopped the program, so nothing was
#: learned about whether it would have succeeded.
OUTCOME_RUN_STATUS = {
    "timeout": "unknown",
    "cancelled": "cancelled",
    "error": "unknown",
}


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """One process to run, described completely enough to be reproducible."""

    command: Sequence[str]
    working_directory: Path | None = None
    #: Applied on top of the inherited environment; a value of None removes the
    #: variable entirely.
    environment: Mapping[str, str | None] = field(default_factory=dict)
    timeout_seconds: float | None = None
    #: Text appended to the process's stdin, then closed. Interactive programs
    #: are not supported: an agent must not be able to leave one waiting.
    stdin: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """What happened when a process ran.

    `outcome` and `exit_code` answer different questions. `exit_code` is what the
    program reported; `outcome` is whether the program was allowed to report
    anything at all.
    """

    command: tuple[str, ...]
    working_directory: str | None
    outcome: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    started_at: str
    completed_at: str
    #: Set when the framework could not run or could not finish the process.
    error: str | None = None
    #: True when captured output was cut before the end of the stream.
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def ok(self) -> bool:
        """Whether the process ran to completion and reported success.

        This is a fact about a process only. It is never sufficient grounds for
        a claim about the game.
        """

        return self.outcome == "completed" and self.exit_code == 0

    @property
    def run_status(self) -> str:
        """The `runs.json` status this outcome justifies."""

        if self.outcome in OUTCOME_RUN_STATUS:
            return OUTCOME_RUN_STATUS[self.outcome]
        return "passed" if self.exit_code == 0 else "failed"

    @property
    def limitations(self) -> tuple[str, ...]:
        """Caveats a reader needs in order not to over-read this result."""

        if self.outcome == "timeout":
            return (
                (
                    "The process was killed after its timeout; whether it "
                    "would have succeeded is unknown."
                ),
            )
        if self.outcome == "cancelled":
            return ("The process was cancelled before it finished.",)
        if self.outcome == "error":
            return (
                (
                    f"The process could not be run to completion: {self.error}."
                    " No conclusion about the program is supported."
                ),
            )
        caveats = []
        if self.stdout_truncated or self.stderr_truncated:
            caveats.append(
                "Captured output was truncated; the full stream is only in the "
                "log artifact."
            )
        return tuple(caveats)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready view for command output."""

        return {
            "command": list(self.command),
            "working_directory": self.working_directory,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }
