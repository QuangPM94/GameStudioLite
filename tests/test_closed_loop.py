"""Closed-loop evidence, workflow readiness, and execution safety.

These are the three things that keep the framework honest once it can run a
game: advice must stay separate from evaluation, readiness must be computed
rather than believed, and an agent must not be able to authorise itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.criteria import (
    CriterionCreateRequest,
    CriterionPatch,
    CriterionService,
)
from practical_game_studio.criterion_support import assess_support
from practical_game_studio.evidence import EvidenceCreateRequest, EvidenceService
from practical_game_studio.safety import (
    ExecutionDeniedError,
    authorize,
    classify,
    evaluate,
    requires_approval,
)
from practical_game_studio.state import StateRepository
from practical_game_studio.workflow_readiness import (
    evaluate_workflow_readiness,
    list_ready_workflows,
    recommend_next_workflow,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    BootstrapService(tmp_path).bootstrap(
        BootstrapRequest(name="Loop Demo", engine="Godot")
    )
    return tmp_path


def _add_criterion(root: Path, policy: str) -> str:
    return (
        CriterionService(root)
        .create_criterion(
            CriterionCreateRequest(
                description="Players finish a delivery unaided.",
                required=True,
                completion_condition="A player completes one delivery loop.",
                verification_policy=policy,
            )
        )
        .details["criterion"]["id"]
    )


def _add_evidence(root: Path, **overrides: object) -> str:
    request = EvidenceCreateRequest(
        title=str(overrides.pop("title", "Observation")),
        claim=str(overrides.pop("claim", "Something was observed.")),
        classification=str(overrides.pop("classification", "observed")),
        source_type=str(overrides.pop("source_type", "runtime")),
        source=str(overrides.pop("source", "godot --headless")),
        **overrides,
    )
    return EvidenceService(root).create_evidence(request).details["evidence"]["id"]


# --- criterion support (read-only advice) ------------------------------------


def test_support_reports_what_the_policy_requires(project: Path) -> None:
    criterion_id = _add_criterion(project, "observed-player-behavior")

    assessment = assess_support(project, criterion_id)

    assert assessment.policy == "observed-player-behavior"
    assert "human" in assessment.required_policy
    assert assessment.missing
    assert not assessment.could_be_verified


def test_support_never_evaluates_anything(project: Path) -> None:
    """A command that both advised and decided could talk itself into a pass."""

    criterion_id = _add_criterion(project, "automated-test")
    before = StateRepository(project).load_milestone()

    assess_support(project, criterion_id)

    assert StateRepository(project).load_milestone() == before


def test_support_separates_qualifying_from_non_qualifying_evidence(
    project: Path,
) -> None:
    criterion_id = _add_criterion(project, "automated-test")
    qualifying = _add_evidence(project, source_type="test-output", title="Suite passed")
    wrong_kind = _add_evidence(
        project,
        source_type="user-note",
        classification="user-reported",
        title="Someone said it works",
    )
    CriterionService(project).update_criterion(
        criterion_id,
        CriterionPatch(add_evidence=(qualifying, wrong_kind)),
    )

    assessment = assess_support(project, criterion_id)

    assert [row["id"] for row in assessment.qualifying_evidence] == [qualifying]
    assert [row["id"] for row in assessment.non_qualifying_evidence] == [wrong_kind]
    assert "user-reported" in assessment.non_qualifying_evidence[0]["reason"]


def test_support_recommends_without_deciding(project: Path) -> None:
    criterion_id = _add_criterion(project, "automated-test")

    assessment = assess_support(project, criterion_id)

    assert "your judgement" in assessment.recommendation or assessment.missing
    assert assessment.support_status == "unsupported"


def test_support_command_states_it_did_not_evaluate(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    criterion_id = _add_criterion(project, "automated-test")

    exit_code = cli.main(["criterion", "support", criterion_id, "--root", str(project)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "read-only" in output
    assert "Missing evidence:" in output


# --- workflow readiness -------------------------------------------------------


def test_a_workflow_with_unmet_requirements_is_blocked(project: Path) -> None:
    readiness = evaluate_workflow_readiness(project, "build-prototype")

    assert not readiness.ready
    assert readiness.status == "blocked"
    assert {item.name for item in readiness.blockers} >= {"prototype_hypothesis"}


def test_a_workflow_without_declared_requirements_is_ready(project: Path) -> None:
    """Not declaring a gate must not mean being gated."""

    readiness = evaluate_workflow_readiness(project, "start")

    assert readiness.ready
    assert readiness.requirements == ()


def test_an_unknown_requirement_never_reads_as_satisfied(project: Path) -> None:
    catalog = json.loads(
        (project / ".studio" / "workflow-catalog.json").read_text(encoding="utf-8")
    )
    for workflow in catalog["workflows"]:
        if workflow["id"] == "start":
            workflow["requires"] = {"a_requirement_from_the_future": True}

    readiness = evaluate_workflow_readiness(project, "start", catalog=catalog)

    assert readiness.requirements[0].outcome == "unknown"
    assert readiness.requirements[0].outcome != "satisfied"


def test_an_unknown_requirement_does_not_block(project: Path) -> None:
    """Otherwise a planning-only project could never run anything."""

    catalog = json.loads(
        (project / ".studio" / "workflow-catalog.json").read_text(encoding="utf-8")
    )
    for workflow in catalog["workflows"]:
        if workflow["id"] == "start":
            workflow["requires"] = {"engine_run_capability": True}

    readiness = evaluate_workflow_readiness(project, "start", catalog=catalog)

    assert readiness.caveats
    assert readiness.ready
    assert readiness.status == "ready-with-unknowns"


def test_ready_with_unknowns_is_distinct_from_ready(project: Path) -> None:
    plain = evaluate_workflow_readiness(project, "start")

    assert plain.status == "ready"
    assert plain.status != "ready-with-unknowns"


def test_readiness_is_computed_from_state_not_guessed(project: Path) -> None:
    blocked = evaluate_workflow_readiness(project, "issue-map")
    assert not blocked.ready

    cli.main(
        [
            "issue",
            "add",
            "--root",
            str(project),
            "--title",
            "Player cannot move",
            "--severity",
            "major",
            "--description",
            "Input is ignored after the first frame.",
            "--category",
            "mechanic",
            "--player-impact",
            "The game cannot be played.",
            "--milestone-impact",
            "Blocks the prototype hypothesis.",
            "--recommended-action",
            "Investigate input handling.",
            "--effort",
            "medium",
            "--owner",
            "developer",
            "--yes",
        ]
    )

    assert evaluate_workflow_readiness(project, "issue-map").ready


def test_recommendation_prefers_the_current_phase(project: Path) -> None:
    recommended = recommend_next_workflow(project)

    assert recommended is not None
    assert recommended.ready
    assert recommended.workflow_id == "start"


def test_every_catalog_workflow_can_be_evaluated(project: Path) -> None:
    evaluated = list_ready_workflows(project)

    assert len(evaluated) == 18
    assert all(
        item.status in {"ready", "ready-with-unknowns", "blocked"} for item in evaluated
    )


def test_workflow_check_exits_non_zero_when_blocked(project: Path) -> None:
    assert (
        cli.main(["workflow", "check", "build-prototype", "--root", str(project)]) == 1
    )
    assert cli.main(["workflow", "check", "start", "--root", str(project)]) == 0


def test_workflow_explain_prints_empty_sections(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "Nothing blocks this" and "we did not look" must not render the same."""

    cli.main(["workflow", "explain", "start", "--root", str(project)])
    output = capsys.readouterr().out

    assert "Blockers:" in output
    assert "Could not be determined:" in output


