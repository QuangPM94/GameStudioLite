"""Running one external process safely and recording what it did.

Every process the framework starts on a project's behalf goes through here, so
that four things are true no matter which adapter asked for it: the process
cannot wait forever, it cannot wait for input, its output is captured as UTF-8
without crashing on a stray byte, and a process the framework had to kill is
never reported as a failure the program itself produced.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from .models import ExecutionRequest, ProcessResult

#: Captured output is held in memory before being written to a log artifact.
#: Beyond this the tail is dropped, because an engine that logs a warning per
#: frame can produce gigabytes and the interesting part is the start.
CAPTURE_LIMIT_BYTES = 4 * 1024 * 1024

#: Grace period between asking a timed-out process to stop and killing it.
TERMINATE_GRACE_SECONDS = 5.0

#: Environment variables never passed to a child process. The framework runs
#: engines and build tools on a developer's machine; leaking credentials into
#: something that logs its own environment is a real way to lose them.
BLOCKED_ENVIRONMENT_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)

#: Forced so captured output decodes predictably on every platform rather than
#: depending on the developer's console code page.
FORCED_ENVIRONMENT = {
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


class ProcessError(RuntimeError):
    """A process could not be started or supervised."""


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def calculate_duration(started: float, finished: float) -> int:
    """Return elapsed milliseconds, never negative."""

    return max(0, int((finished - started) * 1000))


def sanitize_environment(
    overrides: Mapping[str, str | None] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the environment a child process runs with.

    Credential-shaped variables are dropped unless the caller passes one back
    explicitly, so an adapter has to opt in by name rather than inheriting a
    developer's whole shell. An override of None removes a variable.
    """

    environment = {
        key: value
        for key, value in (base if base is not None else os.environ).items()
        if not key.upper().startswith(BLOCKED_ENVIRONMENT_PREFIXES)
    }
    environment.update(FORCED_ENVIRONMENT)
    for key, value in (overrides or {}).items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    return environment


def capture_stdout(result: ProcessResult) -> str:
    """Return the captured standard output of a finished process."""

    return result.stdout


def capture_stderr(result: ProcessResult) -> str:
    """Return the captured standard error of a finished process."""

    return result.stderr


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Ask a process to stop, then kill it if it will not.

    A build tool that ignores a polite signal must not be able to keep the
    framework waiting, but it is given a chance to flush its own logs first.
    """

    if process.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            process.terminate()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            return
        with _suppressed():
            process.wait(timeout=TERMINATE_GRACE_SECONDS)


class _suppressed:
    """Swallow errors raised while cleaning up a process we already gave up on."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return True


def _decode(raw: bytes) -> tuple[str, bool]:
    """Decode captured bytes as UTF-8, replacing anything undecodable.

    An engine emitting one bad byte must not lose the framework the entire log.
    """

    truncated = len(raw) > CAPTURE_LIMIT_BYTES
    if truncated:
        raw = raw[:CAPTURE_LIMIT_BYTES]
    return raw.decode("utf-8", errors="replace"), truncated


def _popen_kwargs(request: ExecutionRequest) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE,
        "cwd": str(request.working_directory) if request.working_directory else None,
        "env": sanitize_environment(request.environment),
    }
    if sys.platform == "win32":
        # A new process group lets a timeout reach the whole tree rather than
        # only the launcher an engine often uses.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return kwargs


