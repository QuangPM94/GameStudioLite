"""Behaviour of the process runner, adapters, doctor, and verification levels.

The line these tests defend is the one the whole framework rests on: a fact about
a process must never quietly become a claim about a game. Concretely that means
a killed process is `unknown` and not `failed`, a missing test framework is
`unknown` and not `failed`, a capability nobody probed is not available, and
`gameplay` never passes on its own.

A stub engine stands in for Godot so the loop can be exercised on a machine with
no engine installed — which is also the machine most contributors have.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.adapters import (
    BaseEngineAdapter,
    BuildOptions,
    CapabilityReport,
    DetectionResult,
    ProbeResult,
    RunOptions,
    UnsupportedOperationError,
    detect_adapters,
    get_adapter,
    register_adapter,
    resolve_adapter,
    unregister_adapter,
)
from practical_game_studio.adapters.godot import commands as godot_commands
from practical_game_studio.adapters.godot.detector import (
    detect_godot_project,
    major_version,
)
from practical_game_studio.adapters.registry import AdapterNotFoundError
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.execution import (
    ExecutionRequest,
    ProcessError,
    calculate_duration,
    execute_process,
    redact_command,
    sanitize_environment,
)
from practical_game_studio.state import StateRepository
from practical_game_studio.verification import (
    LEVELS,
    verify,
    verify_gameplay,
    verify_runtime,
    verify_smoke,
    verify_static,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    BootstrapService(tmp_path).bootstrap(
        BootstrapRequest(name="Execution Core", engine="Godot")
    )
    return tmp_path


def _python(*code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", "\n".join(code))


# --- process runner ----------------------------------------------------------


def test_a_successful_process_reports_what_it_did() -> None:
    result = execute_process(ExecutionRequest(command=_python("print('hello')")))

    assert result.outcome == "completed"
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.ok
    assert result.run_status == "passed"


def test_a_failing_process_is_a_result_not_an_error() -> None:
    """A non-zero exit is data. Only the framework failing is an error."""

    result = execute_process(ExecutionRequest(command=_python("raise SystemExit(3)")))

    assert result.outcome == "completed"
    assert result.exit_code == 3
    assert result.run_status == "failed"
    assert not result.ok


def test_a_killed_process_is_unknown_rather_than_failed() -> None:
    """The framework stopped it, so nothing was learned about the program."""

    result = execute_process(
        ExecutionRequest(
            command=_python("import time", "time.sleep(30)"), timeout_seconds=1
        )
    )

    assert result.outcome == "timeout"
    assert result.run_status == "unknown"
    assert result.run_status != "failed"
    assert any("would have succeeded is unknown" in item for item in result.limitations)


def test_a_program_that_cannot_start_is_unknown_not_failed() -> None:
    result = execute_process(
        ExecutionRequest(command=("definitely-not-a-real-binary-xyz",))
    )

    assert result.outcome == "error"
    assert result.run_status == "unknown"
    assert result.error


def test_an_empty_command_is_refused() -> None:
    with pytest.raises(ProcessError, match="empty command"):
        execute_process(ExecutionRequest(command=()))


def test_undecodable_output_does_not_lose_the_log() -> None:
    """One bad byte from an engine must not cost the framework the whole log."""

    result = execute_process(
        ExecutionRequest(
            command=_python(
                "import sys",
                "sys.stdout.buffer.write(b'ok \\xff\\xfe done')",
            )
        )
    )

    assert result.outcome == "completed"
    assert "ok" in result.stdout
    assert "done" in result.stdout


def test_a_process_cannot_block_waiting_for_input() -> None:
    """An agent must not be able to leave a program waiting on stdin forever."""

    result = execute_process(
        ExecutionRequest(command=_python("import sys", "sys.stdin.read()"))
    )

    assert result.outcome == "completed"


def test_duration_is_never_negative() -> None:
    assert calculate_duration(10.0, 9.0) == 0
    assert calculate_duration(1.0, 1.5) == 500


# --- environment safety ------------------------------------------------------


def test_credential_variables_are_not_handed_to_child_processes() -> None:
    """The framework runs engines and build tools on a developer's machine."""

    environment = sanitize_environment(
        base={"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "x", "GITHUB_TOKEN": "y"}
    )

    assert "PATH" in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "GITHUB_TOKEN" not in environment


def test_a_caller_can_opt_a_variable_back_in_by_name() -> None:
    environment = sanitize_environment(
        {"GITHUB_TOKEN": "needed"}, base={"GITHUB_TOKEN": "blocked"}
    )

    assert environment["GITHUB_TOKEN"] == "needed"


def test_an_override_of_none_removes_a_variable() -> None:
    assert "GONE" not in sanitize_environment({"GONE": None}, base={"GONE": "here"})


def test_secret_looking_arguments_are_redacted_before_being_stored() -> None:
    """`runs.json` is committed to the project's repository."""

    redacted = redact_command(
        ("build", "--api-token=abc123", "--user=alice", "PASSWORD=hunter2")
    )

    assert "abc123" not in " ".join(redacted)
    assert "hunter2" not in " ".join(redacted)
    assert "--user=alice" in redacted


# --- adapter contract --------------------------------------------------------


class StubAdapter(BaseEngineAdapter):
    """An adapter that detects everything and can do nothing."""

    id = "stub"
    display_name = "Stub"
    engine = "Stub Engine"

    def detect(self, root: Path) -> DetectionResult:
        return DetectionResult(detected=True, confidence=10, detail="stub")

    def probe(self, root: Path) -> ProbeResult:
        return ProbeResult(
            adapter_id=self.id,
            engine=self.engine,
            engine_version=None,
            executable=None,
            capabilities=(
                CapabilityReport("RUN", "unavailable", "the stub cannot run"),
            ),
        )


@pytest.fixture
def stub_adapter() -> StubAdapter:
    adapter = StubAdapter()
    register_adapter(adapter, replace=True)
    yield adapter
    unregister_adapter(adapter.id)


def test_an_unprobed_capability_is_not_supported(stub_adapter: StubAdapter) -> None:
    """Silence is never a yes."""

    probe = stub_adapter.probe(Path("."))

    assert not probe.supports("SCREENSHOT")
    assert not probe.supports("RUN")
    assert probe.available_capabilities == ()


def test_requiring_a_missing_capability_says_what_is_available(
    stub_adapter: StubAdapter,
) -> None:
    probe = stub_adapter.probe(Path("."))

    with pytest.raises(UnsupportedOperationError) as raised:
        probe.require("BUILD")

    assert "stub cannot perform BUILD" in str(raised.value)
    assert "no capabilities on this machine" in str(raised.value)


def test_an_unsupported_operation_refuses_instead_of_crashing(
    project: Path, stub_adapter: StubAdapter
) -> None:
    """An agent needs a message it can act on, not an AttributeError."""

    result = stub_adapter.build(project, BuildOptions())

    assert result.status == "unsupported"
    assert result.run_id is None
    assert "cannot perform BUILD" in result.detail
    assert result.limitations


def test_an_unknown_adapter_id_names_what_is_registered() -> None:
    with pytest.raises(AdapterNotFoundError, match="godot-cli"):
        get_adapter("no-such-adapter")


def test_a_project_no_adapter_recognises_resolves_to_none(tmp_path: Path) -> None:
    """The framework must stay usable for a planning-only project."""

    assert resolve_adapter(tmp_path) is None


# --- Godot detection ---------------------------------------------------------


def _write_godot_project(root: Path, *, presets: str | None = None) -> None:
    (root / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="Demo"\n', encoding="utf-8"
    )
    if presets is not None:
        (root / "export_presets.cfg").write_text(presets, encoding="utf-8")


def test_a_godot_project_is_detected_by_its_manifest(tmp_path: Path) -> None:
    _write_godot_project(tmp_path)

    match = next(m for m in detect_adapters(tmp_path) if m.adapter.id == "godot-cli")

    assert match.detection.detected
    assert "project.godot" in match.detection.indicators


def test_a_nested_engine_project_is_found_but_ranked_lower(tmp_path: Path) -> None:
    """`game/project.godot` is a normal layout and must not be unsupported."""

    nested = tmp_path / "game"
    nested.mkdir()
    _write_godot_project(nested)

    detection = get_adapter("godot-cli").detect(tmp_path)

    assert detection.detected
    assert detection.confidence < 90


def test_export_preset_names_are_read_from_the_config(tmp_path: Path) -> None:
    _write_godot_project(
        tmp_path, presets='[preset.0]\nname="Windows Desktop"\n[preset.1]\nname="Web"\n'
    )

    project = detect_godot_project(tmp_path)

    assert project.export_preset_names == ("Windows Desktop", "Web")


def test_an_unparsable_preset_file_does_not_crash_detection(tmp_path: Path) -> None:
    _write_godot_project(tmp_path, presets="this is not a preset file")

    project = detect_godot_project(tmp_path)

    assert project.export_presets is not None
    assert project.export_preset_names == ()


def test_a_project_without_the_engine_installed_is_still_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "This is a Godot project and I cannot run it" must be sayable."""

    _write_godot_project(tmp_path)
    monkeypatch.setattr(
        "practical_game_studio.adapters.godot.detector.which", lambda name: None
    )
    monkeypatch.delenv("GODOT", raising=False)

    adapter = get_adapter("godot-cli")
    probe = adapter.probe(tmp_path)

    assert adapter.detect(tmp_path).detected
    assert not probe.supports("RUN")
    assert probe.capability("RUN").readiness == "unavailable"


def test_major_version_reports_none_when_it_cannot_be_read() -> None:
    assert major_version("4.2.1.stable.official") == 4
    assert major_version("custom build") is None
    assert major_version(None) is None


# --- Godot command lines -----------------------------------------------------


def test_a_headless_run_passes_the_project_path_and_headless_flag(
    tmp_path: Path,
) -> None:
    command = godot_commands.run_command(
        "godot", tmp_path, RunOptions(headless=True, scene="res://Main.tscn")
    )

    assert command[0] == "godot"
    assert "--headless" in command
    assert "--path" in command
    assert "res://Main.tscn" in command


def test_a_release_export_uses_the_release_flag(tmp_path: Path) -> None:
    command, output = godot_commands.export_command(
        "godot", tmp_path, "Windows Desktop", BuildOptions(profile="release")
    )

    assert "--export-release" in command
    assert "--export-debug" not in command
    assert "release" in output


# --- verification levels -----------------------------------------------------


def test_static_verification_says_what_it_did_not_check(project: Path) -> None:
    check = verify_static(project)

    assert check.status == "passed"
    assert any("not built or run" in item for item in check.limitations)


def test_verification_without_an_adapter_is_unknown(tmp_path: Path) -> None:
    BootstrapService(tmp_path).bootstrap(BootstrapRequest(name="No Engine"))

    check = verify_smoke(tmp_path)

    assert check.status == "unknown"
    assert check.status != "failed"


def test_a_project_without_tests_is_unknown_not_failed(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project with no tests has not been shown to be broken."""

    _write_godot_project(project)
    monkeypatch.setattr(
        "practical_game_studio.adapters.godot.detector.which", lambda name: None
    )
    monkeypatch.delenv("GODOT", raising=False)

    check = verify_runtime(project)

    assert check.status == "unknown"
    assert check.status != "failed"


def test_gameplay_can_never_pass_on_its_own(project: Path) -> None:
    """No process result observes a player."""

    check = verify_gameplay(project)

    assert check.status == "unknown"
    assert check.status != "passed"
    assert any("cannot be established" in item for item in check.limitations)


def test_every_level_is_reachable_and_reports_a_status(project: Path) -> None:
    for level in LEVELS:
        report = verify(project, level)
        assert report.level == level
        assert report.status in {"passed", "failed", "unknown", "skipped"}


def test_a_report_status_is_the_worst_of_its_checks(project: Path) -> None:
    report = verify(project, "gameplay")

    assert report.status == "unknown"
    assert any(check.status == "passed" for check in report.checks)


def test_no_verification_creates_evidence(project: Path) -> None:
    """Verification proposes. It never asserts."""

    verify(project, "gameplay")

    assert StateRepository(project).load_evidence()["evidence"] == []


# --- CLI ---------------------------------------------------------------------


def test_doctor_reports_unknown_when_no_adapter_recognises_the_project(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["doctor", "--root", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data"]["resolved_adapter"] is None
    readiness = {
        row["capability"]: row["readiness"] for row in payload["data"]["capabilities"]
    }
    assert readiness["RUN"] == "unknown"
    assert readiness["RUN"] != "unavailable"


def test_doctor_never_claims_a_capability_it_did_not_probe(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["doctor", "--root", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert all(row["readiness"] != "ready" for row in payload["data"]["capabilities"])


def test_doctor_changes_nothing(project: Path) -> None:
    """A doctor that fixed things would make its own report untrustworthy."""

    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

    cli.main(["doctor", "--root", str(project)])

    assert {
        path: path.read_bytes() for path in project.rglob("*") if path.is_file()
    } == before


def test_run_without_an_adapter_exits_unknown_not_failed(project: Path) -> None:
    """`could not attempt` and `attempted and failed` must not look the same."""

    assert cli.main(["run", "--root", str(project)]) == 4


def test_verify_levels_lists_what_each_level_establishes(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["verify", "--levels", "--root", str(project)])
    output = capsys.readouterr().out

    assert exit_code == 0
    for level in LEVELS:
        assert level in output
    assert "never automatic" in output


def test_verify_output_always_states_what_was_not_established(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Silence about limitations reads as "there are none"."""

    cli.main(["verify", "--root", str(project), "--level", "static"])
    output = capsys.readouterr().out

    assert "What this did NOT establish:" in output


def test_verify_json_carries_proposals_separately_from_evidence(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["verify", "--root", str(project), "--level", "static", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert "evidence_proposals" in payload["data"]
    assert StateRepository(project).load_evidence()["evidence"] == []
