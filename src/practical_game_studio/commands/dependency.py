"""`studio dependency` — track explicit, actionable external dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..dependencies import (
    DependencyCreateRequest,
    DependencyInputError,
    DependencyPatch,
    DependencyService,
)
from ._shared import (
    _add_root_argument,
    _confirm_structural_write,
    _json_envelope,
    _mutation_envelope,
    _path_impact_lines,
    _print_json,
    _required_values,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio dependency` and its subcommands."""

    dependency_parser = subparsers.add_parser(
        "dependency", help="manage explicit actionable dependencies"
    )
    dependency_subparsers = dependency_parser.add_subparsers(
        dest="dependency_command", required=True
    )
    dependency_add = dependency_subparsers.add_parser(
        "add", help="create or reactivate a dependency"
    )
    _add_root_argument(dependency_add)
    dependency_add.add_argument("--prerequisite")
    dependency_add.add_argument("--dependent")
    dependency_add.add_argument("--reason")
    dependency_add.add_argument(
        "--scope",
        choices=("current-milestone", "project"),
        default="current-milestone",
    )
    dependency_add.add_argument("--dry-run", action="store_true")
    dependency_add.add_argument("--json", action="store_true")
    dependency_add.add_argument("--yes", action="store_true")

    dependency_list = dependency_subparsers.add_parser("list", help="list dependencies")
    _add_root_argument(dependency_list)
    dependency_list.add_argument("--status", choices=("active", "inactive"))
    dependency_list.add_argument("--source")
    dependency_list.add_argument("--prerequisite")
    dependency_list.add_argument("--dependent")
    dependency_list.add_argument("--scope", choices=("current-milestone", "project"))
    dependency_view = dependency_list.add_mutually_exclusive_group()
    dependency_view.add_argument("--active", action="store_true")
    dependency_view.add_argument("--all", action="store_true")
    dependency_list.add_argument("--json", action="store_true")

    dependency_show = dependency_subparsers.add_parser(
        "show", help="show one dependency"
    )
    dependency_show.add_argument("dependency_id")
    _add_root_argument(dependency_show)
    dependency_show.add_argument("--json", action="store_true")

    dependency_update = dependency_subparsers.add_parser(
        "update", help="update a dependency"
    )
    dependency_update.add_argument("dependency_id")
    _add_root_argument(dependency_update)
    dependency_update.add_argument("--prerequisite")
    dependency_update.add_argument("--dependent")
    dependency_update.add_argument("--reason")
    dependency_update.add_argument("--scope", choices=("current-milestone", "project"))
    dependency_update.add_argument("--status", choices=("active", "inactive"))
    dependency_update.add_argument("--dry-run", action="store_true")
    dependency_update.add_argument("--json", action="store_true")
    dependency_update.add_argument("--yes", action="store_true")

    dependency_deactivate = dependency_subparsers.add_parser(
        "deactivate", help="deactivate a dependency without deleting history"
    )
    dependency_deactivate.add_argument("dependency_id")
    _add_root_argument(dependency_deactivate)
    dependency_deactivate.add_argument("--reason")
    dependency_deactivate.add_argument("--dry-run", action="store_true")
    dependency_deactivate.add_argument("--json", action="store_true")
    dependency_deactivate.add_argument("--yes", action="store_true")


