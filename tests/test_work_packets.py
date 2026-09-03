"""Bounded autonomous work: the boundary has to actually hold.

Four rules, each tested rather than trusted: an agent cannot widen its own
scope, cannot complete without verification, cannot complete over a failing
check, and cannot pass by touching files it promised not to.

These use a real git repository because the scope check reads git rather than
asking the agent what it changed. Asking would make the check circular — the
thing under examination would be supplying the evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.execution import ExecutionRequest, execute_process
from practical_game_studio.state import StateRepository
from practical_game_studio.work import (
    WorkCreateRequest,
    WorkInputError,
    WorkNotFoundError,
    WorkService,
    allocate_work_id,
    matches_any,
)


def _git(root: Path, *args: str) -> None:
    result = execute_process(
        ExecutionRequest(
            command=("git", *args), working_directory=root, timeout_seconds=60
        )
    )
    assert result.ok, f"git {' '.join(args)} failed: {result.stderr}"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", ".")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    BootstrapService(tmp_path).bootstrap(BootstrapRequest(name="Work Demo"))
    source = tmp_path / "src"
    source.mkdir(exist_ok=True)
    (source / "game.py").write_text("print(1)\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _packet(root: Path, **overrides: object) -> str:
    request = WorkCreateRequest(
        goal=str(overrides.pop("goal", "Add a score counter")),
        reason=str(overrides.pop("reason", "The hypothesis needs a visible score.")),
        allowed_files=overrides.pop("allowed_files", ("src/*.py",)),
        acceptance_criteria=overrides.pop(
            "acceptance_criteria", ("The score increments on delivery.",)
        ),
        verification_commands=overrides.pop(
            "verification_commands", ("git --version",)
        ),
        **overrides,
    )
    return WorkService(root).create(request).details["work_id"]


def _work(root: Path) -> list[dict]:
    return StateRepository(root).load_work()["work"]


# --- contract creation --------------------------------------------------------


def test_work_ids_are_never_reused() -> None:
    assert allocate_work_id([]) == "WORK-0001"
    assert allocate_work_id([{"id": "WORK-0003"}]) == "WORK-0004"


def test_a_packet_records_its_whole_contract(project: Path) -> None:
    work_id = _packet(project, forbidden_files=(".studio/**",), risk_level="medium")

    packet = _work(project)[0]
    assert packet["id"] == work_id
    assert packet["status"] == "ready"
    assert packet["allowed_files"] == ["src/*.py"]
    assert packet["forbidden_files"] == [".studio/**"]
    assert packet["risk_level"] == "medium"
    assert packet["started_revision"] is None


def test_a_packet_without_acceptance_criteria_is_refused(project: Path) -> None:
    """Creating one would be creating a trap: nothing could ever complete it."""

    with pytest.raises(WorkInputError, match="acceptance criterion"):
        _packet(project, acceptance_criteria=())


def test_a_packet_with_an_empty_scope_is_refused(project: Path) -> None:
    with pytest.raises(WorkInputError, match="allowed_files"):
        _packet(project, allowed_files=())


def test_an_unknown_risk_level_is_refused(project: Path) -> None:
    with pytest.raises(WorkInputError, match="unsupported risk level"):
        _packet(project, risk_level="catastrophic")


# --- lifecycle ----------------------------------------------------------------


def test_starting_pins_the_revision_scope_is_measured_from(project: Path) -> None:
    work_id = _packet(project)

    WorkService(project).start(work_id)

    packet = _work(project)[0]
    assert packet["status"] == "in-progress"
    assert packet["started_revision"]


def test_a_packet_cannot_start_twice(project: Path) -> None:
    work_id = _packet(project)
    WorkService(project).start(work_id)

    with pytest.raises(WorkInputError, match="only a ready packet can start"):
        WorkService(project).start(work_id)


def test_a_packet_waits_for_its_dependencies(project: Path) -> None:
    first = _packet(project, goal="Groundwork")
    second = _packet(project, goal="Depends on groundwork", dependencies=(first,))

    ready = {packet["id"] for packet in WorkService(project).ready()}
    assert first in ready
    assert second not in ready

    with pytest.raises(WorkInputError, match="depends on incomplete work"):
        WorkService(project).start(second)


def test_an_unknown_packet_names_the_missing_id(project: Path) -> None:
    with pytest.raises(WorkNotFoundError, match="WORK-9999"):
        WorkService(project).start("WORK-9999")


# --- scope enforcement --------------------------------------------------------


def test_glob_matching_normalises_separators() -> None:
    assert matches_any("src/game.py", ("src/*.py",))
    assert matches_any("src\\game.py", ("src/*.py",))
    assert not matches_any("tests/game.py", ("src/*.py",))


def test_work_inside_the_declared_scope_passes(project: Path) -> None:
    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "src" / "game.py").write_text("score = 0\n", encoding="utf-8")

    outcome = service.verify(work_id)

    assert outcome.passed
    assert outcome.scope.ok
    assert outcome.scope.violations == ()


def test_a_change_outside_the_scope_fails_verification(project: Path) -> None:
    """Green tests do not excuse touching what the packet promised not to."""

    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "src" / "game.py").write_text("score = 0\n", encoding="utf-8")
    (project / "sneaky.md").write_text("unrelated\n", encoding="utf-8")

    outcome = service.verify(work_id)

    assert not outcome.passed
    assert any("sneaky.md" in item for item in outcome.scope.violations)
    assert all(item["passed"] for item in outcome.command_results)


def test_an_explicitly_forbidden_change_is_named_as_such(project: Path) -> None:
    work_id = _packet(project, allowed_files=("**",), forbidden_files=("secrets/*",))
    service = WorkService(project)
    service.start(work_id)
    (project / "secrets").mkdir()
    (project / "secrets" / "key.txt").write_text("shh\n", encoding="utf-8")

    outcome = service.verify(work_id)

    assert not outcome.passed
    assert any("explicitly forbidden" in item for item in outcome.scope.violations)


def test_the_frameworks_own_bookkeeping_is_not_a_scope_violation(
    project: Path,
) -> None:
    """`work start` writes work.json; that must not fail every packet."""

    work_id = _packet(project, forbidden_files=(".studio/**",))
    service = WorkService(project)
    service.start(work_id)
    (project / "src" / "game.py").write_text("score = 0\n", encoding="utf-8")

    outcome = service.verify(work_id)

    assert outcome.passed
    assert not any("work.json" in item for item in outcome.scope.violations)


def test_a_scope_that_could_not_be_determined_never_counts_as_held(
    tmp_path: Path,
) -> None:
    """No git, no way to see what changed, so nothing may be concluded."""

    BootstrapService(tmp_path).bootstrap(BootstrapRequest(name="No VCS"))
    work_id = _packet(tmp_path)
    service = WorkService(tmp_path)
    service.start(work_id)

    outcome = service.verify(work_id)

    assert not outcome.scope.ok
    assert outcome.scope.undetermined
    assert not outcome.passed


# --- completion ---------------------------------------------------------------


def test_a_packet_cannot_be_completed_without_verification(project: Path) -> None:
    """There is no flag for "trust me"."""

    work_id = _packet(project)
    WorkService(project).start(work_id)

    with pytest.raises(WorkInputError, match="never been verified"):
        WorkService(project).complete(work_id)


def test_a_packet_cannot_be_completed_over_a_failing_check(project: Path) -> None:
    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "sneaky.md").write_text("unrelated\n", encoding="utf-8")
    service.record_verification(work_id, service.verify(work_id))

    with pytest.raises(WorkInputError, match="cannot be completed over a failing"):
        service.complete(work_id)


def test_a_failing_verification_marks_the_packet_failed(project: Path) -> None:
    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "sneaky.md").write_text("unrelated\n", encoding="utf-8")

    service.record_verification(work_id, service.verify(work_id))

    packet = _work(project)[0]
    assert packet["status"] == "failed"
    assert packet["status"] != "complete"


def test_a_verified_packet_completes_and_keeps_its_history(project: Path) -> None:
    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "src" / "game.py").write_text("score = 0\n", encoding="utf-8")
    service.record_verification(work_id, service.verify(work_id))

    service.complete(work_id, result="Score counter added.")

    packet = _work(project)[0]
    assert packet["status"] == "complete"
    assert packet["result"] == "Score counter added."
    assert packet["verification_history"]


def test_a_failure_keeps_its_reason_on_the_record(project: Path) -> None:
    work_id = _packet(project)
    WorkService(project).start(work_id)

    WorkService(project).fail(work_id, "The approach does not work.")

    packet = _work(project)[0]
    assert packet["status"] == "failed"
    assert packet["result"] == "The approach does not work."


def test_completion_refuses_unknown_evidence(project: Path) -> None:
    work_id = _packet(project)
    service = WorkService(project)
    service.start(work_id)
    (project / "src" / "game.py").write_text("score = 0\n", encoding="utf-8")
    service.record_verification(work_id, service.verify(work_id))

    with pytest.raises(WorkInputError, match="unknown evidence"):
        service.complete(work_id, evidence=("EVD-9999",))


# --- CLI ----------------------------------------------------------------------


def test_start_prints_the_boundary_the_agent_must_respect(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work_id = _packet(project, forbidden_files=(".studio/schemas/*",))

    cli.main(["work", "start", work_id, "--root", str(project)])
    output = capsys.readouterr().out

    assert "You may change only:" in output
    assert "src/*.py" in output
    assert "You must not change:" in output
    assert "not something this packet can do to itself" in output


def test_verify_exits_non_zero_when_the_boundary_broke(project: Path) -> None:
    work_id = _packet(project)
    WorkService(project).start(work_id)
    (project / "sneaky.md").write_text("unrelated\n", encoding="utf-8")

    assert cli.main(["work", "verify", work_id, "--root", str(project)]) == 1


def test_verify_json_reports_the_scope_separately_from_the_commands(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work_id = _packet(project)
    WorkService(project).start(work_id)
    (project / "sneaky.md").write_text("unrelated\n", encoding="utf-8")

    cli.main(["work", "verify", work_id, "--root", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert not payload["data"]["passed"]
    assert not payload["data"]["scope"]["ok"]
    assert all(item["passed"] for item in payload["data"]["commands"])


def test_a_packet_with_no_verification_commands_is_warned_about(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(
        [
            "work",
            "add",
            "--root",
            str(project),
            "--goal",
            "Unverifiable work",
            "--reason",
            "Someone forgot the checks.",
            "--allow",
            "src/*.py",
            "--criterion",
            "Something is true.",
        ]
    )
    output = capsys.readouterr().out

    assert "can never be completed" in output


def test_show_states_when_a_packet_was_never_verified(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work_id = _packet(project)

    cli.main(["work", "show", work_id, "--root", str(project)])

    assert "never verified" in capsys.readouterr().out
