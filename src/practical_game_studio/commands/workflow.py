"""`studio workflow` — which workflows can actually run, and why not.

Readiness used to be a matter of an agent reading prose in a playbook. These
commands compute it from declared requirements instead, so the answer can be
checked, disagreed with, and tested.

Everything here is read-only. Knowing a workflow is blocked never advances a
phase or changes state on its own.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..workflow_commands import canonical_command, catalog_workflows_by_id
from ..workflow_readiness import (
    WorkflowReadiness,
    evaluate_workflow_readiness,
    explain_workflow_blockers,
    list_ready_workflows,
    load_catalog,
    recommend_next_workflow,
)
from ._shared import _add_root_argument, _json_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio workflow` and its subcommands."""

    workflow_parser = subparsers.add_parser(
        "workflow", help="inspect workflow readiness"
    )
    workflow_subparsers = workflow_parser.add_subparsers(
        dest="workflow_command", required=True
    )

    workflow_list = workflow_subparsers.add_parser(
        "list", help="list every workflow in the catalog"
    )
    _add_root_argument(workflow_list)
    workflow_list.add_argument("--json", action="store_true")

    workflow_ready = workflow_subparsers.add_parser(
        "ready", help="list workflows that can run now"
    )
    _add_root_argument(workflow_ready)
    workflow_ready.add_argument(
        "--all", action="store_true", help="include blocked workflows"
    )
    workflow_ready.add_argument("--json", action="store_true")

    workflow_check = workflow_subparsers.add_parser(
        "check", help="report whether one workflow can run"
    )
    workflow_check.add_argument("workflow_id")
    _add_root_argument(workflow_check)
    workflow_check.add_argument("--json", action="store_true")

    workflow_explain = workflow_subparsers.add_parser(
        "explain", help="explain one workflow's requirements in full"
    )
    workflow_explain.add_argument("workflow_id")
    _add_root_argument(workflow_explain)
    workflow_explain.add_argument("--json", action="store_true")


def _summary(readiness: WorkflowReadiness) -> str:
    blockers = (
        "; ".join(item.name for item in readiness.blockers)
        if readiness.blockers
        else ""
    )
    suffix = f" — blocked by {blockers}" if blockers else ""
    return f"{readiness.canonical:<28} {readiness.status}{suffix}"


def _run_list(args: argparse.Namespace, root: Path) -> int:
    catalog = load_catalog(root)
    workflows = catalog_workflows_by_id(catalog)
    rows = [
        {
            "workflow_id": workflow_id,
            "canonical": workflow.get("canonical", canonical_command(workflow_id)),
            "phase": workflow.get("phase"),
            "declares_requirements": bool(workflow.get("requires")),
        }
        for workflow_id, workflow in sorted(workflows.items())
    ]
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="workflow.list",
                data={"count": len(rows), "workflows": rows},
            )
        )
        return 0
    print(f"Workflows ({len(rows)}):")
    for row in rows:
        gate = "" if row["declares_requirements"] else "  (no declared requirements)"
        print(f"- {row['canonical']:<28} {row['phase'] or 'no phase'}{gate}")
    return 0


def _run_ready(args: argparse.Namespace, root: Path) -> int:
    evaluated = list_ready_workflows(root)
    shown = evaluated if args.all else [item for item in evaluated if item.ready]
    recommended = recommend_next_workflow(root)

    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="workflow.ready",
                data={
                    "count": len(shown),
                    "workflows": [item.to_dict() for item in shown],
                    "recommended": (
                        recommended.to_dict() if recommended is not None else None
                    ),
                },
            )
        )
        return 0

    if not shown:
        print("No workflow is currently ready.")
    else:
        print(f"Workflows ({len(shown)}):")
        for item in shown:
            print(f"- {_summary(item)}")

    print("\nRecommended next workflow:")
    if recommended is None:
        # Naming no recommendation is better than naming one the project cannot
        # act on.
        print("- none; resolve the blockers above first.")
    else:
        print(f"- {recommended.canonical}")
    return 0


def _run_check(args: argparse.Namespace, root: Path) -> int:
    readiness = evaluate_workflow_readiness(root, args.workflow_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=readiness.ready,
                operation="workflow.check",
                data=readiness.to_dict(),
            )
        )
        return 0 if readiness.ready else 1
    print(_summary(readiness))
    if readiness.blockers:
        print("\nBlockers:")
        for item in readiness.blockers:
            print(f"- {item.name}: {item.detail}")
        print(f"\nRun `studio workflow explain {args.workflow_id}` for the full list.")
    return 0 if readiness.ready else 1


def _run_explain(args: argparse.Namespace, root: Path) -> int:
    readiness = evaluate_workflow_readiness(root, args.workflow_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=readiness.ready,
                operation="workflow.explain",
                data=readiness.to_dict(),
            )
        )
        return 0
    print(explain_workflow_blockers(readiness))
    return 0


_SUBCOMMANDS = {
    "list": _run_list,
    "ready": _run_ready,
    "check": _run_check,
    "explain": _run_explain,
}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio workflow` subcommand."""

    return _SUBCOMMANDS[args.workflow_command](args, root)
