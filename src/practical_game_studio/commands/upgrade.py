"""`studio upgrade` — check, plan, and apply a scaffold upgrade."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..migrations import (
    MigrationInputError,
    MigrationPlan,
    apply_migration,
    get_current_version,
    get_target_version,
    plan_migration,
)
from ..safety import classify
from ._shared import (
    _add_root_argument,
    _confirm_structural_write,
    _json_envelope,
    _mutation_envelope,
    _print_json,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio upgrade` and its subcommands."""

    upgrade_parser = subparsers.add_parser(
        "upgrade", help="upgrade project scaffold and canonical state"
    )
    upgrade_subparsers = upgrade_parser.add_subparsers(
        dest="upgrade_command", required=True
    )

    upgrade_check = upgrade_subparsers.add_parser(
        "check", help="report whether an upgrade is available"
    )
    _add_root_argument(upgrade_check)
    upgrade_check.add_argument("--json", action="store_true")

    upgrade_plan = upgrade_subparsers.add_parser(
        "plan", help="show what an upgrade would change"
    )
    _add_root_argument(upgrade_plan)
    upgrade_plan.add_argument("--json", action="store_true")

    upgrade_apply = upgrade_subparsers.add_parser(
        "apply", help="run the resolved migration chain"
    )
    _add_root_argument(upgrade_apply)
    upgrade_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="stage and validate the upgrade without writing project files",
    )
    upgrade_apply.add_argument(
        "--yes", action="store_true", help="acknowledge a non-interactive upgrade"
    )
    upgrade_apply.add_argument("--json", action="store_true")


def _section(title: str, entries: tuple[str, ...]) -> list[str]:
    """Render one plan section, naming an empty section rather than hiding it.

    A reviewer must be able to tell "this upgrade destroys nothing" from "the
    plan forgot to mention destruction", so an empty list still prints.
    """

    return ["", f"{title}:", *(f"- {entry}" for entry in entries or ("none",))]


def _format_plan(plan: MigrationPlan) -> str:
    lines = [
        f"Source version: {plan.source_version}",
        f"Target version: {plan.target_version}",
    ]
    if plan.up_to_date:
        lines.append("")
        lines.append("Migrations: none; the project is already at the target version.")
        return "\n".join(lines)

    lines.extend(
        _section(
            f"Migrations ({len(plan.migrations)})",
            tuple(
                f"{migration.id} ({migration.from_version} -> "
                f"{migration.to_version}): {migration.summary}"
                for migration in plan.migrations
            ),
        )
    )
    lines.extend(
        _section(f"Affected files ({len(plan.affected_files)})", plan.affected_files)
    )
    lines.extend(_section("Destructive changes", plan.destructive_changes))
    lines.extend(_section("Manual actions", plan.manual_actions))
    lines.extend(_section("Expected compatibility impact", plan.compatibility_impact))
    return "\n".join(lines)


def _run_check(args: argparse.Namespace, root: Path) -> int:
    current = get_current_version(root)
    target = get_target_version()
    plan = plan_migration(root)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="upgrade.check",
                data={
                    "root": str(root),
                    "current_version": current,
                    "target_version": target,
                    "up_to_date": plan.up_to_date,
                    "pending_migrations": [
                        migration.id for migration in plan.migrations
                    ],
                },
            )
        )
        return 0
    if plan.up_to_date:
        print(f"Scaffold version {current} is current; no upgrade is available.")
        return 0
    pending = ", ".join(migration.id for migration in plan.migrations)
    print(
        f"Scaffold version {current} can upgrade to {target}.\n"
        f"Pending migrations: {pending}\n\n"
        "Recommended next command:\nstudio upgrade plan"
    )
    return 0


def _run_plan(args: argparse.Namespace, root: Path) -> int:
    plan = plan_migration(root)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="upgrade.plan",
                data=plan.to_dict(),
                changed_files=plan.affected_files,
            )
        )
        return 0
    print(_format_plan(plan))
    return 0


def _run_apply(args: argparse.Namespace, root: Path) -> int:
    plan = plan_migration(root)
    if plan.up_to_date:
        result = apply_migration(root, dry_run=args.dry_run)
        if args.json:
            _print_json(_mutation_envelope(result))
        else:
            print(
                f"Scaffold version {plan.source_version} is current; "
                "no migration was applied."
            )
        return 0

    _confirm_structural_write(
        args,
        root,
        prompt=(
            f"Upgrade scaffold {plan.source_version} -> {plan.target_version} "
            f"and migrate {len(plan.affected_files)} file(s)? "
            f"({classify('upgrade.apply')} risk)"
        ),
        error_type=MigrationInputError,
    )
    result = apply_migration(root, dry_run=args.dry_run)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0

    verb = "would change" if result.dry_run else "changed"
    print(_format_plan(plan))
    print(f"\nUpgrade {verb} {len(result.changed_files)} file(s).")
    for relative in result.changed_files:
        print(f"- {relative}")
    if not result.dry_run:
        print("\nRecommended next command:\nstudio validate")
    return 0


_SUBCOMMANDS = {"check": _run_check, "plan": _run_plan, "apply": _run_apply}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio upgrade` subcommand."""

    return _SUBCOMMANDS[args.upgrade_command](args, root)
