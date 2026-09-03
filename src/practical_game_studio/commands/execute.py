"""`studio run`, `studio test`, `studio build`, and `studio verify`.

These are the four verbs that actually do something to a game. They share a
module because they share one contract, and stating it once is better than
restating it four times:

Each resolves an engine adapter, asks it to perform one operation, and reports
what the resulting RUN and ART records say. None of them creates evidence.
A green exit code here is a fact about a process, and turning it into a claim
about the game is a separate, explicit act — which `studio verify` supports by
*proposing* wording, never by asserting it.

An operation the adapter cannot perform exits with a distinct code, because
"this could not be attempted" and "this was attempted and failed" must not look
the same to an agent deciding what to do next.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..adapters import (
    AdapterOperationResult,
    BuildOptions,
    RunOptions,
    TestOptions,
    resolve_adapter,
)
from ..verification import LEVELS, VerificationReport, summarize_levels, verify
from ._shared import _add_root_argument, _json_envelope, _print_json

#: Exit codes. `4` is separate from `1` on purpose: a failing test and an
#: un-runnable project call for completely different next actions.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNKNOWN = 4


def register_run(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio run`."""

    parser = subparsers.add_parser("run", help="launch the game through its adapter")
    _add_root_argument(parser)
    parser.add_argument("--adapter")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--scene", help="scene to launch instead of the main scene")
    parser.add_argument(
        "--timeout", type=float, help="seconds before the run is stopped"
    )
    parser.add_argument(
        "--no-capture-log",
        dest="capture_log",
        action="store_false",
        help="do not register the captured output as an artifact",
    )
    parser.add_argument("--json", action="store_true")


