"""Helpers shared by the `studio` command modules.

Command modules own argument registration and human/JSON presentation for one
noun. Anything that more than one of them needs lives here so that presentation
logic is written once.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..models import MutationResult
from ..state import StateRepository
from ..workflow_commands import canonical_command


def _recommended_workflow_block(details: dict[str, Any]) -> str:
    """Render the recommended-next-workflow footer.

    Services return the workflow id; the canonical `GS:` command is what a
    reader types. Keeping the translation here means adding another spelling
    never means touching four command modules.
    """

    command = canonical_command(details["recommended_next_workflow"])
    return f"\nRecommended next workflow:\n{command}"


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        help="PGS repository root (defaults to current/parent discovery)",
    )


def _json_envelope(
    *,
    success: bool,
    operation: str,
    data: Any = None,
    dry_run: bool = False,
    changed_files: Sequence[str] = (),
    unchanged_files: Sequence[str] = (),
    changed_fields: dict[str, Any] | None = None,
    warnings: Sequence[str] = (),
    validation: dict[str, Any] | None = None,
    reports: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": success,
        "operation": operation,
        "dry_run": dry_run,
        "changed_files": list(changed_files),
        "unchanged_files": list(unchanged_files),
        "changed_fields": changed_fields or {},
        "warnings": list(warnings),
        "data": data,
        "validation": validation or {},
        "reports": reports or {},
    }
    if error is not None:
        payload["error"] = error
    return payload


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _mutation_envelope(result: MutationResult) -> dict[str, Any]:
    return _json_envelope(
        success=result.success,
        operation=result.operation,
        data=result.details,
        dry_run=result.dry_run,
        changed_files=result.changed_files,
        unchanged_files=result.unchanged_files,
        changed_fields=result.changed_fields,
        warnings=result.warnings,
        validation=result.validation_summary,
        reports=result.report_summary,
    )


def _confirm_structural_write(
    args: argparse.Namespace,
    root: Path,
    *,
    prompt: str,
    error_type: type[ValueError],
) -> None:
    if args.dry_run:
        return
    review_mode = StateRepository(root).load_project()["review_mode"]
    if review_mode == "fast" or args.yes:
        return
    if sys.stdin.isatty() and not args.json:
        answer = input(f"{prompt} [y/N]: ").strip().casefold()
        if answer in {"y", "yes"}:
            return
        raise error_type("operation cancelled")
    raise error_type(
        f"{review_mode} review mode requires --yes in a non-interactive terminal"
    )


def _required_values(
    values: Sequence[tuple[str | None, str]], error_type: type[ValueError]
) -> None:
    missing = [flag for value, flag in values if value is None or not value.strip()]
    if missing:
        raise error_type("missing required values: " + ", ".join(missing))


def _path_impact_lines(details: dict[str, Any]) -> list[str]:
    impact = details.get("path_impact", "may-be-stale")
    if impact == "stale":
        message = "The current milestone critical path is stale."
    elif impact == "none":
        message = "The current milestone critical path was not changed."
    else:
        message = "The current milestone critical path may be stale."
    return [
        "",
        "Critical-path impact:",
        message,
        "",
        "Recommended next command:",
        details.get("recommended_next_command", "studio path check"),
    ]
