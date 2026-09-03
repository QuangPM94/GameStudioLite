"""Opt-in end-to-end checks against an actual Godot executable.

The ordinary suite remains hermetic. CI sets ``PGS_REAL_GODOT_BINARY`` for a
separate job so the reference adapter is also exercised against the engine it
claims to control, rather than only against the deterministic fake used by the
unit tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _godot_binary() -> Path:
    configured = os.environ.get("PGS_REAL_GODOT_BINARY")
    if configured is None:
        pytest.skip("set PGS_REAL_GODOT_BINARY to run the real-Godot integration")
    binary = Path(configured).resolve()
    assert binary.is_file(), f"real Godot binary does not exist: {binary}"
    return binary


def _write_quitting_project(root: Path) -> None:
    """Create the smallest Godot game that launches and exits deliberately."""

    (root / "project.godot").write_text(
        """config_version=5

[application]
config/name="GameStudioLite CI Smoke"
run/main_scene="res://Main.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
""",
        encoding="utf-8",
    )
    (root / "Main.tscn").write_text(
        """[gd_scene load_steps=2 format=3]

[ext_resource path="res://Main.gd" type="Script" id="1"]

[node name="Main" type="Node"]
script = ExtResource("1")
""",
        encoding="utf-8",
    )
    (root / "Main.gd").write_text(
        """extends Node

func _ready():
    print("PGS_REAL_GODOT_SMOKE_OK")
    get_tree().quit()
""",
        encoding="utf-8",
    )


def _studio(root: Path, *arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "practical_game_studio.cli",
            *arguments,
            "--root",
            str(root),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert completed.returncode == 0, (
        f"studio {' '.join(arguments)} exited {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_real_godot_closed_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    godot = _godot_binary()
    monkeypatch.setenv("GODOT", str(godot))
    _write_quitting_project(tmp_path)

    bootstrap = _studio(
        tmp_path,
        "bootstrap",
        "--name",
        "Real Godot Smoke",
        "--engine",
        "Godot",
    )
    assert bootstrap["success"] is True

    doctor = _studio(tmp_path, "doctor")
    doctor_data = doctor["data"]
    assert doctor_data["resolved_adapter"] == "godot-cli"
    assert doctor_data["engine"]["engine_version"].startswith("4.7.2")
    readiness = {
        item["capability"]: item["readiness"] for item in doctor_data["capabilities"]
    }
    assert readiness["RUN"] == "ready"
    assert readiness["HEADLESS"] == "ready"

    launched = _studio(tmp_path, "run", "--headless", "--timeout", "10")
    launched_data = launched["data"]
    assert launched_data["status"] == "passed"
    assert launched_data["run_id"] == "RUN-0001"
    assert launched_data["artifacts"] == ["ART-0001"]

    log_path = tmp_path / ".studio" / "logs" / "run-0001.log"
    assert log_path.is_file()
    assert "PGS_REAL_GODOT_SMOKE_OK" in log_path.read_text(encoding="utf-8")

    verified = _studio(tmp_path, "verify", "--level", "smoke")
    verified_data = verified["data"]
    assert verified_data["status"] == "passed"
    assert [check["status"] for check in verified_data["checks"]] == [
        "passed",
        "passed",
    ]
    assert verified_data["evidence_proposals"]

    proposal = verified_data["evidence_proposals"][0]
    evidence_arguments = [
        "evidence",
        "add",
        "--title",
        "Real Godot smoke launch",
        "--claim",
        proposal["claim"],
        "--classification",
        proposal["classification"],
        "--source-type",
        proposal["source_type"],
        "--description",
        "Accepted from the smoke verification proposal for the pinned CI runtime.",
        "--yes",
    ]
    for run_id in proposal["related_runs"]:
        evidence_arguments.extend(("--run", run_id))
    for artifact_id in proposal["related_artifacts"]:
        evidence_arguments.extend(("--artifact", artifact_id))
    for limitation in proposal["limitations"]:
        evidence_arguments.extend(("--limitation", limitation))
    evidence = _studio(tmp_path, *evidence_arguments)
    evidence_id = evidence["data"]["evidence"]["id"]

    criterion = _studio(
        tmp_path,
        "criterion",
        "add",
        "--description",
        "The prototype launches in the pinned real Godot runtime.",
        "--required",
        "--completion-condition",
        "A real Godot process launches and exits cleanly.",
        "--verification-policy",
        "observed-runtime",
        "--yes",
    )
    criterion_id = criterion["data"]["criterion"]["id"]
    evaluated = _studio(
        tmp_path,
        "criterion",
        "evaluate",
        criterion_id,
        "--support",
        "verified",
        "--reason",
        "The pinned Godot process emitted the expected marker and exited zero.",
        "--evidence",
        evidence_id,
        "--yes",
    )
    assert evaluated["data"]["criterion"]["support_status"] == "verified"

    calculated = _studio(tmp_path, "path", "calculate", "--yes")
    assert calculated["success"] is True

    runs = json.loads((tmp_path / ".studio" / "state" / "runs.json").read_text())
    artifacts = json.loads(
        (tmp_path / ".studio" / "state" / "artifacts.json").read_text()
    )
    evidence_state = json.loads(
        (tmp_path / ".studio" / "state" / "evidence.json").read_text()
    )
    milestone = json.loads(
        (tmp_path / ".studio" / "state" / "milestone.json").read_text()
    )
    critical_path = json.loads(
        (tmp_path / ".studio" / "state" / "critical-path.json").read_text()
    )
    assert [run["status"] for run in runs["runs"]] == ["passed", "passed"]
    assert all(run["engine"] == "Godot" for run in runs["runs"])
    assert all(run["engine_version"].startswith("4.7.2") for run in runs["runs"])
    assert len(artifacts["artifacts"]) == 2
    assert all(artifact["sha256"] for artifact in artifacts["artifacts"])
    assert evidence_state["evidence"][0]["related_runs"] == ["RUN-0002"]
    assert evidence_state["evidence"][0]["related_artifacts"] == ["ART-0002"]
    criterion_state = next(
        item for item in milestone["criteria_results"] if item["id"] == criterion_id
    )
    assert criterion_state["support_status"] == "verified"
    assert criterion_state["supporting_evidence"] == [evidence_id]
    assert critical_path["freshness"]["status"] == "current"
    assert criterion_id not in {
        item.get("source_id") for item in critical_path["items"]
    }