def register_test(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio test`."""

    parser = subparsers.add_parser("test", help="run the project's tests")
    _add_root_argument(parser)
    parser.add_argument("--adapter")
    parser.add_argument(
        "--suite",
        choices=("unit", "scene", "integration", "all"),
        default="all",
    )
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--json", action="store_true")


def register_build(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio build`."""

    parser = subparsers.add_parser("build", help="build or export the game")
    _add_root_argument(parser)
    parser.add_argument("--adapter")
    parser.add_argument("--target", help="export preset or build target name")
    parser.add_argument("--profile", choices=("debug", "release"), default="debug")
    parser.add_argument("--output", help="path to write the produced build to")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--json", action="store_true")


def register_verify(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio verify`."""

    parser = subparsers.add_parser(
        "verify", help="check what has actually been established, at a stated depth"
    )
    _add_root_argument(parser)
    parser.add_argument("--adapter")
    parser.add_argument("--level", choices=LEVELS, default="smoke")
    parser.add_argument(
        "--levels",
        action="store_true",
        help="list the levels and what each does and does not establish",
    )
    parser.add_argument("--json", action="store_true")


def _exit_code(status: str) -> int:
    if status == "passed":
        return EXIT_OK
    if status == "failed":
        return EXIT_FAILED
    return EXIT_UNKNOWN


def _no_adapter(operation: str, json_output: bool) -> int:
    detail = (
        "No engine adapter recognises this project. The framework stays usable "
        "for planning; nothing was executed."
    )
    if json_output:
        _print_json(
            _json_envelope(
                success=False,
                operation=operation,
                data={"status": "unknown", "detail": detail},
            )
        )
    else:
        print(detail)
        print("\nRecommended next command:\nstudio doctor")
    return EXIT_UNKNOWN


def _report_operation(
    operation: str, result: AdapterOperationResult, json_output: bool
) -> int:
    if json_output:
        _print_json(
            _json_envelope(
                success=result.status == "passed",
                operation=operation,
                data=result.to_dict(),
            )
        )
        return _exit_code(result.status)

    print(f"Status: {result.status}")
    print(result.detail)
    if result.run_id:
        print(f"\nRun: {result.run_id}")
    if result.artifacts:
        print("Artifacts: " + ", ".join(result.artifacts))
    # Printed even when empty is impossible here: an operation with no caveats
    # still gets the closing reminder below, which is the important one.
    if result.limitations:
        print("\nLimitations:")
        for item in result.limitations:
            print(f"- {item}")
    print(
        "\nThis records what a process did. It is not evidence about the game "
        "until you create some:\nstudio evidence add --run "
        f"{result.run_id or '<RUN-ID>'} ..."
    )
    return _exit_code(result.status)


def run_run(args: argparse.Namespace, root: Path) -> int:
    """Launch the game and record what happened."""

    adapter = resolve_adapter(root, adapter_id=args.adapter)
    if adapter is None:
        return _no_adapter("run", args.json)
    result = adapter.run(
        root,
        RunOptions(
            headless=args.headless,
            scene=args.scene,
            timeout_seconds=args.timeout,
            capture_log=args.capture_log,
        ),
    )
    return _report_operation("run", result, args.json)


def run_test(args: argparse.Namespace, root: Path) -> int:
    """Run the project's tests and record what happened."""

    adapter = resolve_adapter(root, adapter_id=args.adapter)
    if adapter is None:
        return _no_adapter("test", args.json)
    result = adapter.test(
        root, TestOptions(suite=args.suite, timeout_seconds=args.timeout)
    )
    return _report_operation("test", result, args.json)


def run_build(args: argparse.Namespace, root: Path) -> int:
    """Build the game and record what happened."""

    adapter = resolve_adapter(root, adapter_id=args.adapter)
    if adapter is None:
        return _no_adapter("build", args.json)
    result = adapter.build(
        root,
        BuildOptions(
            target=args.target,
            profile=args.profile,
            output=args.output,
            timeout_seconds=args.timeout,
        ),
    )
    return _report_operation("build", result, args.json)


def _format_report(report: VerificationReport) -> str:
    lines = [
        f"Verification level: {report.level}",
        f"Status: {report.status}",
        f"Adapter: {report.adapter_id or 'none'}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- {check.name}: {check.status} — {check.detail}")
        if check.run_id:
            lines.append(f"  run: {check.run_id}")
        if check.artifacts:
            lines.append("  artifacts: " + ", ".join(check.artifacts))

    # Always printed, even when empty: silence about limitations reads as "there
    # are none", which is the single most dangerous thing this output could imply.
    lines.extend(["", "What this did NOT establish:"])
    lines.extend(f"- {item}" for item in report.limitations or ("nothing recorded",))

    lines.extend(["", "Evidence proposals:"])
    if not report.proposals:
        lines.append("- none; nothing observed here supports a claim about the game.")
    else:
        for proposal in report.proposals:
            lines.append(f"- [{proposal.classification}] {proposal.claim}")
            lines.extend(f"    limitation: {item}" for item in proposal.limitations)
        lines.extend(
            [
                "",
                "These are proposals, not evidence. Accept one explicitly:",
                report.proposals[0].as_command("<your title>"),
            ]
        )
    return "\n".join(lines)


def run_verify(args: argparse.Namespace, root: Path) -> int:
    """Report what a verification level established, and what it did not."""

    if args.levels:
        rows: list[dict[str, Any]] = [
            {"level": level, "establishes": description}
            for level, description in summarize_levels()
        ]
        if args.json:
            _print_json(
                _json_envelope(
                    success=True, operation="verify.levels", data={"levels": rows}
                )
            )
            return EXIT_OK
        print("Verification levels:")
        for row in rows:
            print(f"- {row['level']}: {row['establishes']}")
        return EXIT_OK

    report = verify(root, args.level, adapter_id=args.adapter)
    if args.json:
        _print_json(
            _json_envelope(
                success=report.status == "passed",
                operation="verify",
                data=report.to_dict(),
            )
        )
        return _exit_code(report.status)
    print(_format_report(report))
    return _exit_code(report.status)
