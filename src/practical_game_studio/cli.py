"""Command-line entry point for the Phase A foundation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .reporting import format_status, generate_reports
from .state import find_project_root, load_state
from .validation import validate_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Practical Game Studio foundation tooling",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "validate", help="validate framework, schemas, state, and references"
    )
    subparsers.add_parser("status", help="show current milestone direction")
    subparsers.add_parser(
        "report", help="generate Markdown reports from canonical JSON"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        root = find_project_root()
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
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        print(f"studio: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