def execute_process(request: ExecutionRequest) -> ProcessResult:
    """Run one process to completion, a timeout, or a startup failure.

    Never raises for a program that fails: a non-zero exit is a result, not an
    error. It returns an `error` outcome only when the framework itself could
    not run or supervise the process.
    """

    command = tuple(str(part) for part in request.command)
    if not command:
        raise ProcessError("cannot execute an empty command")
    working_directory = (
        str(request.working_directory) if request.working_directory else None
    )
    started_at = _timestamp()
    started = time.monotonic()

    try:
        process = subprocess.Popen(command, **_popen_kwargs(request))
    except (OSError, ValueError) as exc:
        return ProcessResult(
            command=command,
            working_directory=working_directory,
            outcome="error",
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=calculate_duration(started, time.monotonic()),
            started_at=started_at,
            completed_at=_timestamp(),
            error=str(exc),
        )

    stdin_bytes = request.stdin.encode("utf-8") if request.stdin else None
    outcome = "completed"
    error: str | None = None
    try:
        raw_out, raw_err = process.communicate(
            input=stdin_bytes, timeout=request.timeout_seconds
        )
    except subprocess.TimeoutExpired:
        terminate_process(process)
        raw_out, raw_err = process.communicate()
        outcome = "timeout"
        error = f"no result after {request.timeout_seconds} seconds"
    except KeyboardInterrupt:
        terminate_process(process)
        raw_out, raw_err = process.communicate()
        outcome = "cancelled"
        error = "interrupted"
    except OSError as exc:
        terminate_process(process)
        raw_out, raw_err = b"", b""
        outcome = "error"
        error = str(exc)

    stdout, stdout_truncated = _decode(raw_out or b"")
    stderr, stderr_truncated = _decode(raw_err or b"")
    return ProcessResult(
        command=command,
        working_directory=working_directory,
        outcome=outcome,
        exit_code=process.returncode if outcome == "completed" else None,
        stdout=stdout,
        stderr=stderr,
        duration_ms=calculate_duration(started, time.monotonic()),
        started_at=started_at,
        completed_at=_timestamp(),
        error=error,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def stream_process(request: ExecutionRequest):
    """Yield output lines while a process runs, then return its result.

    Used where a caller wants to show progress for a long build. The captured
    result is identical to :func:`execute_process`, so nothing about what is
    recorded depends on whether anyone was watching.
    """

    command = tuple(str(part) for part in request.command)
    if not command:
        raise ProcessError("cannot execute an empty command")
    started_at = _timestamp()
    started = time.monotonic()
    kwargs = _popen_kwargs(request)
    kwargs["stderr"] = subprocess.STDOUT

    try:
        process = subprocess.Popen(command, **kwargs)
    except (OSError, ValueError) as exc:
        yield from ()
        return ProcessResult(
            command=command,
            working_directory=kwargs["cwd"],
            outcome="error",
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=calculate_duration(started, time.monotonic()),
            started_at=started_at,
            completed_at=_timestamp(),
            error=str(exc),
        )

    collected = bytearray()
    outcome = "completed"
    error: str | None = None
    deadline = (
        started + request.timeout_seconds
        if request.timeout_seconds is not None
        else None
    )
    if process.stdin is not None:
        if request.stdin:
            process.stdin.write(request.stdin.encode("utf-8"))
        process.stdin.close()

    assert process.stdout is not None
    for raw_line in process.stdout:
        if len(collected) < CAPTURE_LIMIT_BYTES:
            collected.extend(raw_line)
        yield raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if deadline is not None and time.monotonic() > deadline:
            terminate_process(process)
            outcome = "timeout"
            error = f"no result after {request.timeout_seconds} seconds"
            break
    process.wait()

    stdout, truncated = _decode(bytes(collected))
    return ProcessResult(
        command=command,
        working_directory=kwargs["cwd"],
        outcome=outcome,
        exit_code=process.returncode if outcome == "completed" else None,
        stdout=stdout,
        stderr="",
        duration_ms=calculate_duration(started, time.monotonic()),
        started_at=started_at,
        completed_at=_timestamp(),
        error=error,
        stdout_truncated=truncated,
    )


def which(program: str, *, path: str | None = None) -> Path | None:
    """Locate an executable, returning None rather than guessing at a path."""

    import shutil

    located = shutil.which(program, path=path)
    return Path(located) if located else None


def redact_command(command: Sequence[str]) -> tuple[str, ...]:
    """Return a command safe to store in canonical state.

    Anything that looks like an inline secret is replaced before the command is
    written to `runs.json`, which is committed to the project's repository.
    """

    redacted: list[str] = []
    for part in command:
        text = str(part)
        lowered = text.lower()
        if "=" in text and any(
            marker in lowered.split("=", 1)[0]
            for marker in ("token", "secret", "password", "key", "credential")
        ):
            redacted.append(text.split("=", 1)[0] + "=***")
        else:
            redacted.append(text)
    return tuple(redacted)
