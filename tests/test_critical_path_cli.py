from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.dependencies import (
    DependencyCreateRequest,
    DependencyService,
)
from practical_game_studio.issues import IssueCreateRequest, IssueService


def _add_blocker(root: Path) -> None:
    IssueService(root).create_issue(
        IssueCreateRequest(
            title="Prototype does not launch",
            severity="blocker",
            milestone_impact="No prototype evaluation can begin.",
            recommended_action="Launch successfully from a clean checkout.",
        )
    )


def test_human_calculate_show_explain_check(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_blocker(framework_repo)

    assert (
        cli.main(
            [
                "path",
                "calculate",
                "--root",
                str(framework_repo),
                "--yes",
            ]
        )
        == 0
    )
    calculated = capsys.readouterr()
    assert "Milestone critical path calculated." in calculated.out
    assert "Recommended next action:" in calculated.out

    assert cli.main(["path", "show", "--root", str(framework_repo)]) == 0
    shown = capsys.readouterr()
    assert "Milestone critical path:" in shown.out
    assert "Freshness: Current" in shown.out

    assert (
        cli.main(
            [
                "path",
                "explain",
                "CP-0001",
                "--root",
                str(framework_repo),
            ]
        )
        == 0
    )
    explained = capsys.readouterr()
    assert "Why this item is on the path:" in explained.out
    assert "Completion condition:" in explained.out

    assert cli.main(["path", "check", "--root", str(framework_repo)]) == 0
    checked = capsys.readouterr()
    assert "Critical path is current." in checked.out


@pytest.mark.parametrize("command", ["show", "check"])
def test_json_read_commands_are_stable_and_json_only(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    arguments = ["path", command, "--root", str(framework_repo), "--json"]

    assert cli.main(arguments) == 0
    first = capsys.readouterr()
    assert cli.main(arguments) == 0
    second = capsys.readouterr()

    assert first.out == second.out
    assert first.err == second.err == ""
    payload = json.loads(first.out)
    assert payload["success"] is True
    assert payload["operation"] == f"path.{command}"


def test_json_calculate_and_explain(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_blocker(framework_repo)
    assert (
        cli.main(
            [
                "path",
                "calculate",
                "--root",
                str(framework_repo),
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    calculated = json.loads(capsys.readouterr().out)
    assert calculated["operation"] == "path.calculate"
    item_id = calculated["data"]["items"][0]["id"]

    assert (
        cli.main(
            [
                "path",
                "explain",
                item_id,
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 0
    )
    explained = json.loads(capsys.readouterr().out)
    assert explained["data"]["item"]["id"] == item_id


def test_path_explain_exposes_prerequisite_satisfaction(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = IssueService(framework_repo)
    prerequisite = service.create_issue(
        IssueCreateRequest(
            title="Prepare fixture",
            severity="major",
            milestone_impact="The blocker depends on this fixture.",
        )
    ).details["issue"]["id"]
    dependent = service.create_issue(
        IssueCreateRequest(
            title="Run blocker verification",
            severity="blocker",
            milestone_impact="The milestone is blocked.",
        )
    ).details["issue"]["id"]
    DependencyService(framework_repo).create_dependency(
        DependencyCreateRequest(
            prerequisite,
            dependent,
            "The verification needs the fixture.",
        )
    )
    assert (
        cli.main(
            [
                "path",
                "calculate",
                "--root",
                str(framework_repo),
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    calculated = json.loads(capsys.readouterr().out)
    dependent_id = next(
        item["id"]
        for item in calculated["data"]["items"]
        if item["source_id"] == dependent
    )

    assert (
        cli.main(
            [
                "path",
                "explain",
                dependent_id,
                "--root",
                str(framework_repo),
            ]
        )
        == 0
    )
    assert "Prerequisite state: Active and unsatisfied" in capsys.readouterr().out

    assert (
        cli.main(
            [
                "path",
                "explain",
                dependent_id,
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 0
    )
    dependency_state = json.loads(capsys.readouterr().out)["data"]["dependency_states"][
        0
    ]
    assert dependency_state["dependency_id"] == "DEP-0001"
    assert dependency_state["prerequisite_terminal"] is False
    assert dependency_state["prerequisite_satisfied"] is False
    assert dependency_state["prerequisite_valid"] is True


def test_cli_dry_run_and_include_exclude(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_blocker(framework_repo)
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Optional polish",
            severity="minor",
            player_impact="Small presentation issue.",
        )
    )
    path = framework_repo / ".studio/state/critical-path.json"
    before = path.read_bytes()

    exit_code = cli.main(
        [
            "path",
            "calculate",
            "--root",
            str(framework_repo),
            "--include",
            "ISS-0002",
            "--exclude",
            "ISS-0001",
            "--exclude-reason",
            "External build fix pending.",
            "--dry-run",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Dry run — no files were written." in output.out
    assert path.read_bytes() == before


def test_cli_invalid_max_and_missing_item_have_structured_errors(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = cli.main(
        [
            "path",
            "calculate",
            "--root",
            str(framework_repo),
            "--max-items",
            "2",
            "--dry-run",
            "--json",
        ]
    )
    invalid_payload = json.loads(capsys.readouterr().out)
    missing = cli.main(
        [
            "path",
            "explain",
            "CP-9999",
            "--root",
            str(framework_repo),
            "--json",
        ]
    )
    missing_payload = json.loads(capsys.readouterr().out)

    assert invalid == 2
    assert invalid_payload["error"]["type"] == "usage"
    assert missing == 3
    assert missing_payload["error"]["type"] == "not_found"


def test_guided_noninteractive_requires_yes(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NonInteractive:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(cli.sys, "stdin", NonInteractive())

    exit_code = cli.main(["path", "calculate", "--root", str(framework_repo)])
    output = capsys.readouterr()

    assert exit_code == 2
    assert "requires --yes" in output.err


def test_fast_mode_does_not_require_confirmation(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_path = framework_repo / ".studio/state/project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["review_mode"] = "fast"
    project_path.write_text(
        json.dumps(project, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert cli.main(["path", "calculate", "--root", str(framework_repo)]) == 0
    assert "Milestone critical path calculated." in capsys.readouterr().out
