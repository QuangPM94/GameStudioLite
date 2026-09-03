"""Probing the machine the framework is running on.

Every value here is *probed*, never assumed. A tool the framework did not find
is reported as absent; a version it could not parse is reported as unknown. The
difference matters because `studio doctor` uses these results to say what the
framework can actually do, and a doctor that overstates its capabilities is
worse than no doctor at all.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ExecutionRequest
from .runner import execute_process, which

#: How confident the framework is about one capability.
#:
#: `unknown` exists because it is not the same as `unavailable`. "We looked and
#: it is not there" and "we could not tell" lead to different next actions, and
#: collapsing them would let the framework claim it had checked something it had
#: not.
READINESS = ("ready", "unavailable", "unknown", "not-configured")

#: How long a version probe may take. A tool that cannot answer this fast is
#: treated as unknown rather than allowed to stall the doctor.
PROBE_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class ToolProbe:
    """The result of looking for one external tool."""

    name: str
    executable: str | None
    version: str | None
    readiness: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "executable": self.executable,
            "version": self.version,
            "readiness": self.readiness,
            "detail": self.detail,
        }


def probe_tool(
    name: str,
    program: str,
    version_args: tuple[str, ...] = ("--version",),
    *,
    executable: Path | None = None,
) -> ToolProbe:
    """Find a tool and ask it its version, without ever inferring either."""

    located = executable or which(program)
    if located is None:
        return ToolProbe(
            name=name,
            executable=None,
            version=None,
            readiness="unavailable",
            detail=f"{program} was not found on PATH",
        )

    result = execute_process(
        ExecutionRequest(
            command=(str(located), *version_args),
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
    )
    if not result.ok:
        return ToolProbe(
            name=name,
            executable=str(located),
            version=None,
            readiness="unknown",
            detail=(
                f"{program} is present but did not report a version "
                f"({result.outcome}, exit {result.exit_code})"
            ),
        )
    version = _first_line(result.stdout) or _first_line(result.stderr)
    return ToolProbe(
        name=name,
        executable=str(located),
        version=version,
        readiness="ready",
        detail=f"{program} responded to {' '.join(version_args)}",
    )


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def probe_python() -> ToolProbe:
    """Report the interpreter actually running the framework."""

    return ToolProbe(
        name="python",
        executable=sys.executable,
        version=platform.python_version(),
        readiness="ready",
        detail="the interpreter running this process",
    )


def probe_git() -> ToolProbe:
    """Report whether git is available for revision provenance."""

    return probe_tool("git", "git")


def detect_revision(root: Path) -> str | None:
    """Return the current commit for run provenance, or None if unknowable.

    Returning None is a real answer: a project that is not a git repository, or
    a machine without git, cannot have its runs pinned to a revision, and
    pretending otherwise would make artifacts untraceable in a way that is hard
    to notice later.
    """

    if which("git") is None:
        return None
    result = execute_process(
        ExecutionRequest(
            command=("git", "rev-parse", "HEAD"),
            working_directory=root,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
    )
    if not result.ok:
        return None
    revision = result.stdout.strip()
    return revision or None


def detect_repository(root: Path) -> dict[str, Any]:
    """Describe the version-control context a run happened in."""

    if which("git") is None:
        return {"vcs": None, "revision": None, "dirty": None, "detail": "git not found"}
    inside = execute_process(
        ExecutionRequest(
            command=("git", "rev-parse", "--is-inside-work-tree"),
            working_directory=root,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
    )
    if not inside.ok or inside.stdout.strip() != "true":
        return {
            "vcs": None,
            "revision": None,
            "dirty": None,
            "detail": "not inside a git work tree",
        }
    status = execute_process(
        ExecutionRequest(
            command=("git", "status", "--porcelain"),
            working_directory=root,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
    )
    return {
        "vcs": "git",
        "revision": detect_revision(root),
        # A dirty tree means an artifact cannot be reproduced from the recorded
        # revision alone, which a reader of the evidence needs to know.
        "dirty": bool(status.stdout.strip()) if status.ok else None,
        "detail": "git work tree",
    }


def describe_platform() -> dict[str, str]:
    """Return the host facts recorded alongside every run."""

    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def platform_label() -> str:
    """A short host identifier stored in run records."""

    return f"{platform.system().lower()}-{platform.machine().lower()}"
