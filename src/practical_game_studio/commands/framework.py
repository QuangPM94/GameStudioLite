"""`studio framework` — GameStudioLite framework development commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..validation import validate_framework
from ._shared import _add_root_argument, _json_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio framework` and its subcommands."""

    framework_parser = subparsers.add_parser(
        "framework", help="GameStudioLite framework development commands"
    )
    framework_subparsers = framework_parser.add_subparsers(
        dest="framework_command", required=True
    )
    framework_validate = framework_subparsers.add_parser(
        "validate", help="validate the GameStudioLite framework source repository"
    )
    _add_root_argument(framework_validate)
    framework_validate.add_argument("--json", action="store_true")


def run(args: argparse.Namespace, root: Path) -> int:
    """Validate the framework source repository and packaged scaffold."""

    result = validate_framework(root)
    if getattr(args, "json", False):
        _print_json(
            _json_envelope(
                success=result.ok,
                operation="framework.validate",
                data={"root": str(root), "error_count": len(result.errors)},
                validation={
                    "framework": "passed" if result.ok else "failed",
                    "errors": result.errors,
                },
            )
        )
    elif not result.ok:
        print(
            f"Framework validation failed with {len(result.errors)} error(s):",
            file=sys.stderr,
        )
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(
            "Framework validation passed: project scaffold, source "
            "repository, and packaged resources are valid."
        )
    return 0 if result.ok else 1
