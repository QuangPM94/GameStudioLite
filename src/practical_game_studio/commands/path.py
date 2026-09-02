"""`studio path` — calculate and inspect the milestone critical path."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..critical_path import (
    CriticalPathInputError,
    CriticalPathService,
    PathCalculationRequest,
)
from ..state import StateRepository
from ._shared import _add_root_argument, _json_envelope, _mutation_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio path` and its subcommands."""

    path_parser = subparsers.add_parser(
        "path", help="calculate and inspect the milestone critical path"
    )
    path_subparsers = path_parser.add_subparsers(dest="path_command", required=True)
    path_calculate = path_subparsers.add_parser(
        "calculate", help="calculate the dependency-aware milestone path"
    )
    _add_root_argument(path_calculate)
    path_calculate.add_argument("--milestone")
    path_calculate.add_argument("--include", action="append", default=[])
    path_calculate.add_argument("--exclude", action="append", default=[])
    path_calculate.add_argument("--exclude-reason")
    path_calculate.add_argument("--max-items", type=int, default=7)
    path_calculate.add_argument("--dry-run", action="store_true")
    path_calculate.add_argument("--json", action="store_true")
    path_calculate.add_argument("--yes", action="store_true")

    path_show = path_subparsers.add_parser(
        "show", help="show the current milestone path"
    )
    _add_root_argument(path_show)
    path_show.add_argument("--all", action="store_true")
    path_show.add_argument("--json", action="store_true")

    path_explain = path_subparsers.add_parser(
        "explain", help="explain why one item gates the milestone"
    )
    path_explain.add_argument("path_item_id")
    _add_root_argument(path_explain)
    path_explain.add_argument("--json", action="store_true")

    path_check = path_subparsers.add_parser(
        "check", help="check whether the current path is stale"
    )
    _add_root_argument(path_check)
    path_check.add_argument("--json", action="store_true")


def _confirm_path_calculation(args: argparse.Namespace, root: Path) -> None:
    if args.dry_run:
        return
    review_mode = StateRepository(root).load_project()["review_mode"]
    if review_mode == "fast" or args.yes:
        return
    if sys.stdin.isatty() and not args.json:
        answer = (
            input("Calculate and persist the proposed milestone critical path? [y/N]: ")
            .strip()
            .casefold()
        )
        if answer in {"y", "yes"}:
            return
        raise CriticalPathInputError("path calculation cancelled")
    raise CriticalPathInputError(
        f"{review_mode} review mode requires --yes in a non-interactive terminal"
    )


def _path_item_source(item: dict[str, Any]) -> str:
    return item.get("source_id") or item["source_key"]


def _recommended_type_label(item: dict[str, Any]) -> str:
    return {
        "decision": "Next required user decision",
        "issue": "Recommended implementation",
        "verification": "Recommended verification",
    }.get(item["type"], "Recommended action")


def _format_path_items(items: Sequence[dict[str, Any]]) -> str:
    if not items:
        return "No active milestone critical path.\nRun:\nstudio path calculate"
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item['id']} — {item['title']}",
                f"   Source: {_path_item_source(item)}",
                f"   Status: {item['status'].replace('-', ' ').title()}",
            ]
        )
        if item["dependencies"]:
            lines.append(f"   Depends on: {', '.join(item['dependencies'])}")
    return "\n".join(lines)


def _run_path_calculate(args: argparse.Namespace, root: Path) -> int:
    _confirm_path_calculation(args, root)
    result = CriticalPathService(root).apply_path(
        PathCalculationRequest(
            milestone=args.milestone,
            include=tuple(args.include),
            exclude=tuple(args.exclude),
            exclude_reason=args.exclude_reason,
            max_items=args.max_items,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    details = result.details
    if result.dry_run:
        print("Dry run — no files were written.\n")
    if details["no_op"]:
        print("Milestone critical path is unchanged.")
    else:
        print("Milestone critical path calculated.")
    print(f"\nMilestone:\n{details['milestone']}")
    print(f"\nActive items: {details['active_count']}\n")
    print(_format_path_items(details["items"]))
    recommended = next(
        (
            item
            for item in details["items"]
            if item["id"] == details["recommended_next"]
        ),
        None,
    )
    print("\nRecommended next action:")
    print(
        f"{_recommended_type_label(recommended)}: "
        f"{recommended['id']} — {recommended['title']}"
        if recommended
        else "None identified."
    )
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    label = (
        "Reports rendered for validation" if result.dry_run else "Reports regenerated"
    )
    rendered = (
        result.report_summary["rendered"]
        if result.dry_run or not details["no_op"]
        else 0
    )
    print(f"\n{label}: {rendered}")
    return 0


def _run_path_show(args: argparse.Namespace, root: Path) -> int:
    data = CriticalPathService(root).show_path(include_history=args.all)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.show",
                data=data,
            )
        )
        return 0
    print(f"Current milestone:\n{data['milestone']}")
    print("\nMilestone critical path:\n")
    print(_format_path_items(data["items"]))
    if data["items"]:
        recommended = next(
            (item for item in data["items"] if item["id"] == data["recommended_next"]),
            None,
        )
        print("\nRecommended next action:")
        print(
            f"{_recommended_type_label(recommended)}: "
            f"{recommended['id']} — {recommended['title']}"
            if recommended
            else "None identified."
        )
    print("\nBlocked items:")
    print("\n".join(f"- {item}" for item in data["blocked_items"]) or "- None")
    print("\nManual inclusions:")
    print("\n".join(f"- {item}" for item in data["pinned_sources"]) or "- None")
    if data["excluded_sources"]:
        print("\nManual exclusions:")
        for source in data["excluded_sources"]:
            print(f"- {source}: {data['exclusion_reasons'][source]}")
    print("\nDo not work on yet:")
    for item in data["non_critical_work"]:
        print(f"- {item}")
    print(f"\nLast calculated: {data['calculated_at'] or 'Never'}")
    print(f"Freshness: {data['freshness']['status'].title()}")
    if args.all:
        print("\nCompleted and removed history:")
        history = data.get("history", [])
        if history:
            for item in history:
                print(f"- {item['id']} [{item['status']}] — {item['title']}")
        else:
            print("- None")
    return 0


