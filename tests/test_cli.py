from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli


class NonInteractiveInput:
    def isatty(self) -> bool:
        return False


def test_cli_init_success_output(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "init",
            "--root",
            str(framework_repo),
            "--name",
            "Midnight Carrier",
            "--engine",
            "Unity",
            "--platform",
            "Windows",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Practical Game Studio initialized." in output.out
    assert "Project: Midnight Carrier" in output.out
    assert "Recommended next workflow:\n/start" in output.out
    assert output.err == ""


def test_cli_validation_failure_exit_code(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = framework_repo / ".studio" / "state" / "project.json"
    project = json.loads(path.read_text(encoding="utf-8"))
    project["review_mode"] = "invalid"
    path.write_text(json.dumps(project), encoding="utf-8")

    exit_code = cli.main(["validate", "--root", str(framework_repo)])
    output = capsys.readouterr()

    assert exit_code == 1
    assert "Validation failed" in output.err


def test_cli_missing_name_noninteractive_fails_clearly(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", NonInteractiveInput())

    exit_code = cli.main(["init", "--root", str(framework_repo)])
    output = capsys.readouterr()

    assert exit_code == 2
    assert "missing required values: --name" in output.err
    assert "Traceback" not in output.err


def test_cli_invalid_review_mode_is_rejected(framework_repo: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "init",
                "--root",
                str(framework_repo),
                "--name",
                "Invalid",
                "--review-mode",
                "reckless",
            ]
        )

    assert exc_info.value.code == 2


def test_cli_dry_run_labels_no_write(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_path = framework_repo / ".studio" / "state" / "project.json"
    before = project_path.read_bytes()

    exit_code = cli.main(
        [
            "init",
            "--root",
            str(framework_repo),
            "--name",
            "Preview",
            "--dry-run",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Dry run — no files were written." in output.out
    assert "Proposed changes:" in output.out
    assert project_path.read_bytes() == before


def test_cli_already_initialized_is_successful_noop(
    framework_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["init", "--root", str(framework_repo), "--name", "Existing"]) == 0
    capsys.readouterr()

    exit_code = cli.main(["init", "--root", str(framework_repo), "--name", "Ignored"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "already initialized" in output.out
    assert "Run `studio status`" in output.out


def test_cli_noninteractive_force_requires_yes(
    framework_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cli.main(["init", "--root", str(framework_repo), "--name", "Existing"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(cli.sys, "stdin", NonInteractiveInput())

    denied = cli.main(
        [
            "init",
            "--root",
            str(framework_repo),
            "--platform",
            "Linux",
            "--force",
        ]
    )
    denied_output = capsys.readouterr()
    accepted = cli.main(
        [
            "init",
            "--root",
            str(framework_repo),
            "--platform",
            "Linux",
            "--force",
            "--yes",
        ]
    )

    assert denied == 2
    assert "requires --yes" in denied_output.err
    assert accepted == 0
