"""Structural guards for the `studio` command package.

These tests protect the Sprint 0 refactor: `cli.py` stays a router, every
command noun keeps its own module, and the published command surface stays
exactly what `docs/baseline.md` records. Behavioural coverage for each command
lives in the per-command CLI test modules.
"""

from __future__ import annotations

import argparse

import pytest

from practical_game_studio import cli
from practical_game_studio.commands import (
    artifact,
    bootstrap,
    criterion,
    decision,
    dependency,
    doctor,
    evidence,
    execute,
    execution,
    framework,
    issue,
    path,
    project,
    report,
    upgrade,
    workflow,
)

#: The baseline command surface. Extending it is a deliberate, documented act.
EXPECTED_COMMANDS = (
    "bootstrap",
    "validate",
    "framework",
    "status",
    "report",
    "init",
    "upgrade",
    "issue",
    "evidence",
    "decision",
    "dependency",
    "criterion",
    "path",
    "workflow",
    "execution",
    "artifact",
    "doctor",
    "run",
    "test",
    "build",
    "verify",
)

EXPECTED_SUBCOMMANDS = {
    "framework": ("validate",),
    "upgrade": ("check", "plan", "apply"),
    "issue": ("add", "list", "show", "update"),
    "evidence": ("add", "list", "show", "update"),
    "decision": ("add", "list", "show", "update", "resolve"),
    "dependency": ("add", "list", "show", "update", "deactivate"),
    "criterion": (
        "add",
        "list",
        "show",
        "update",
        "evaluate",
        "retire",
        "support",
    ),
    "path": ("calculate", "show", "explain", "check"),
    "execution": ("list", "show"),
    "artifact": ("add", "list", "show", "verify"),
    "workflow": ("list", "ready", "check", "explain"),
}


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser exposes no subcommands")


def test_command_order_matches_the_recorded_baseline() -> None:
    action = _subparsers_action(cli._parser())

    assert tuple(action.choices) == EXPECTED_COMMANDS


@pytest.mark.parametrize("command", sorted(EXPECTED_SUBCOMMANDS))
def test_subcommand_order_matches_the_recorded_baseline(command: str) -> None:
    parent = _subparsers_action(cli._parser()).choices[command]

    assert tuple(_subparsers_action(parent).choices) == EXPECTED_SUBCOMMANDS[command]


def test_every_command_routes_to_a_command_module() -> None:
    routed = set(cli._HANDLERS) | {"bootstrap"}

    assert routed == set(EXPECTED_COMMANDS)


def test_command_modules_expose_registration_and_a_handler() -> None:
    for module in (
        artifact,
        bootstrap,
        doctor,
        criterion,
        decision,
        dependency,
        evidence,
        execution,
        framework,
        issue,
        path,
        report,
        upgrade,
        workflow,
    ):
        assert callable(module.register), module.__name__
        assert callable(module.run), module.__name__

    # `project` and `execute` each own several commands, so they register them
    # individually rather than through one `register`.
    for name in ("register_run", "register_test", "register_build", "register_verify"):
        assert callable(getattr(execute, name)), name
    for name in ("run_run", "run_test", "run_build", "run_verify"):
        assert callable(getattr(execute, name)), name

    for name in ("register_validate", "register_status", "register_init"):
        assert callable(getattr(project, name))
    for name in ("run_validate", "run_status", "run_init"):
        assert callable(getattr(project, name))


def test_cli_module_holds_no_command_implementations() -> None:
    """`cli.py` routes; it must not grow domain rendering again."""

    implementation_prefixes = ("_run_", "_format_")
    leaked = [
        name
        for name in vars(cli)
        if name.startswith(implementation_prefixes) and callable(getattr(cli, name))
    ]

    assert leaked == []


def test_operation_names_survive_the_router_split() -> None:
    namespace = argparse.Namespace(command="criterion", criterion_command="evaluate")

    assert cli._operation(namespace) == "criterion.evaluate"
    assert (
        cli._operation(argparse.Namespace(command="bootstrap")) == "project.bootstrap"
    )
    assert cli._operation(argparse.Namespace(command="status")) == "status"
    assert cli._operation(argparse.Namespace(command="issue")) == "issue.unknown"