def _run_path_explain(args: argparse.Namespace, root: Path) -> int:
    explanation = CriticalPathService(root).explain_item(args.path_item_id)
    data = explanation.to_dict()
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.explain",
                data=data,
            )
        )
        return 0
    item = data["item"]
    print(f"{item['id']} — {item['title']}")
    print(f"\nSource:\n{_path_item_source(item)}")
    print(f"\nSource state:\n{item['source_status']}")
    print(f"\nWhy this item is on the path:\n{item['reason']}")
    print(f"\nMilestone impact:\n{item['milestone_impact']}")
    print(f"\nPriority tier:\n{item['priority_tier']}")
    print("\nDependencies:")
    print("\n".join(f"- {value}" for value in item["dependencies"]) or "- None")
    print("\nPrerequisite states:")
    if data["dependency_states"]:
        labels = {
            "active-unsatisfied": "Active and unsatisfied",
            "satisfied": "Satisfied",
            "terminal-unsatisfied": "Terminal but unsatisfied",
            "invalid-or-missing": "Invalid or missing",
        }
        for dependency in data["dependency_states"]:
            dependency_label = dependency["dependency_id"] or "Derived relationship"
            print(
                f"- {dependency_label}: {dependency['prerequisite']}\n"
                f"  Prerequisite state: "
                f"{labels[dependency['prerequisite_state']]}\n"
                f"  {dependency['prerequisite_satisfaction_reason']}"
            )
    else:
        print("- None")
    print("\nDependency origin:")
    if item["dependency_origins"]:
        for origin in item["dependency_origins"]:
            if origin["origin"] == "explicit":
                print(f"- Explicit — {origin['dependency_id']}: {origin['reason']}")
            else:
                print(f"- Derived — {origin['reason']}")
    else:
        print("- None")
    print("\nBlocks:")
    print("\n".join(f"- {value}" for value in data["downstream_items"]) or "- None")
    print(f"\nEvidence state:\n{item['evidence_state']}")
    print(f"\nCompletion condition:\n{item['completion_condition']}")
    print(f"\nWhy delaying it delays the milestone:\n{item['milestone_impact']}")
    print("\nWhy lower-priority alternatives were not selected:")
    print(
        "\n".join(f"- {value}" for value in data["lower_priority_alternatives"])
        or "- No lower-priority milestone-gating alternative was identified."
    )
    if data["manual_context"]:
        print(f"\nManual context:\n{data['manual_context']}")
    source = data["source"]
    if source and str(item.get("source_id") or "").startswith("MC-"):
        print(f"\nCriterion:\n{source['description']}")
        print(f"\nCurrent support:\n{source['support_status']}")
        print(f"\nCriterion completion condition:\n{source['completion_condition']}")
        print(
            "\nCurrent evidence:\n"
            + (
                "\n".join(f"- {value}" for value in source["supporting_evidence"])
                or "- None"
            )
        )
        if source["evaluation_reason"]:
            print(f"\nEvaluation reason:\n{source['evaluation_reason']}")
    return 0


def _run_path_check(args: argparse.Namespace, root: Path) -> int:
    freshness = CriticalPathService(root).check_freshness()
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.check",
                data=freshness.to_dict(),
            )
        )
        return 0
    if freshness.status == "current":
        print("Critical path is current.")
        return 0
    if freshness.status == "absent":
        print("No active milestone critical path.")
        print("Run:\nstudio path calculate")
        return 0
    print("Critical path is stale.\n\nReasons:")
    for reason in freshness.reasons:
        print(f"- {reason}")
    print("\nRecommended action:\nstudio path calculate")
    return 0


def run(args: argparse.Namespace, root: Path) -> int:
    if args.path_command == "calculate":
        return _run_path_calculate(args, root)
    if args.path_command == "show":
        return _run_path_show(args, root)
    if args.path_command == "explain":
        return _run_path_explain(args, root)
    if args.path_command == "check":
        return _run_path_check(args, root)
    raise CriticalPathInputError(f"unknown path command {args.path_command}")
