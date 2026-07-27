from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.evidence import EvidenceCreateRequest, EvidenceService


def _evidence(root: Path) -> str:
    return (
        EvidenceService(root)
        .create_evidence(
            EvidenceCreateRequest(
                title="Observed launch",
                claim="The prototype launched successfully.",
                classification="observed",
                source_type="runtime",
                description="Observed from a clean checkout.",
            )
        )
        .details["evidence"]["id"]
    )


def test_human_add_list_show_evaluate_retire(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "criterion",
                "add",
                "--root",
                str(framework_repo),
                "--description",
                "The prototype launches from a clean checkout.",
                "--required",
                "--completion-condition",
                "A clean checkout launches without errors.",
                "--verification-method",
                "Observed runtime launch test.",
                "--yes",
            ]
        )
        == 0
    )
    assert "Milestone criterion created." in capsys.readouterr().out
    assert cli.main(["criterion", "list", "--root", str(framework_repo)]) == 0
    assert "MC-002" in capsys.readouterr().out
    assert cli.main(["criterion", "show", "MC-002", "--root", str(framework_repo)]) == 0
    assert "Completion condition:" in capsys.readouterr().out

    evidence_id = _evidence(framework_repo)
    assert (
        cli.main(
            [
                "criterion",
                "evaluate",
                "MC-002",
                "--root",
                str(framework_repo),
                "--support",
                "verified",
                "--reason",
                "The clean-checkout launch completed without errors.",
                "--evidence",
                evidence_id,
                "--yes",
            ]
        )
        == 0
    )
    assert "Milestone criterion evaluated." in capsys.readouterr().out
    assert (
        cli.main(
            [
                "criterion",
                "retire",
                "MC-002",
                "--root",
                str(framework_repo),
                "--reason",
                "Launchability moved to the next milestone.",
                "--yes",
            ]
        )
        == 0
    )
    assert "Milestone criterion retired." in capsys.readouterr().out


def test_criterion_json_dry_run_and_missing_error(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [
        "criterion",
        "add",
        "--root",
        str(framework_repo),
        "--description",
        "A delivery loop is playable.",
        "--required",
        "--completion-condition",
        "One loop completes without developer assistance.",
        "--dry-run",
        "--json",
    ]
    assert cli.main(arguments) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "criterion.add"
    assert payload["data"]["criterion"]["id"] == "MC-002"
    assert payload["dry_run"] is True

    assert (
        cli.main(
            [
                "criterion",
                "show",
                "MC-999",
                "--root",
                str(framework_repo),
                "--json",
            ]
        )
        == 3
    )
    error = json.loads(capsys.readouterr().out)
    assert error["error"]["type"] == "not_found"


def test_criterion_noninteractive_requires_yes(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NonInteractiveInput:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", NonInteractiveInput())
    exit_code = cli.main(
        [
            "criterion",
            "add",
            "--root",
            str(framework_repo),
            "--description",
            "A criterion.",
            "--optional",
            "--completion-condition",
            "A concrete condition.",
        ]
    )
    assert exit_code == 2
    assert "requires --yes" in capsys.readouterr().err


def test_criterion_json_reads_update_and_evaluate(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "criterion",
                "add",
                "--root",
                str(framework_repo),
                "--description",
                "The prototype launches.",
                "--required",
                "--completion-condition",
                "A clean checkout launches.",
                "--verification-method",
                "Observed runtime launch test.",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    for command in (
        ["criterion", "list"],
        ["criterion", "show", "MC-002"],
    ):
        arguments = [*command, "--root", str(framework_repo), "--json"]
        assert cli.main(arguments) == 0
        first = capsys.readouterr().out
        assert cli.main(arguments) == 0
        second = capsys.readouterr().out
        assert first == second
    assert (
        cli.main(
            [
                "criterion",
                "update",
                "MC-002",
                "--root",
                str(framework_repo),
                "--completion-condition",
                "Two clean checkouts launch.",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["operation"] == "criterion.update"

    evidence_id = _evidence(framework_repo)
    assert (
        cli.main(
            [
                "criterion",
                "evaluate",
                "MC-002",
                "--root",
                str(framework_repo),
                "--support",
                "verified",
                "--reason",
                "Two observed launches succeeded.",
                "--evidence",
                evidence_id,
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "criterion.evaluate"
    assert payload["data"]["criterion"]["support_status"] == "verified"
