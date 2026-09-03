"""`studio work` — bounded autonomous work packets.

The command surface mirrors the lifecycle, and the order is not decoration:
a packet must be started before it can be verified, and verified before it can
be completed. There is no path that skips a step.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..safety import authorize
from ..state import StateRepository
from ..work import (
    RISK_LEVELS,
    STATUSES,
    VerificationOutcome,
    WorkCreateRequest,
    WorkService,
    find_work,
)
from ._shared import (
    _add_root_argument,
    _json_envelope,
    _mutation_envelope,
    _print_json,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio work` and its subcommands."""

    work_parser = subparsers.add_parser(
        "work", help="manage bounded autonomous work packets"
    )
    work_subparsers = work_parser.add_subparsers(dest="work_command", required=True)

    work_add = work_subparsers.add_parser("add", help="write a work packet contract")
    _add_root_argument(work_add)
    work_add.add_argument("--goal", required=True)
    work_add.add_argument("--reason", required=True)
    work_add.add_argument(
        "--allow",
        action="append",
        default=[],
        required=True,
        help="glob an agent may change (repeatable); an empty scope permits nothing",
    )
    work_add.add_argument(
        "--forbid", action="append", default=[], help="glob that must not change"
    )
    work_add.add_argument(
        "--criterion",
        action="append",
        default=[],
        required=True,
        help="what must be true at the end (repeatable)",
    )
    work_add.add_argument(
        "--verify-with",
        action="append",
        default=[],
        help="command that proves the criteria (repeatable)",
    )
    work_add.add_argument("--critical-path-item")
    work_add.add_argument("--depends-on", action="append", default=[])
    work_add.add_argument("--risk", choices=RISK_LEVELS, default="low")
    work_add.add_argument("--requires-approval", action="store_true")
    work_add.add_argument("--dry-run", action="store_true")
    work_add.add_argument("--json", action="store_true")

    work_list = work_subparsers.add_parser("list", help="list work packets")
    _add_root_argument(work_list)
    work_list.add_argument("--status", choices=STATUSES)
    work_list.add_argument("--json", action="store_true")

    work_show = work_subparsers.add_parser("show", help="show one packet in full")
    work_show.add_argument("work_id")
    _add_root_argument(work_show)
    work_show.add_argument("--json", action="store_true")

    work_ready = work_subparsers.add_parser(
        "ready", help="list packets whose dependencies are complete"
    )
    _add_root_argument(work_ready)
    work_ready.add_argument("--json", action="store_true")

    work_start = work_subparsers.add_parser(
        "start", help="begin work, pinning the revision scope is measured from"
    )
    work_start.add_argument("work_id")
    _add_root_argument(work_start)
    work_start.add_argument("--yes", action="store_true")
    work_start.add_argument("--json", action="store_true")

    work_verify = work_subparsers.add_parser(
        "verify", help="run the declared checks and confirm the scope held"
    )
    work_verify.add_argument("work_id")
    _add_root_argument(work_verify)
    work_verify.add_argument(
        "--no-record",
        dest="record",
        action="store_false",
        help="report the result without storing it",
    )
    work_verify.add_argument("--json", action="store_true")

    work_complete = work_subparsers.add_parser(
        "complete", help="close a packet; refused without a passing verification"
    )
    work_complete.add_argument("work_id")
    _add_root_argument(work_complete)
    work_complete.add_argument("--result")
    work_complete.add_argument("--evidence", action="append", default=[])
    work_complete.add_argument("--json", action="store_true")

    work_fail = work_subparsers.add_parser("fail", help="close a packet as failed")
    work_fail.add_argument("work_id")
    _add_root_argument(work_fail)
    work_fail.add_argument("--reason", required=True)
    work_fail.add_argument("--json", action="store_true")


def _summary(packet: dict[str, Any]) -> str:
    return f"{packet['id']}  {packet['status']:<12} {packet['goal']}"


def _format_detail(packet: dict[str, Any]) -> str:
    lines = [
        f"{packet['id']} — {packet['goal']}",
        "",
        f"Status: {packet['status']}",
        f"Risk: {packet['risk_level']}",
        f"Human approval required: {'yes' if packet['human_approval_required'] else 'no'}",
        f"Critical-path item: {packet['critical_path_item'] or 'none'}",
        f"Started from revision: {packet['started_revision'] or 'not started'}",
        "",
        "Reason:",
        packet["reason"],
    ]
    for title, key in (
        ("Allowed files", "allowed_files"),
        ("Forbidden files", "forbidden_files"),
        ("Acceptance criteria", "acceptance_criteria"),
        ("Verification commands", "verification_commands"),
        ("Dependencies", "dependencies"),
        ("Related runs", "related_runs"),
        ("Related artifacts", "related_artifacts"),
        ("Related evidence", "related_evidence"),
    ):
        lines.extend(["", f"{title}:"])
        lines.extend(f"- {item}" for item in packet[key] or ["none"])

    lines.extend(["", "Verification history:"])
    if not packet["verification_history"]:
        # Printed even when empty: "never verified" is the fact that decides
        # whether this packet may be completed.
        lines.append("- never verified")
    else:
        lines.extend(
            f"- {entry['verified_at']}: "
            f"{'passed' if entry['passed'] else 'failed'} — {entry['detail']}"
            for entry in packet["verification_history"]
        )
    lines.extend(["", f"Result: {packet['result'] or 'none recorded'}"])
    return "\n".join(lines)


