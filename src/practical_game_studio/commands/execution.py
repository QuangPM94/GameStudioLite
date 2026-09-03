"""`studio execution` — inspect the runs the framework recorded.

The noun is `execution`, not `run`, because `studio run` is the verb that starts
a process. Keeping the action and the record under separate names means neither
has to grow a subcommand to disambiguate it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..runs import ACTIONS, STATUSES, RunFilter, filter_runs, project_run
from ..state import StateRepository
from ._shared import _add_root_argument, _json_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio execution` and its subcommands."""

    execution_parser = subparsers.add_parser(
        "execution", help="inspect recorded execution runs"
    )
    execution_subparsers = execution_parser.add_subparsers(
        dest="execution_command", required=True
    )

    execution_list = execution_subparsers.add_parser("list", help="list runs")
    _add_root_argument(execution_list)
    execution_list.add_argument("--action", choices=ACTIONS)
    execution_list.add_argument("--status", choices=STATUSES)
    execution_list.add_argument("--adapter")
    execution_list.add_argument(
        "--limit", type=int, help="show at most this many runs, newest first"
    )
    execution_list.add_argument("--json", action="store_true")

    execution_show = execution_subparsers.add_parser("show", help="show one run")
    _add_root_argument(execution_show)
    execution_show.add_argument("run_id")
    execution_show.add_argument("--json", action="store_true")


def _format_run_summary(run: dict[str, Any]) -> str:
    duration = run["duration_ms"]
    timing = f"{duration} ms" if duration is not None else "unfinished"
    exit_code = run["exit_code"]
    ended = f"exit {exit_code}" if exit_code is not None else "no exit code"
    return (
        f"{run['id']}  {run['status']:<9} {run['action']:<7} "
        f"{ended:<14} {timing:<12} {run['adapter'] or 'no adapter'}"
    )


def _format_run_detail(projection: Any) -> str:
    run = projection.run
    lines = [
        f"{run['id']} — {run['action']}",
        "",
        f"Status: {run['status']}",
        f"Exit code: {run['exit_code'] if run['exit_code'] is not None else 'none'}",
        f"Adapter: {run['adapter'] or 'none'}",
        f"Provider: {run['provider'] or 'none'}",
        f"Command: {' '.join(run['command']) if run['command'] else 'none recorded'}",
        f"Working directory: {run['working_directory'] or 'none'}",
        f"Started at: {run['started_at'] or 'not started'}",
        f"Completed at: {run['completed_at'] or 'not completed'}",
        f"Duration: {run['duration_ms']} ms"
        if run["duration_ms"] is not None
        else "Duration: unknown",
        f"Revision: {run['revision'] or 'unknown'}",
        f"Engine: {run['engine'] or 'unknown'}"
        + (f" {run['engine_version']}" if run["engine_version"] else ""),
        f"Platform: {run['platform'] or 'unknown'}",
    ]

    lines.extend(["", "Artifacts:"])
    if projection.artifacts:
        lines.extend(
            f"- {artifact['id']} ({artifact['type']}, {artifact['status']}): "
            f"{artifact['path']}"
            for artifact in projection.artifacts
        )
    else:
        lines.append("- none")

    # Limitations are printed even when empty: "this run proved nothing about
    # gameplay" is a fact a reader needs, and silence reads as "no caveats".
    lines.extend(["", "Limitations:"])
    lines.extend(f"- {item}" for item in run["limitations"] or ["none recorded"])

    for label, key in (("stdout", "stdout_summary"), ("stderr", "stderr_summary")):
        if run[key]:
            lines.extend(["", f"Captured {label}:", run[key]])
    return "\n".join(lines)


def _run_list(args: argparse.Namespace, root: Path) -> int:
    state = StateRepository(root).load_runs()
    criteria = RunFilter(
        action=args.action,
        status=args.status,
        adapter=args.adapter,
        limit=args.limit,
    )
    selected = filter_runs(state["runs"], criteria)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="execution.list",
                data={"count": len(selected), "runs": selected},
            )
        )
        return 0
    if not selected:
        print("No runs match the given filters.")
        return 0
    print(f"Runs ({len(selected)}):")
    for run in selected:
        print(_format_run_summary(run))
    return 0


def _run_show(args: argparse.Namespace, root: Path) -> int:
    state = StateRepository(root).load_all()
    projection = project_run(state, args.run_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="execution.show",
                data={
                    "run": projection.run,
                    "artifacts": list(projection.artifacts),
                },
            )
        )
        return 0
    print(_format_run_detail(projection))
    return 0


_SUBCOMMANDS = {"list": _run_list, "show": _run_show}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio execution` subcommand."""

    return _SUBCOMMANDS[args.execution_command](args, root)
