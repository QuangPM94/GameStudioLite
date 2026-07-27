from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli


def _add_args(root: Path, *extra: str) -> list[str]:
    return [
        "decision",
        "add",
        "--root",
        str(root),
        "--question",
        "How should the player locate the delivery room?",
        "--context",
        "The corridor lacks sufficient guidance.",
        "--urgency",
        "high",
        "--owner",
        "user",
        "--option",
        "OPT-A|Explicit waypoint|Show a marker over the target door.",
        "--option",
        "OPT-B|Environmental guidance|Use signs and stronger numbering.",
        "--recommended-option",
        "OPT-B",
        "--recommendation-reason",
        "It preserves immersion.",
        "--trade-off",
        "Less explicit than a waypoint.",
        "--status",
        "ready",
        "--yes",
        *extra,
    ]


def test_add_human_and_json_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    output = capsys.readouterr()
    assert "Decision created." in output.out
    assert "ID: DEC-0001" in output.out
    assert "OPT-B — Environmental guidance" in output.out
    assert "Recommended next workflow:\n/next-step" in output.out

    assert cli.main(_add_args(framework_repo, "--json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "decision.add"
    assert payload["data"]["decision"]["id"] == "DEC-0002"


def test_dry_run_and_guided_confirmation(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _add_args(framework_repo, "--dry-run")
    args.remove("--yes")
    assert cli.main(args) == 0
    assert "Dry run — no files were written." in capsys.readouterr().out

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
    assert "Decision created." in capsys.readouterr().out


def test_missing_fields_and_bad_option_fail_cleanly(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["decision", "add", "--root", str(framework_repo)]) == 2
    output = capsys.readouterr()
    assert "--question" in output.err
    assert "Traceback" not in output.err

    args = _add_args(framework_repo)
    index = args.index("OPT-A|Explicit waypoint|Show a marker over the target door.")
    args[index] = "not-enough-fields"
    assert cli.main(args) == 2
    assert "option specs use" in capsys.readouterr().err


def test_list_show_update_and_resolve_human(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_add_args(framework_repo)) == 0
    capsys.readouterr()
    assert cli.main(["decision", "list", "--root", str(framework_repo)]) == 0
    assert "Pending decisions: 1" in capsys.readouterr().out
    assert (
        cli.main(["decision", "show", "DEC-0001", "--root", str(framework_repo)]) == 0
    )
    shown = capsys.readouterr().out
    assert "Options:" in shown
    assert "Evidence support: None recorded" in shown

    assert (
        cli.main(
            [
                "decision",
                "update",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--urgency",
                "blocking",
            ]
        )
        == 0
    )
    assert "Decision updated." in capsys.readouterr().out

    assert (
        cli.main(
            [
                "decision",
                "resolve",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--option",
                "OPT-B",
                "--reason",
                "It preserves immersion.",
                "--follow-up",
                "Run another playtest.",
                "--yes",
            ]
        )
        == 0
    )
    resolved = capsys.readouterr().out
    assert "Decision resolved." in resolved
    assert "Recommendation:\nFollowed" in resolved
    assert "Recommended next workflow:\n/iterate" in resolved


def test_update_and_resolve_dry_runs(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    assert (
        cli.main(
            [
                "decision",
                "update",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--urgency",
                "blocking",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "Dry run — no files were written." in capsys.readouterr().out
    assert (
        cli.main(
            [
                "decision",
                "resolve",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--custom-decision",
                "Combine both options.",
                "--reason",
                "Best fit.",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "Proposed decision resolution." in capsys.readouterr().out


def test_json_list_show_update_resolve_are_stable(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    list_args = ["decision", "list", "--root", str(framework_repo), "--json"]
    assert cli.main(list_args) == 0
    first = capsys.readouterr().out
    assert cli.main(list_args) == 0
    assert capsys.readouterr().out == first
    assert json.loads(first)["data"]["count"] == 1

    assert (
        cli.main(
            [
                "decision",
                "show",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["operation"] == "decision.show"

    assert (
        cli.main(
            [
                "decision",
                "update",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--urgency",
                "blocking",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["operation"] == "decision.update"

    assert (
        cli.main(
            [
                "decision",
                "resolve",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--option",
                "OPT-A",
                "--reason",
                "Override.",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "decision.resolve"
    assert payload["data"]["decision"]["recommendation_followed"] is False


def test_missing_decision_invalid_id_and_empty_list(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["decision", "list", "--root", str(framework_repo)]) == 0
    assert capsys.readouterr().out.strip() == "No matching decisions."
    assert (
        cli.main(["decision", "show", "DEC-9999", "--root", str(framework_repo)]) == 3
    )
    assert "studio decision list" in capsys.readouterr().err
    assert cli.main(["decision", "show", "bad-id", "--root", str(framework_repo)]) == 2
    assert "invalid decision ID" in capsys.readouterr().err


def test_invalid_resolution_and_empty_update(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_add_args(framework_repo))
    capsys.readouterr()
    assert (
        cli.main(["decision", "update", "DEC-0001", "--root", str(framework_repo)]) == 2
    )
    assert "at least one" in capsys.readouterr().err
    assert (
        cli.main(
            [
                "decision",
                "resolve",
                "DEC-0001",
                "--root",
                str(framework_repo),
                "--option",
                "OPT-Z",
                "--reason",
                "Invalid.",
                "--yes",
            ]
        )
        == 2
    )
    assert "OPT-Z" in capsys.readouterr().err
