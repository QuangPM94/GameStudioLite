from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class NonInteractiveInput:
    def isatty(self) -> bool:
        return False


class InteractiveInput:
    def isatty(self) -> bool:
        return True


def test_bootstrap_human_output_and_no_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["bootstrap", "--root", str(tmp_path)])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "project scaffold created" in output.out
    assert "Project state:\nNot initialized" in output.out
    assert "Starter game brief:" in output.out
    assert str(tmp_path / "GAME_BRIEF.md") in output.out
    assert 'studio init --name "Project Name"' in output.out
    assert output.err == ""


def test_bootstrap_open_brief_opens_created_starter_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Path] = []

    monkeypatch.setattr(cli, "_open_path", lambda path: opened.append(path))

    exit_code = cli.main(["bootstrap", "--root", str(tmp_path), "--open-brief"])

    assert exit_code == 0
    assert opened == [tmp_path / "GAME_BRIEF.md"]


def test_bootstrap_json_is_one_stable_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "bootstrap",
            "--root",
            str(tmp_path),
            "--name",
            "JSON Game",
            "--json",
        ]
    )
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0
    assert output.err == ""
    assert payload["success"] is True
    assert payload["operation"] == "project.bootstrap"
    assert payload["data"]["initialized"] is True
    assert payload["data"]["conflict_count"] == 0
    assert payload["changed_files"] == sorted(payload["changed_files"])


def test_bootstrap_dry_run_cli_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "bootstrap",
            "--root",
            str(tmp_path),
            "--name",
            "Preview",
            "--dry-run",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0
    assert "Dry run — no files were written." in output.out
    assert not any(tmp_path.iterdir())


def test_identical_dry_run_json_is_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["bootstrap", "--root", str(tmp_path), "--dry-run", "--json"]

    assert cli.main(arguments) == 0
    first = capsys.readouterr()
    assert cli.main(arguments) == 0
    second = capsys.readouterr()

    assert first.err == second.err == ""
    assert first.out == second.out
    assert not any(tmp_path.iterdir())


def test_bootstrap_conflict_json_has_paths_and_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "AGENTS.md").write_text("conflict\n", encoding="utf-8")

    exit_code = cli.main(["bootstrap", "--root", str(tmp_path), "--json"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 1
    assert output.err == ""
    assert payload["error"]["type"] == "conflict"
    assert payload["error"]["paths"] == ["AGENTS.md"]


def test_noninteractive_force_requires_yes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest())
    (tmp_path / "AGENTS.md").write_text("old\n", encoding="utf-8")
    monkeypatch.setattr(cli.sys, "stdin", NonInteractiveInput())

    denied = cli.main(["bootstrap", "--root", str(tmp_path), "--force"])
    denied_output = capsys.readouterr()
    accepted = cli.main(["bootstrap", "--root", str(tmp_path), "--force", "--yes"])

    assert denied == 2
    assert "--force --yes" in denied_output.err
    assert accepted == 0


def test_force_noop_does_not_prompt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest())
    monkeypatch.setattr(cli.sys, "stdin", InteractiveInput())

    def unexpected_prompt(prompt: str) -> str:
        raise AssertionError(f"no-op force unexpectedly prompted: {prompt}")

    monkeypatch.setattr("builtins.input", unexpected_prompt)

    exit_code = cli.main(["bootstrap", "--root", str(tmp_path), "--force"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "already present" in output.out
    assert output.err == ""


def test_force_json_never_prompts_on_tty(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest())
    (tmp_path / "AGENTS.md").write_text("outdated\n", encoding="utf-8")
    monkeypatch.setattr(cli.sys, "stdin", InteractiveInput())

    def unexpected_prompt(prompt: str) -> str:
        raise AssertionError(f"JSON mode unexpectedly prompted: {prompt}")

    monkeypatch.setattr("builtins.input", unexpected_prompt)

    exit_code = cli.main(["bootstrap", "--root", str(tmp_path), "--force", "--json"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 2
    assert output.err == ""
    assert payload["error"]["stage"] == "confirmation"


def test_validate_lightweight_project_without_pyproject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest(name="Lightweight"))

    exit_code = cli.main(["validate", "--root", str(tmp_path)])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "project scaffold" in output.out
    assert not (tmp_path / "pyproject.toml").exists()


def test_framework_validate_fails_clearly_in_game_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest())

    exit_code = cli.main(["framework", "validate", "--root", str(tmp_path)])
    output = capsys.readouterr()

    assert exit_code == 1
    assert (
        "bootstrapped PGS game project, not a GameStudioLite framework "
        "source repository" in output.err
    )


def test_framework_validate_json_passes_in_source_repository(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        ["framework", "validate", "--root", str(REPOSITORY_ROOT), "--json"]
    )
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0
    assert output.err == ""
    assert payload["operation"] == "framework.validate"
    assert payload["validation"]["framework"] == "passed"


def test_init_without_bootstrap_recommends_bootstrap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["init", "--root", str(tmp_path), "--name", "Not Attached"])
    output = capsys.readouterr()

    assert exit_code == 2
    assert "No Practical Game Studio project found" not in output.err
    assert "studio bootstrap" in output.err


def test_help_exposes_first_time_and_framework_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    output = capsys.readouterr()

    assert exc_info.value.code == 0
    assert "bootstrap" in output.out
    assert "attach Practical Game Studio" in output.out
    assert "framework" in output.out
