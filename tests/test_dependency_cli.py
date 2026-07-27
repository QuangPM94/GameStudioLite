from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.issues import IssueCreateRequest, IssueService


def _issues(root: Path) -> tuple[str, str]:
    service = IssueService(root)
    return tuple(
        service.create_issue(
            IssueCreateRequest(
                title=title,
                severity="blocker",
                description=f"{title} description.",
                milestone_impact=f"{title} gates the milestone.",
            )
        ).details["issue"]["id"]
        for title in ("Prerequisite", "Dependent")
    )


def test_human_add_list_show_deactivate(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prerequisite, dependent = _issues(framework_repo)
    assert (
        cli.main(
            [
                "dependency",
                "add",
                "--root",
                str(framework_repo),
                "--prerequisite",
                prerequisite,
                "--dependent",
                dependent,
                "--reason",
                "Dependent work requires the prerequisite.",
                "--yes",
            ]
        )
        == 0
    )
    assert "Dependency created." in capsys.readouterr().out

    assert cli.main(["dependency", "list", "--root", str(framework_repo)]) == 0
    assert "DEP-0001" in capsys.readouterr().out
    assert (
        cli.main(
            [
                "dependency",
                "show",
                "DEP-0001",
                "--root",
                str(framework_repo),
            ]
        )
        == 0
    )
    assert "Prerequisite satisfied: No" in capsys.readouterr().out
    assert (
        cli.main(
            [
                "dependency",
                "deactivate",
                "DEP-0001",
                "--root",
                str(framework_repo),
                "--reason",
                "Ordering changed.",
                "--yes",
            ]
        )
        == 0
    )
    assert "Dependency deactivated." in capsys.readouterr().out


def test_dependency_json_and_dry_run(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prerequisite, dependent = _issues(framework_repo)
    arguments = [
        "dependency",
        "add",
        "--root",
        str(framework_repo),
        "--prerequisite",
        prerequisite,
        "--dependent",
        dependent,
        "--reason",
        "Required ordering.",
        "--dry-run",
        "--json",
    ]
    assert cli.main(arguments) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "dependency.add"
    assert payload["dry_run"] is True
    assert payload["data"]["dependency"]["id"] == "DEP-0001"


def test_dependency_missing_and_cycle_errors_are_structured(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "dependency",
                "show",
                "DEP-9999",
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 3
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["type"] == "not_found"


def test_dependency_json_reads_and_update(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prerequisite, dependent = _issues(framework_repo)
    assert (
        cli.main(
            [
                "dependency",
                "add",
                "--root",
                str(framework_repo),
                "--prerequisite",
                prerequisite,
                "--dependent",
                dependent,
                "--reason",
                "Required ordering.",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    for command in (
        ["dependency", "list"],
        ["dependency", "show", "DEP-0001"],
    ):
        arguments = [*command, "--root", str(framework_repo), "--json"]
        assert cli.main(arguments) == 0
        first = capsys.readouterr().out
        assert cli.main(arguments) == 0
        second = capsys.readouterr().out
        assert first == second
        assert json.loads(first)["success"] is True
    assert (
        cli.main(
            [
                "dependency",
                "update",
                "DEP-0001",
                "--root",
                str(framework_repo),
                "--reason",
                "Clarified ordering.",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "dependency.update"
