"""Behaviour of run and artifact records, and their CLI surface.

The framework's whole claim is that it can tell what actually happened from what
someone hopes happened. These tests hold that line: a run is a fact about a
process, an artifact is a fact about a file, neither becomes evidence on its own,
and a check that could not be performed reports `unknown`/`unverified` rather
than guessing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.artifacts import (
    ArtifactCreateRequest,
    ArtifactInputError,
    ArtifactNotFoundError,
    ArtifactService,
    allocate_artifact_id,
    hash_artifact,
)
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidenceInputError,
    EvidencePatch,
    EvidenceService,
)
from practical_game_studio.runs import (
    RunCreateRequest,
    RunInputError,
    RunNotFoundError,
    RunResult,
    RunService,
    allocate_run_id,
    summarize_output,
)
from practical_game_studio.state import StateRepository


@pytest.fixture
def project(tmp_path: Path) -> Path:
    BootstrapService(tmp_path).bootstrap(
        BootstrapRequest(name="Execution Game", engine="Godot")
    )
    return tmp_path


def _runs(root: Path) -> list[dict]:
    return StateRepository(root).load_runs()["runs"]


def _artifacts(root: Path) -> list[dict]:
    return StateRepository(root).load_artifacts()["artifacts"]


def _start_run(root: Path, **overrides: object) -> str:
    request = RunCreateRequest(
        action=str(overrides.pop("action", "build")),
        command=overrides.pop("command", ("godot", "--headless")),
        adapter=str(overrides.pop("adapter", "godot-cli")),
        **overrides,
    )
    return RunService(root).create(request).details["run_id"]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- id allocation -----------------------------------------------------------


def test_run_ids_continue_past_the_highest_ever_allocated() -> None:
    assert allocate_run_id([]) == "RUN-0001"
    assert allocate_run_id([{"id": "RUN-0001"}, {"id": "RUN-0007"}]) == "RUN-0008"


def test_artifact_ids_are_not_reused_after_a_gap() -> None:
    assert allocate_artifact_id([]) == "ART-0001"
    assert allocate_artifact_id([{"id": "ART-0004"}]) == "ART-0005"


# --- run lifecycle -----------------------------------------------------------


def test_a_run_is_recorded_before_its_result_exists(project: Path) -> None:
    """A process that never returns must still leave a trace of the attempt."""

    run_id = _start_run(project, action="test", command=["pytest"])

    record = _runs(project)[0]
    assert record["id"] == run_id
    assert record["status"] == "running"
    assert record["started_at"] is not None
    assert record["completed_at"] is None
    assert record["exit_code"] is None


def test_completing_a_run_records_how_it_ended(project: Path) -> None:
    run_id = _start_run(project)

    RunService(project).complete(
        run_id, RunResult(status="passed", exit_code=0, duration_ms=1234)
    )

    record = _runs(project)[0]
    assert record["status"] == "passed"
    assert record["exit_code"] == 0
    assert record["duration_ms"] == 1234
    assert record["completed_at"] is not None


def test_unknown_is_recorded_as_its_own_result_not_as_failure(project: Path) -> None:
    """A result nobody could determine must stay distinguishable from a failure."""

    run_id = _start_run(project, action="verify")

    RunService(project).complete(
        run_id,
        RunResult(
            status="unknown",
            limitations=("No test framework was detected; nothing was executed.",),
        ),
    )

    record = _runs(project)[0]
    assert record["status"] == "unknown"
    assert record["status"] != "failed"
    assert record["limitations"] == [
        "No test framework was detected; nothing was executed."
    ]


def test_a_run_cannot_be_completed_twice(project: Path) -> None:
    service = RunService(project)
    run_id = _start_run(project)
    service.complete(run_id, RunResult(status="passed", exit_code=0))

    with pytest.raises(RunInputError, match="already completed"):
        service.complete(run_id, RunResult(status="failed", exit_code=1))


def test_completing_an_unknown_run_names_the_missing_id(project: Path) -> None:
    with pytest.raises(RunNotFoundError, match="RUN-9999"):
        RunService(project).complete("RUN-9999", RunResult(status="passed"))


def test_an_unsupported_action_is_refused(project: Path) -> None:
    with pytest.raises(RunInputError, match="unsupported action"):
        RunService(project).create(RunCreateRequest(action="deploy"))


def test_duration_is_derived_from_timestamps_when_not_supplied(project: Path) -> None:
    run_id = _start_run(project)

    RunService(project).complete(
        run_id,
        RunResult(status="passed", exit_code=0, completed_at="2030-01-01T00:00:00Z"),
    )

    assert _runs(project)[0]["duration_ms"] > 0


def test_a_dry_run_records_nothing(project: Path) -> None:
    result = RunService(project).create(RunCreateRequest(action="build"), dry_run=True)

    assert result.dry_run
    assert _runs(project) == []


# --- output summarisation ----------------------------------------------------


def test_short_output_is_stored_verbatim() -> None:
    assert summarize_output("all good") == "all good"
    assert summarize_output(None) is None


def test_truncated_output_says_that_it_was_truncated() -> None:
    """A fragment that looks whole would let a reader draw a false conclusion."""

    summary = summarize_output("x" * 5000, limit=100)

    assert summary.startswith("x" * 100)
    assert "4900 characters truncated" in summary


# --- artifacts ---------------------------------------------------------------


def test_registering_a_file_records_its_hash_and_size(project: Path) -> None:
    log = _write(project / "build" / "out.log", "compiled 12 scenes\n")

    result = ArtifactService(project).add(
        ArtifactCreateRequest(type="log", path=str(log))
    )

    artifact = result.details["artifact"]
    assert artifact["status"] == "present"
    assert artifact["sha256"] == hash_artifact(log)
    assert artifact["size_bytes"] == log.stat().st_size
    assert artifact["path"] == "build/out.log"


def test_a_promised_file_that_is_absent_is_recorded_as_missing(project: Path) -> None:
    """A build that did not produce what it promised is worth recording."""

    result = ArtifactService(project).add(
        ArtifactCreateRequest(type="build", path="dist/game.exe")
    )

    artifact = result.details["artifact"]
    assert artifact["status"] == "missing"
    assert artifact["sha256"] is None
    assert artifact["size_bytes"] is None


def test_an_artifact_links_back_to_the_run_that_produced_it(project: Path) -> None:
    run_id = _start_run(project)
    log = _write(project / "build" / "out.log", "ok\n")

    artifact_id = (
        ArtifactService(project)
        .add(ArtifactCreateRequest(type="log", path=str(log), source_run=run_id))
        .details["artifact_id"]
    )

    assert _artifacts(project)[0]["source_run"] == run_id
    assert _runs(project)[0]["artifacts"] == [artifact_id]


def test_an_artifact_cannot_cite_a_run_that_does_not_exist(project: Path) -> None:
    with pytest.raises(ArtifactInputError, match="unknown source run"):
        ArtifactService(project).add(
            ArtifactCreateRequest(type="log", path="x.log", source_run="RUN-4242")
        )


def test_an_unsupported_artifact_type_is_refused(project: Path) -> None:
    with pytest.raises(ArtifactInputError, match="unsupported artifact type"):
        ArtifactService(project).add(
            ArtifactCreateRequest(type="hologram", path="x.log")
        )


# --- verification ------------------------------------------------------------


def test_verification_reports_present_for_an_untouched_file(project: Path) -> None:
    log = _write(project / "out.log", "unchanged\n")
    ArtifactService(project).add(ArtifactCreateRequest(type="log", path=str(log)))

    (verification,) = ArtifactService(project).verify()

    assert verification.ok
    assert verification.status == "present"


def test_verification_tells_modified_apart_from_missing(project: Path) -> None:
    """A silently edited screenshot is worse than a missing one."""

    edited = _write(project / "shot.png", "original")
    gone = _write(project / "gone.log", "temporary")
    service = ArtifactService(project)
    service.add(ArtifactCreateRequest(type="screenshot", path=str(edited)))
    service.add(ArtifactCreateRequest(type="log", path=str(gone)))

    edited.write_text("tampered", encoding="utf-8")
    gone.unlink()

    by_id = {item.artifact_id: item for item in service.verify()}

    assert by_id["ART-0001"].status == "modified"
    assert by_id["ART-0002"].status == "missing"
    assert not any(item.ok for item in by_id.values())


def test_verification_is_read_only_unless_asked_to_record(project: Path) -> None:
    """A check is an observation at a moment, not a new fact about the record."""

    log = _write(project / "out.log", "before")
    service = ArtifactService(project)
    service.add(ArtifactCreateRequest(type="log", path=str(log)))
    log.write_text("after", encoding="utf-8")

    service.verify()
    assert _artifacts(project)[0]["status"] == "present"

    service.record_verification()
    assert _artifacts(project)[0]["status"] == "modified"


def test_verifying_an_unknown_artifact_names_the_missing_id(project: Path) -> None:
    with pytest.raises(ArtifactNotFoundError, match="ART-9999"):
        ArtifactService(project).verify("ART-9999")


# --- evidence provenance -----------------------------------------------------


def _add_evidence(root: Path, **overrides: object) -> str:
    request = EvidenceCreateRequest(
        title=str(overrides.pop("title", "Headless launch did not crash")),
        claim=str(
            overrides.pop("claim", "The prototype launches without an immediate crash.")
        ),
        classification=str(overrides.pop("classification", "observed")),
        source_type=str(overrides.pop("source_type", "runtime")),
        source=str(overrides.pop("source", "godot --headless")),
        **overrides,
    )
    return EvidenceService(root).create_evidence(request).details["evidence"]["id"]


def test_evidence_can_cite_the_run_and_artifact_behind_it(project: Path) -> None:
    run_id = _start_run(project)
    log = _write(project / "out.log", "ok\n")
    artifact_id = (
        ArtifactService(project)
        .add(ArtifactCreateRequest(type="log", path=str(log), source_run=run_id))
        .details["artifact_id"]
    )

    evidence_id = _add_evidence(
        project, related_runs=(run_id,), related_artifacts=(artifact_id,)
    )

    record = EvidenceService(project).get_evidence(evidence_id)
    assert record["related_runs"] == [run_id]
    assert record["related_artifacts"] == [artifact_id]


def test_evidence_cannot_cite_a_run_that_was_never_recorded(project: Path) -> None:
    """Citing a missing run reads as sourced while its source cannot be inspected."""

    with pytest.raises(EvidenceInputError, match="referenced run RUN-4242"):
        _add_evidence(project, related_runs=("RUN-4242",))


def test_provenance_can_be_attached_and_detached_after_the_fact(project: Path) -> None:
    run_id = _start_run(project)
    evidence_id = _add_evidence(project)
    service = EvidenceService(project)

    service.update_evidence(evidence_id, EvidencePatch(add_runs=(run_id,)))
    assert service.get_evidence(evidence_id)["related_runs"] == [run_id]

    service.update_evidence(evidence_id, EvidencePatch(remove_runs=(run_id,)))
    assert service.get_evidence(evidence_id)["related_runs"] == []


def test_a_recorded_run_is_not_evidence_by_itself(project: Path) -> None:
    """Execution records never become claims without an explicit act."""

    run_id = _start_run(project)
    RunService(project).complete(run_id, RunResult(status="passed", exit_code=0))

    assert StateRepository(project).load_evidence()["evidence"] == []


def test_reports_show_the_provenance_a_claim_rests_on(project: Path) -> None:
    run_id = _start_run(project)
    _add_evidence(project, related_runs=(run_id,))

    report = (project / ".studio" / "reports" / "current-state.md").read_text(
        encoding="utf-8"
    )

    assert f"(from {run_id})" in report


# --- CLI ---------------------------------------------------------------------


def test_execution_list_and_show_render_a_run(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _start_run(project, action="test", command=["pytest", "-q"])
    RunService(project).complete(
        run_id, RunResult(status="failed", exit_code=1, stderr_summary="2 failed")
    )

    assert cli.main(["execution", "list", "--root", str(project)]) == 0
    listed = capsys.readouterr().out
    assert run_id in listed
    assert "failed" in listed

    assert cli.main(["execution", "show", run_id, "--root", str(project)]) == 0
    shown = capsys.readouterr().out
    assert "Exit code: 1" in shown
    assert "2 failed" in shown


def test_execution_list_filters_by_action(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start_run(project, action="build")
    test_run = _start_run(project, action="test")

    cli.main(
        ["execution", "list", "--action", "test", "--root", str(project), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["data"]["count"] == 1
    assert payload["data"]["runs"][0]["id"] == test_run


def test_artifact_add_and_show_over_the_cli(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _write(project / "out.log", "ok\n")

    exit_code = cli.main(
        [
            "artifact",
            "add",
            "--type",
            "log",
            "--path",
            str(log),
            "--root",
            str(project),
            "--yes",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"]
    assert payload["data"]["artifact"]["status"] == "present"


def test_artifact_add_warns_rather_than_hiding_a_missing_file(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "artifact",
            "add",
            "--type",
            "build",
            "--path",
            "dist/game.exe",
            "--root",
            str(project),
            "--yes",
        ]
    )

    assert exit_code == 0
    assert "recorded as missing" in capsys.readouterr().out


def test_artifact_verify_exits_non_zero_when_something_does_not_match(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _write(project / "out.log", "before")
    ArtifactService(project).add(ArtifactCreateRequest(type="log", path=str(log)))
    log.write_text("after", encoding="utf-8")

    exit_code = cli.main(["artifact", "verify", "--root", str(project)])

    assert exit_code == 1
    assert "modified" in capsys.readouterr().out