def test_workflow_ready_names_no_recommendation_rather_than_a_bad_one(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["workflow", "ready", "--root", str(project)])
    output = capsys.readouterr().out

    assert "Recommended next workflow:" in output


# --- execution safety ---------------------------------------------------------


def test_reading_state_is_never_gated() -> None:
    for operation in ("doctor", "status", "execution.list", "criterion.support"):
        assert classify(operation) == "safe"
        assert not requires_approval(operation, "strict")


def test_building_is_gated_under_guided_review() -> None:
    assert classify("build") == "medium"
    assert requires_approval("build", "guided")
    assert requires_approval("build", "strict")
    assert not requires_approval("build", "fast")


def test_fast_review_still_gates_high_risk() -> None:
    """A review preference is not a licence to delete things unasked."""

    assert requires_approval("files.delete", "fast")


def test_an_unclassified_operation_defaults_to_high_risk() -> None:
    """The cautious default is the only safe one for something unrecognised."""

    assert classify("something.the.framework.has.never.heard.of") == "high"
    assert requires_approval("something.the.framework.has.never.heard.of", "fast")


def test_an_agent_cannot_authorise_itself_by_being_unsupervised(
    project: Path,
) -> None:
    decision = evaluate(project, "build", interactive=False)

    assert not decision.allowed
    assert decision.authorization == "denied"
    assert "nobody to ask" in decision.message


def test_a_denial_names_the_flag_that_would_authorise_it(project: Path) -> None:
    with pytest.raises(ExecutionDeniedError) as raised:
        authorize(project, "build", interactive=False)

    message = str(raised.value)
    assert "--yes" in message
    assert "Nothing was executed" in message
    assert "medium risk" in message


def test_the_yes_flag_authorises_a_medium_risk_operation(project: Path) -> None:
    decision = authorize(project, "build", acknowledged=True, interactive=False)

    assert decision.allowed
    assert decision.authorization == "flag"


def test_the_yes_flag_is_not_enough_for_high_risk_without_a_person(
    project: Path,
) -> None:
    decision = evaluate(project, "files.delete", acknowledged=True, interactive=False)

    assert not decision.allowed
    assert "need a person present" in decision.message


def test_json_output_never_prompts(project: Path) -> None:
    """Prompting into a pipe would hang a caller with no way to answer."""

    decision = evaluate(project, "build", interactive=True, json_output=True)

    assert not decision.allowed
    assert decision.authorization == "denied"


def test_a_refused_build_exits_with_its_own_code(project: Path) -> None:
    """A refusal is neither a crash nor a usage error."""

    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")

    assert cli.main(["build", "--root", str(project)]) == 5


def test_a_refused_build_changes_nothing(project: Path) -> None:
    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

    cli.main(["build", "--root", str(project)])

    assert {
        path: path.read_bytes() for path in project.rglob("*") if path.is_file()
    } == before


def test_a_run_records_how_it_was_authorised(project: Path) -> None:
    """ "Who agreed to this build?" must be answerable from the record."""

    from practical_game_studio.runs import RunCreateRequest, RunService

    RunService(project).create(
        RunCreateRequest(action="build", risk_level="medium", authorization="flag")
    )

    record = StateRepository(project).load_runs()["runs"][0]
    assert record["risk_level"] == "medium"
    assert record["authorization"] == "flag"
