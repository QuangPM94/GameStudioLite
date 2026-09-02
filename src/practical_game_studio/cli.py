"""Command-line entry point for Practical Game Studio.

This module is a router. It assembles the argument parser from the modules in
:mod:`practical_game_studio.commands`, dispatches a parsed command to the module
that owns it, and translates service exceptions into exit codes and JSON error
envelopes. Command behaviour lives in the command modules; domain rules and
state mutation live in the service modules.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .bootstrap import BootstrapConflictError, BootstrapError
from .commands import (
    bootstrap,
    criterion,
    decision,
    dependency,
    evidence,
    framework,
    issue,
    path,
    project,
    report,
)
from .commands._shared import _json_envelope, _print_json
from .criteria import CriterionInputError, CriterionNotFoundError
from .critical_path import CriticalPathInputError, CriticalPathNotFoundError
from .decisions import DecisionInputError, DecisionNotFoundError
from .dependencies import DependencyInputError, DependencyNotFoundError
from .evidence import EvidenceInputError, EvidenceNotFoundError
from .initialization import InitializationError
from .issues import IssueInputError, IssueNotFoundError
from .state import StateReadError, find_project_root
from .transaction import TransactionError

CommandHandler = Callable[[argparse.Namespace, Path], int]

#: Commands that dispatch to a subcommand, mapped to the namespace attribute
#: that carries it. Used to name the failing operation in JSON error envelopes.
_SUBCOMMAND_DESTS = {
    "framework": "framework_command",
    "issue": "issue_command",
    "evidence": "evidence_command",
    "decision": "decision_command",
    "dependency": "dependency_command",
    "criterion": "criterion_command",
    "path": "path_command",
}

#: Commands that run against a discovered project root. ``bootstrap`` is absent
#: because it resolves its own target root before a project exists.
_HANDLERS: dict[str, CommandHandler] = {
    "validate": project.run_validate,
    "framework": framework.run,
    "status": project.run_status,
    "report": report.run,
    "init": project.run_init,
    "issue": issue.run,
    "evidence": evidence.run,
    "decision": decision.run,
    "dependency": dependency.run,
    "criterion": criterion.run,
    "path": path.run,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Practical Game Studio foundation tooling",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    # Registration order is the order commands appear in `studio --help`.
    bootstrap.register(subparsers)
    project.register_validate(subparsers)
    framework.register(subparsers)
    project.register_status(subparsers)
    report.register(subparsers)
    project.register_init(subparsers)
    issue.register(subparsers)
    evidence.register(subparsers)
    decision.register(subparsers)
    dependency.register(subparsers)
    criterion.register(subparsers)
    path.register(subparsers)
    return parser


def _bootstrap_root(args: argparse.Namespace) -> Path:
    if args.root is not None:
        return args.root.expanduser().resolve()
    return Path.cwd().resolve()


def _operation(args: argparse.Namespace) -> str:
    command = getattr(args, "command", None)
    if command == "bootstrap":
        return "project.bootstrap"
    dest = _SUBCOMMAND_DESTS.get(command)
    if dest is not None:
        return f"{command}.{getattr(args, dest, 'unknown')}"
    return command if command is not None else "studio"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "bootstrap":
            return bootstrap.run(args, _bootstrap_root(args))
        root = find_project_root(explicit=args.root)
        handler = _HANDLERS.get(args.command)
        if handler is None:
            return 2
        return handler(args, root)
    except BootstrapConflictError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation="project.bootstrap",
                    dry_run=getattr(args, "dry_run", False),
                    data={
                        "root": str(_bootstrap_root(args)),
                        "conflict_count": len(exc.conflicts),
                        "conflicts": list(exc.conflicts),
                    },
                    error={
                        "type": "conflict",
                        "stage": exc.stage,
                        "message": exc.message,
                        "paths": list(exc.conflicts),
                    },
                )
            )
        else:
            print(f"studio bootstrap: {exc.message}", file=sys.stderr)
        return 1
    except BootstrapError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation="project.bootstrap",
                    dry_run=getattr(args, "dry_run", False),
                    error={
                        "type": "bootstrap",
                        "stage": exc.stage,
                        "message": exc.message,
                    },
                )
            )
        else:
            print(f"studio bootstrap: {exc}", file=sys.stderr)
        return 2 if exc.stage in {"root", "confirmation", "initialization"} else 1
    except (
        CriticalPathNotFoundError,
        CriterionNotFoundError,
        DependencyNotFoundError,
        DecisionNotFoundError,
        EvidenceNotFoundError,
        IssueNotFoundError,
    ) as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={"type": "not_found", "message": str(exc)},
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 3
    except (
        CriticalPathInputError,
        CriterionInputError,
        DependencyInputError,
        DecisionInputError,
        EvidenceInputError,
        IssueInputError,
    ) as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={"type": "usage", "message": str(exc)},
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 2
    except TransactionError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={
                        "type": "transaction",
                        "stage": exc.stage,
                        "message": exc.message,
                    },
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 1
    except (
        FileNotFoundError,
        InitializationError,
        KeyError,
        OSError,
        StateReadError,
        ValueError,
    ) as exc:
        print(f"studio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
