"""`studio bootstrap` — attach the framework to a game repository."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ..bootstrap import BootstrapError, BootstrapRequest, BootstrapService
from ..models import MutationResult
from ._shared import _mutation_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio bootstrap`."""

    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="attach Practical Game Studio to a game repository"
    )
    bootstrap_parser.add_argument(
        "--root",
        type=Path,
        help="target game root (defaults to the current working directory)",
    )
    bootstrap_parser.add_argument("--name", help="project name")
    bootstrap_parser.add_argument("--engine", help="game engine")
    bootstrap_parser.add_argument("--engine-version", help="game engine version")
    bootstrap_parser.add_argument("--platform", help="target platform")
    bootstrap_parser.add_argument("--genre", help="game genre")
    bootstrap_parser.add_argument(
        "--review-mode",
        choices=("fast", "guided", "strict"),
        help="review intensity (defaults to guided during initialization)",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="replace conflicting framework-managed files only",
    )
    bootstrap_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the proposed scaffold without writing target files",
    )
    bootstrap_parser.add_argument(
        "--json", action="store_true", help="emit one JSON result envelope"
    )
    bootstrap_parser.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge non-interactive managed-file replacement",
    )
    bootstrap_parser.add_argument(
        "--open-brief",
        action="store_true",
        help="open GAME_BRIEF.md after a successful non-dry-run bootstrap",
    )


def _format_bootstrap_result(result: MutationResult) -> str:
    details = result.details
    changed = details["created_count"] + details["updated_count"]
    lines: list[str] = []
    if result.dry_run:
        lines.extend(
            [
                "Dry run — no files were written.",
                "",
                "Proposed Practical Game Studio scaffold.",
            ]
        )
    elif changed == 0:
        lines.append("Practical Game Studio project scaffold is already present.")
    else:
        lines.append("Practical Game Studio project scaffold created.")
    lines.extend(
        [
            "",
            "Root:",
            details["root"],
            "",
            (
                f"Files to create: {details['created_count']}"
                if result.dry_run
                else f"Files created: {details['created_count']}"
            ),
            (
                f"Files to update: {details['updated_count']}"
                if result.dry_run
                else f"Files updated: {details['updated_count']}"
            ),
            (
                f"Files to preserve: {details['preserved_count']}"
                if result.dry_run
                else f"Files preserved: {details['preserved_count']}"
            ),
            f"Conflicts: {details['conflict_count']}",
            "",
            "Project state:",
            "Initialized" if details["initialized"] else "Not initialized",
        ]
    )
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(
        [
            "",
            "Recommended next command:",
            details["recommended_next_command"],
            "",
            "Starter game brief:",
            details["starter_brief_path"],
        ]
    )
    return "\n".join(lines)


def _open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen(
        [command, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run(args: argparse.Namespace, root: Path) -> int:
    def attempt(acknowledged: bool) -> MutationResult:
        return BootstrapService(root).bootstrap(
            BootstrapRequest(
                name=args.name,
                engine=args.engine,
                engine_version=args.engine_version,
                platform=args.platform,
                genre=args.genre,
                review_mode=args.review_mode,
                force=args.force,
                dry_run=args.dry_run,
                acknowledged=acknowledged,
            )
        )

    try:
        result = attempt(args.yes)
    except BootstrapError as exc:
        if exc.stage != "confirmation" or args.json or not sys.stdin.isatty():
            raise
        answer = input(
            "Replace conflicting framework-managed files while preserving "
            "project state and reports? [y/N]: "
        ).strip()
        if answer.casefold() not in {"y", "yes"}:
            print("studio bootstrap: forced refresh cancelled.", file=sys.stderr)
            return 2
        result = attempt(True)
    if args.json:
        _print_json(_mutation_envelope(result))
    else:
        print(_format_bootstrap_result(result))
    if args.open_brief and not result.dry_run:
        _open_path(Path(result.details["starter_brief_path"]))
    return 0
