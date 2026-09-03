"""Deterministic primitives for running things and recording what happened.

Workflows and adapters call into this package rather than reaching for
`subprocess` themselves. Routing every execution through one place is what makes
four guarantees hold everywhere: a process cannot run forever, it cannot wait for
input, its output is captured safely, and a process the framework had to kill is
never reported as a failure the program produced.

The package deliberately stops at RUN and ART records. Turning "exit code 0" into
"the prototype works" is a judgement, and judgements are made explicitly, by
creating evidence.
"""

from __future__ import annotations

from .environment import (
    READINESS,
    ToolProbe,
    describe_platform,
    detect_repository,
    detect_revision,
    platform_label,
    probe_git,
    probe_python,
    probe_tool,
)
from .models import OUTCOMES, ExecutionRequest, ProcessResult
from .result import (
    ExecutionRecord,
    complete_execution_record,
    create_execution_record,
    fail_execution_record,
    write_log,
)
from .runner import (
    ProcessError,
    calculate_duration,
    capture_stderr,
    capture_stdout,
    execute_process,
    redact_command,
    sanitize_environment,
    stream_process,
    terminate_process,
    which,
)

__all__ = [
    "OUTCOMES",
    "READINESS",
    "ExecutionRecord",
    "ExecutionRequest",
    "ProcessError",
    "ProcessResult",
    "ToolProbe",
    "calculate_duration",
    "capture_stderr",
    "capture_stdout",
    "complete_execution_record",
    "create_execution_record",
    "describe_platform",
    "detect_repository",
    "detect_revision",
    "execute_process",
    "fail_execution_record",
    "platform_label",
    "probe_git",
    "probe_python",
    "probe_tool",
    "redact_command",
    "sanitize_environment",
    "stream_process",
    "terminate_process",
    "which",
    "write_log",
]