def _run_dependency_add(args: argparse.Namespace, root: Path) -> int:
    _required_values(
        (
            (args.prerequisite, "--prerequisite"),
            (args.dependent, "--dependent"),
            (args.reason, "--reason"),
        ),
        DependencyInputError,
    )
    _confirm_structural_write(
        args,
        root,
        prompt="Create this explicit dependency?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).create_dependency(
        DependencyCreateRequest(
            prerequisite=args.prerequisite,
            dependent=args.dependent,
            reason=args.reason,
            scope=args.scope,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["dependency"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed dependency.")
    elif result.details["reactivated"]:
        print("Dependency reactivated.")
    else:
        print("Dependency created.")
    print(
        f"\nID: {record['id']}\n\nPrerequisite:\n{record['prerequisite']}"
        f"\n\nDependent:\n{record['dependent']}\n\nRelationship:\n"
        f"{record['dependent']} requires {record['prerequisite']}\n\nReason:\n"
        f"{record['reason']}"
    )
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_dependency_list(args: argparse.Namespace, root: Path) -> int:
    if args.active and args.status == "inactive":
        raise DependencyInputError("--active cannot be combined with inactive status")
    records = DependencyService(root).list_dependencies(
        status="active" if args.active else args.status,
        source=args.source,
        prerequisite=args.prerequisite,
        dependent=args.dependent,
        scope=args.scope,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="dependency.list",
                data={"count": len(records), "dependencies": records},
            )
        )
        return 0
    if not records:
        print("No matching dependencies.")
        return 0
    if args.all:
        label = "Dependencies"
    elif args.status == "inactive":
        label = "Inactive dependencies"
    else:
        label = "Active dependencies"
    print(f"{label}: {len(records)}\n")
    print(f"{'ID':<10}{'Prerequisite':<14}{'Dependent':<14}Scope")
    for record in records:
        print(
            f"{record['id']:<10}{record['prerequisite']:<14}"
            f"{record['dependent']:<14}"
            f"{record['scope'].replace('-', ' ').title()}"
        )
    return 0


def _format_dependency_detail(record: dict[str, Any]) -> str:
    prerequisite_state = {
        "active-unsatisfied": "Active and unsatisfied",
        "satisfied": "Satisfied",
        "terminal-unsatisfied": "Terminal but unsatisfied",
        "invalid-or-missing": "Invalid or missing",
    }[record["prerequisite_state"]]
    lines = [
        f"ID: {record['id']}",
        f"Status: {record['status'].title()}",
        f"Prerequisite: {record['prerequisite']}",
        f"Dependent: {record['dependent']}",
        f"Relationship: {record['dependent']} requires {record['prerequisite']}",
        f"Scope: {record['scope'].replace('-', ' ').title()}",
        f"Prerequisite state: {prerequisite_state}",
        f"Prerequisite source status: {record['prerequisite_status']}",
        f"Prerequisite satisfied: {'Yes' if record['prerequisite_satisfied'] else 'No'}",
        f"Critical-path presence: {'Yes' if record['on_critical_path'] else 'No'}",
        "",
        "Satisfaction reason:",
        record["prerequisite_satisfaction_reason"],
        "",
        "Reason:",
        record["reason"],
    ]
    for heading, values in (
        ("Upstream", record["upstream"]),
        ("Downstream", record["downstream"]),
    ):
        lines.extend(["", f"{heading}:"])
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- None")
    if record["deactivation_reason"]:
        lines.extend(["", "Deactivation reason:", record["deactivation_reason"]])
    lines.extend(
        [
            "",
            f"Created: {record['created_at']}",
            f"Updated: {record['updated_at']}",
        ]
    )
    return "\n".join(lines)


def _run_dependency_show(args: argparse.Namespace, root: Path) -> int:
    record = DependencyService(root).get_dependency(args.dependency_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="dependency.show",
                data={"dependency": record},
            )
        )
    else:
        print(_format_dependency_detail(record))
    return 0


def _run_dependency_update(args: argparse.Namespace, root: Path) -> int:
    _confirm_structural_write(
        args,
        root,
        prompt=f"Update {args.dependency_id}?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).update_dependency(
        args.dependency_id,
        DependencyPatch(
            prerequisite=args.prerequisite,
            dependent=args.dependent,
            reason=args.reason,
            scope=args.scope,
            status=args.status,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed dependency update.")
    elif result.details["no_op"]:
        print("Dependency unchanged.")
    else:
        print("Dependency updated.")
    print(f"\nID: {result.details['dependency']['id']}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_dependency_deactivate(args: argparse.Namespace, root: Path) -> int:
    _required_values(((args.reason, "--reason"),), DependencyInputError)
    _confirm_structural_write(
        args,
        root,
        prompt=f"Deactivate {args.dependency_id}?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).deactivate_dependency(
        args.dependency_id, args.reason, dry_run=args.dry_run
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    print(
        "Dry run — no files were written.\n\nProposed dependency deactivation."
        if result.dry_run
        else "Dependency deactivated."
    )
    print(f"\nID: {result.details['dependency']['id']}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def run(args: argparse.Namespace, root: Path) -> int:
    if args.dependency_command == "add":
        return _run_dependency_add(args, root)
    if args.dependency_command == "list":
        return _run_dependency_list(args, root)
    if args.dependency_command == "show":
        return _run_dependency_show(args, root)
    if args.dependency_command == "update":
        return _run_dependency_update(args, root)
    if args.dependency_command == "deactivate":
        return _run_dependency_deactivate(args, root)
    raise DependencyInputError(f"unknown dependency command {args.dependency_command}")
