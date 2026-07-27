from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli


def _add_args(root: Path, *extra: str) -> list[str]:
    return [
        "issue",
        "add",
        "--root",
        str(root),
        "--title",
        "Player cannot identify the delivery room",
        "--severity",
        "critical",
        "--player-impact",
        "The player stops progressing.",
        "--yes",
        *extra,
    ]


def test_issue_add_human_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    output = capsys.readouterr()
    assert "Issue created." in output.out
    assert "ID: ISS-0001" in output.out
    assert "Recommended next workflow:\n/issue-map" in output.out
    assert output.err == ""


def test_issue_add_json_output_is_valid(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo, "--json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["operation"] == "issue.add"
    assert payload["data"]["issue"]["id"] == "ISS-0001"


def test_issue_add_dry_run_does_not_require_confirmation(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo, "--dry-run")
    args.remove("--yes")
    assert cli.main(args) == 0
    output = capsys.readouterr()
    assert "Dry run — no files were written." in output.out


def test_guided_noninteractive_add_requires_yes(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _add_args(framework_repo)
    args.remove("--yes")
    assert cli.main(args) == 2
    assert "requires --yes" in capsys.readouterr().err


def test_fast_mode_does_not_require_confirmation(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_path = framework_repo / ".studio" / "state" / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["review_mode"] = "fast"
    project_path.write_text(json.dumps(project), encoding="utf-8")
    args = _add_args(framework_repo)
    args.remove("--yes")
    assert cli.main(args) == 0
    assert "Issue created." in capsys.readouterr().out


def test_missing_required_add_values_fail_without_traceback(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["issue", "add", "--root", str(framework_repo)]) == 2
    output = capsys.readouterr()
    assert "--title" in output.err
    assert "--severity" in output.err
    assert "Traceback" not in output.err


def test_list_show_update_human_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    capsys.readouterr()
    assert cli.main(["issue", "list", "--root", str(framework_repo)]) == 0
    listed = capsys.readouterr()
    assert "Open issues: 1" in listed.out
    assert "ISS-0001" in listed.out

    assert cli.main(["issue", "show", "ISS-0001", "--root", str(framework_repo)]) == 0
    shown = capsys.readouterr()
    assert "Player impact:" in shown.out
    assert "Evidence type:" in shown.out

    assert (
        cli.main(
            [
                "issue",
                "update",
                "ISS-0001",
                "--root",
                str(framework_repo),
                "--status",
                "resolved",
                "--resolution",
                "Added directional signage.",
            ]
        )
        == 0
    )
    updated = capsys.readouterr()
    assert "Issue updated." in updated.out
    assert "- status" in updated.out
    assert "- resolution" in updated.out


def test_list_json_is_stable_and_terminal_hidden_by_default(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    cli.main(
        [
            "issue",
            "update",
            "ISS-0001",
            "--root",
            str(framework_repo),
            "--status",
            "resolved",
            "--resolution",
            "Fixed.",
        ]
    )
    capsys.readouterr()
    args = ["issue", "list", "--root", str(framework_repo), "--json"]
    assert cli.main(args) == 0
    first = capsys.readouterr().out
    assert cli.main(args) == 0
    second = capsys.readouterr().out
    assert first == second
    assert json.loads(first)["data"]["count"] == 0

    assert cli.main([*args, "--all"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["count"] == 1


def test_missing_issue_has_not_found_exit_and_json_error(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "issue",
                "show",
                "ISS-9999",
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 3
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["error"]["type"] == "not_found"
    assert "studio issue list" in payload["error"]["message"]


def test_invalid_severity_json_error(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo, "--json")
    args[args.index("critical")] = "urgent"
    assert cli.main(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["type"] == "usage"


def test_update_requires_at_least_one_field(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    assert cli.main(["issue", "update", "ISS-0001", "--root", str(framework_repo)]) == 2
    assert "at least one" in capsys.readouterr().err


def test_empty_list_is_success(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["issue", "list", "--root", str(framework_repo)]) == 0
    assert capsys.readouterr().out.strip() == "No matching issues."
