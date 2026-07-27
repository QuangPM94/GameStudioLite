"""Command-line entry point for Practical Game Studio."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .initialization import (
    InitializationError,
    InitRequest,
    initialize_project,
    is_placeholder_project,
)
from .models import MutationResult
from .reporting import format_status, generate_reports
from .state import StateReadError, StateRepository, find_project_root, load_state
from .transaction import TransactionError
from .validation import validate_project


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        help="PGS repository root (defaults to current/parent discovery)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Practical Game Studio foundation tooling",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="validate framework, schemas, state, and references"
    )
    _add_root_argument(validate_parser)
    status_parser = subparsers.add_parser(
        "status", help="show current milestone direction"
    )
    _add_root_argument(status_parser)
    report_parser = subparsers.add_parser(
        "report", help="generate Markdown reports from canonical JSON"
    )
    _add_root_argument(report_parser)
    init_parser = subparsers.add_parser(
        "init", help="initialize or explicitly update project identity"
    )
    _add_root_argument(init_parser)
    init_parser.add_argument("--name", help="project name")
    init_parser.add_argument("--engine", help="game engine")
    init_parser.add_argument("--engine-version", help="game engine version")
    init_parser.add_argument("--platform", help="target platform")
    init_parser.add_argument("--genre", help="game genre")
    init_parser.add_argument(
        "--review-mode",
        choices=("fast", "guided", "strict"),
        help="review intensity (defaults to guided on first initialization)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="update only explicitly supplied identity fields",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and render the proposal without writing files",
    )
    init_parser.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge a non-interactive forced update",
    )
    return parser


def _display_value(value: object) -> str:
    return str(value) if value not in (None, "") else "Unknown"


def _format_init_result(result: MutationResult) -> str:
    project = result.details["project"]
    already_initialized = result.details["already_initialized"]
    lines: list[str] = []
    if result.dry_run:
        lines.extend(["Dry run — no files were written.", ""])
    elif already_initialized and not result.changed_files:
        lines.extend(["Practical Game Studio is already initialized.", ""])
    else:
        lines.extend(["Practical Game Studio initialized.", ""])

    lines.extend(
        [
            f"Project: {_display_value(project['project_name'])}",
            f"Engine: {_display_value(project['engine'])}",
            f"Platform: {_display_value(project['platform'])}",
            f"Phase: {project['current_phase'].replace('-', ' ').title()}",
            f"Milestone: {project['current_milestone']}",
            f"Review mode: {project['review_mode'].title()}",
            "",
        ]
    )
    if result.changed_fields:
        lines.append("Proposed changes:" if result.dry_run else "Changed fields:")
        for field, change in result.changed_fields.items():
            label = field.replace("_", " ").title()
            lines.append(
                f"- {label}: {_display_value(change['old'])} -> "
                f"{_display_value(change['new'])}"
            )
        lines.append("")

    state_count = sum(
        path.startswith(".studio/state/") for path in result.changed_files
    )
    lines.append(f"State files changed: {state_count}")
    if result.dry_run:
        lines.append(
            f"Reports rendered for validation: {result.report_summary['rendered']}"
        )
        lines.append(f"Affected files: {len(result.changed_files)}")
    elif already_initialized and not result.changed_files:
        lines.append("Reports regenerated: 0")
        lines.append(f"Reports verified in memory: {result.report_summary['rendered']}")
    else:
        lines.append(f"Reports regenerated: {result.report_summary['rendered']}")
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(
        [
            "",
            "Recommended next workflow:",
            result.details["recommended_next_workflow"],
        ]
    )
    if already_initialized and not result.changed_files and not result.dry_run:
        lines.extend(["", "Run `studio status` to review current direction."])
    return "\n".join(lines)


def _run_init(args: argparse.Namespace, root: Path) -> int:
    existing = StateRepository(root).load_project()
    name = args.name
    if is_placeholder_project(existing) and (name is None or not name.strip()):
        if sys.stdin.isatty():
            name = input("Project name: ").strip()
        else:
            print(
                "studio init: missing required values: --name",
                file=sys.stderr,
            )
            return 2

    acknowledged = args.yes
    if args.force and not args.dry_run and not acknowledged:
        if sys.stdin.isatty():
            answer = input(
                "Update only the explicitly supplied project fields? [y/N]: "
            ).strip()
            acknowledged = answer.casefold() in {"y", "yes"}
            if not acknowledged:
                print("studio init: forced update cancelled.", file=sys.stderr)
                return 2
        else:
            print(
                "studio init: --force in a non-interactive terminal requires --yes",
                file=sys.stderr,
            )
            return 2

    request = InitRequest(
        name=name,
        engine=args.engine,
        engine_version=args.engine_version,
        platform=args.platform,
        genre=args.genre,
        review_mode=args.review_mode,
        force=args.force,
        dry_run=args.dry_run,
        acknowledged=acknowledged,
    )
    result = initialize_project(root, request)
    print(_format_init_result(result))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        root = find_project_root(explicit=args.root)
        if args.command == "init":
            return _run_init(args, root)
        if args.command == "validate":
            result = validate_project(root)
            if not result.ok:
                print(
                    f"Validation failed with {len(result.errors)} error(s):",
                    file=sys.stderr,
                )
                for error in result.errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print(
                "Validation passed: framework, schemas, state, and references are valid."
            )
            return 0
        if args.command == "status":
            print(format_status(load_state(root)))
            return 0
        if args.command == "report":
            generated = generate_reports(root)
            print(f"Generated {len(generated)} report(s):")
            for path in generated:
                print(f"- {path.relative_to(root).as_posix()}")
            return 0
    except (
        FileNotFoundError,
        InitializationError,
        KeyError,
        OSError,
        StateReadError,
        TransactionError,
        ValueError,
    ) as exc:
        print(f"studio: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
