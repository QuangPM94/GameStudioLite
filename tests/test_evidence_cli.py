from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.issues import IssueCreateRequest, IssueService
from practical_game_studio.state import StateRepository


def _add_args(root: Path, *extra: str) -> list[str]:
    return [
        "evidence",
        "add",
        "--root",
        str(root),
        "--title",
        "Player stopped in corridor",
        "--claim",
        "The player could not identify the target apartment.",
        "--classification",
        "user-reported",
        "--source-type",
        "human-playtest",
        "--description",
        "Tester remained in the corridor for forty seconds.",
        "--yes",
        *extra,
    ]


def test_evidence_add_human_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    output = capsys.readouterr()
    assert "Evidence created." in output.out
    assert "ID: EVD-0001" in output.out
    assert "Classification: User Reported" in output.out
    assert "Recommended next workflow:\n/issue-map" in output.out
    assert output.err == ""


def test_evidence_add_json_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo, "--json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["operation"] == "evidence.add"
    assert payload["data"]["evidence"]["id"] == "EVD-0001"


def test_evidence_add_dry_run_needs_no_confirmation(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo, "--dry-run")
    args.remove("--yes")
    assert cli.main(args) == 0
    assert "Dry run — no files were written." in capsys.readouterr().out


def test_guided_noninteractive_add_requires_yes(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo)
    args.remove("--yes")
    assert cli.main(args) == 2
    assert "requires --yes" in capsys.readouterr().err


def test_fast_mode_skips_confirmation(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_path = framework_repo / ".studio" / "state" / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["review_mode"] = "fast"
    project_path.write_text(json.dumps(project), encoding="utf-8")
    args = _add_args(framework_repo)
    args.remove("--yes")
    assert cli.main(args) == 0
    assert "Evidence created." in capsys.readouterr().out


def test_missing_required_fields_fail_without_traceback(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["evidence", "add", "--root", str(framework_repo)]) == 2
    output = capsys.readouterr()
    assert "--title" in output.err
    assert "--claim" in output.err
    assert "Traceback" not in output.err


def test_required_source_missing_fails(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo)
    args[args.index("human-playtest")] = "screenshot"
    assert cli.main(args) == 2
    assert "source is required" in capsys.readouterr().err


def test_list_show_and_update_human_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    capsys.readouterr()
    assert cli.main(["evidence", "list", "--root", str(framework_repo)]) == 0
    listed = capsys.readouterr()
    assert "Active evidence: 1" in listed.out
    assert "EVD-0001" in listed.out

    assert (
        cli.main(["evidence", "show", "EVD-0001", "--root", str(framework_repo)]) == 0
    )
    shown = capsys.readouterr()
    assert "Claim:" in shown.out
    assert "Captured:" in shown.out

    assert (
        cli.main(
            [
                "evidence",
                "update",
                "EVD-0001",
                "--root",
                str(framework_repo),
                "--status",
                "retracted",
            ]
        )
        == 0
    )
    updated = capsys.readouterr()
    assert "Evidence updated." in updated.out
    assert "Status: Retracted" in updated.out


def test_list_json_is_stable_and_all_includes_retracted(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    cli.main(
        [
            "evidence",
            "update",
            "EVD-0001",
            "--root",
            str(framework_repo),
            "--status",
            "retracted",
        ]
    )
    capsys.readouterr()
    args = ["evidence", "list", "--root", str(framework_repo), "--json"]
    assert cli.main(args) == 0
    first = capsys.readouterr().out
    assert cli.main(args) == 0
    second = capsys.readouterr().out
    assert first == second
    assert json.loads(first)["data"]["count"] == 0

    assert cli.main([*args, "--all"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["count"] == 1


def test_link_and_unlink_issue_through_cli(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    IssueService(framework_repo).create_issue(
        IssueCreateRequest(
            title="Unclear room",
            severity="critical",
            player_impact="Player cannot progress.",
        )
    )
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    assert (
        cli.main(
            [
                "evidence",
                "update",
                "EVD-0001",
                "--root",
                str(framework_repo),
                "--add-issue",
                "ISS-0001",
            ]
        )
        == 0
    )
    state = StateRepository(framework_repo).load_all()
    assert state["issues"]["issues"][0]["evidence_references"] == ["EVD-0001"]

    capsys.readouterr()
    assert (
        cli.main(
            [
                "evidence",
                "update",
                "EVD-0001",
                "--root",
                str(framework_repo),
                "--remove-issue",
                "ISS-0001",
            ]
        )
        == 0
    )
    state = StateRepository(framework_repo).load_all()
    assert state["issues"]["issues"][0]["evidence_references"] == []


def test_missing_evidence_json_not_found(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "evidence",
                "show",
                "EVD-9999",
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 3
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["type"] == "not_found"
    assert "studio evidence list" in payload["error"]["message"]


def test_invalid_evidence_id_is_usage_error(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["evidence", "show", "bad-id", "--root", str(framework_repo)]) == 2
    output = capsys.readouterr()
    assert "invalid evidence ID" in output.err
    assert "Traceback" not in output.err


def test_invalid_classification_json_error(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo, "--json")
    args[args.index("user-reported")] = "certain"
    assert cli.main(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["type"] == "usage"


def test_update_requires_a_field(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    assert (
        cli.main(["evidence", "update", "EVD-0001", "--root", str(framework_repo)]) == 2
    )
    assert "at least one" in capsys.readouterr().err


def test_empty_list_succeeds(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["evidence", "list", "--root", str(framework_repo)]) == 0
    assert capsys.readouterr().out.strip() == "No matching evidence."