def _format_verification(outcome: VerificationOutcome) -> str:
    lines = [
        f"{outcome.work_id}: {'passed' if outcome.passed else 'failed'}",
        outcome.detail,
        "",
        "Commands:",
    ]
    lines.extend(
        f"- {item['command']}: {'passed' if item['passed'] else 'failed'} "
        f"({item['outcome']}, exit {item['exit_code']})"
        for item in outcome.command_results
    ) if outcome.command_results else lines.append("- none declared")

    scope = outcome.scope
    lines.extend(["", f"Scope ({scope.detail}):"])
    lines.append(f"- changed: {len(scope.changed)} file(s)")
    lines.append(f"- within scope: {len(scope.allowed)}")
    lines.extend(["", "Out-of-scope changes:"])
    lines.extend([f"- {item}" for item in scope.violations] or ["- none"])
    return "\n".join(lines)


def _run_add(args: argparse.Namespace, root: Path) -> int:
    result = WorkService(root).create(
        WorkCreateRequest(
            goal=args.goal,
            reason=args.reason,
            allowed_files=tuple(args.allow),
            forbidden_files=tuple(args.forbid),
            acceptance_criteria=tuple(args.criterion),
            verification_commands=tuple(args.verify_with),
            critical_path_item=args.critical_path_item,
            dependencies=tuple(args.depends_on),
            risk_level=args.risk,
            human_approval_required=args.requires_approval,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    packet = result.details["work"]
    print(f"{'Would create' if result.dry_run else 'Created'} {packet['id']}.\n")
    print(_format_detail(packet))
    if not packet["verification_commands"]:
        print(
            "\nWarning: this packet declares no verification commands, so it "
            "can never be completed. Add some before starting it."
        )
    return 0


def _run_list(args: argparse.Namespace, root: Path) -> int:
    packets = StateRepository(root).load_work()["work"]
    if args.status:
        packets = [item for item in packets if item["status"] == args.status]
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="work.list",
                data={"count": len(packets), "work": packets},
            )
        )
        return 0
    if not packets:
        print("No work packets match the given filters.")
        return 0
    print(f"Work packets ({len(packets)}):")
    for packet in packets:
        print(_summary(packet))
    return 0


def _run_show(args: argparse.Namespace, root: Path) -> int:
    packet = find_work(StateRepository(root).load_work(), args.work_id)
    if args.json:
        _print_json(
            _json_envelope(success=True, operation="work.show", data={"work": packet})
        )
        return 0
    print(_format_detail(packet))
    return 0


def _run_ready(args: argparse.Namespace, root: Path) -> int:
    packets = WorkService(root).ready()
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="work.ready",
                data={"count": len(packets), "work": list(packets)},
            )
        )
        return 0
    if not packets:
        print("No work packet is ready to start.")
        return 0
    print(f"Ready ({len(packets)}):")
    for packet in packets:
        print(_summary(packet))
    return 0


def _run_start(args: argparse.Namespace, root: Path) -> int:
    packet = find_work(StateRepository(root).load_work(), args.work_id)
    if packet["human_approval_required"]:
        # The packet's own author decided this needs a person. The safety layer
        # enforces it the same way it enforces a risky command.
        authorize(
            root,
            "build" if packet["risk_level"] == "medium" else "run",
            acknowledged=args.yes,
            json_output=args.json,
            prompt_detail=f"{packet['id']}: {packet['goal']}",
        )
    result = WorkService(root).start(args.work_id)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    print(f"{args.work_id} started.\n")
    print("You may change only:")
    for pattern in result.details["allowed_files"]:
        print(f"- {pattern}")
    if result.details["forbidden_files"]:
        print("\nYou must not change:")
        for pattern in result.details["forbidden_files"]:
            print(f"- {pattern}")
    print(
        "\nChanging anything else will fail verification. Widening the scope is "
        "not something this packet can do to itself."
    )
    return 0


def _run_verify(args: argparse.Namespace, root: Path) -> int:
    service = WorkService(root)
    outcome = service.verify(args.work_id)
    if args.record:
        service.record_verification(args.work_id, outcome)
    if args.json:
        _print_json(
            _json_envelope(
                success=outcome.passed,
                operation="work.verify",
                data=outcome.to_dict(),
            )
        )
        return 0 if outcome.passed else 1
    print(_format_verification(outcome))
    if outcome.passed:
        print(f"\nRecommended next command:\nstudio work complete {args.work_id}")
    else:
        print(
            "\nThis packet is not complete. Fix the work and verify again; there "
            "is no way to complete it over a failing check."
        )
    return 0 if outcome.passed else 1


def _run_complete(args: argparse.Namespace, root: Path) -> int:
    result = WorkService(root).complete(
        args.work_id, result=args.result, evidence=tuple(args.evidence)
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    packet = result.details["work"]
    print(f"{packet['id']} complete.")
    print(f"Result: {packet['result']}")
    return 0


def _run_fail(args: argparse.Namespace, root: Path) -> int:
    result = WorkService(root).fail(args.work_id, args.reason)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    print(f"{args.work_id} failed: {result.details['work']['result']}")
    return 0


_SUBCOMMANDS = {
    "add": _run_add,
    "list": _run_list,
    "show": _run_show,
    "ready": _run_ready,
    "start": _run_start,
    "verify": _run_verify,
    "complete": _run_complete,
    "fail": _run_fail,
}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio work` subcommand."""

    return _SUBCOMMANDS[args.work_command](args, root)
