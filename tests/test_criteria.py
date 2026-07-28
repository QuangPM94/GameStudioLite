from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.criteria import (
    VERIFICATION_POLICIES,
    CriterionCreateRequest,
    CriterionEvaluation,
    CriterionInputError,
    CriterionPatch,
    CriterionService,
)
from practical_game_studio.critical_path import (
    CriticalPathService,
    PathCalculationRequest,
)
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidencePatch,
    EvidenceService,
)
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import TransactionError
from tests.conftest import managed_bytes

NOW = datetime(2026, 7, 28, 1, 0, tzinfo=UTC)


def _service(root: Path) -> CriterionService:
    return CriterionService(root, clock=lambda: NOW)


def _request(
    *,
    required: bool = True,
    description: str = "A new player completes one delivery loop unaided.",
    verification_policy: str = "observed-player-behavior",
) -> CriterionCreateRequest:
    return CriterionCreateRequest(
        description=description,
        required=required,
        completion_condition="Two of three observed testers complete the loop.",
        verification_policy=verification_policy,
        verification_method="Observed human playtest.",
    )


def _evidence(
    root: Path,
    *,
    classification: str = "observed",
    source_type: str = "human-playtest",
) -> str:
    return (
        EvidenceService(root, clock=lambda: NOW)
        .create_evidence(
            EvidenceCreateRequest(
                title="Criterion observation",
                claim="A tester completed the delivery loop.",
                classification=classification,
                source_type=source_type,
                source="criterion-evidence.txt",
                description="Recorded against the current prototype.",
            )
        )
        .details["evidence"]["id"]
    )


def test_add_allocates_after_migrated_id_and_defaults_unsupported(
    framework_repo: Path,
) -> None:
    result = _service(framework_repo).create_criterion(_request())
    criterion = result.details["criterion"]
    assert criterion["id"] == "MC-002"
    assert criterion["support_status"] == "unsupported"
    assert criterion["lifecycle_status"] == "active"
    assert criterion["evaluation_history"] == []


@pytest.mark.parametrize("policy", VERIFICATION_POLICIES)
def test_every_verification_policy_is_stored(framework_repo: Path, policy: str) -> None:
    criterion = (
        _service(framework_repo)
        .create_criterion(_request(verification_policy=policy))
        .details["criterion"]
    )

    assert criterion["verification_policy"] == policy


def test_unknown_verification_policy_fails(framework_repo: Path) -> None:
    with pytest.raises(CriterionInputError, match="verification policy"):
        _service(framework_repo).create_criterion(
            _request(verification_policy="keyword-guess")
        )


def test_add_dry_run_preserves_state_and_id(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    preview = _service(framework_repo).create_criterion(_request(), dry_run=True)
    assert managed_bytes(framework_repo) == before

    committed = _service(framework_repo).create_criterion(_request())
    assert preview.details["criterion"]["id"] == "MC-002"
    assert committed.details["criterion"]["id"] == "MC-002"


def test_partial_requires_active_evidence_and_limitation(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    evidence_id = _evidence(framework_repo)
    with pytest.raises(CriterionInputError, match="limitation"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation(
                "partially-supported", "One tester succeeded.", (evidence_id,)
            ),
        )

    result = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "partially-supported",
            "One tester succeeded.",
            (evidence_id,),
            limitations=("Two more observations are required.",),
        ),
    )
    assert result.details["criterion"]["support_status"] == "partially-supported"


def test_verified_player_behavior_requires_observed_evidence(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    inferred = _evidence(
        framework_repo,
        classification="inferred",
        source_type="source-review",
    )
    with pytest.raises(CriterionInputError, match="observed-player-behavior"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation("verified", "Source implies completion.", (inferred,)),
        )


@pytest.mark.parametrize(
    "description",
    [
        "Người chơi có thể tự hoàn thành một vòng giao hàng mà không cần trợ giúp.",
        "プレイヤーは開発者の助けなしで配送ループを完了できる。",
    ],
)
@pytest.mark.parametrize("classification", ["user-reported", "inferred"])
def test_multilingual_player_behavior_uses_policy_not_keywords(
    framework_repo: Path, description: str, classification: str
) -> None:
    criterion_id = (
        _service(framework_repo)
        .create_criterion(_request(description=description))
        .details["criterion"]["id"]
    )
    insufficient = _evidence(
        framework_repo,
        classification=classification,
        source_type="human-playtest",
    )
    with pytest.raises(CriterionInputError, match="observed-player-behavior"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation(
                "verified",
                "The criterion text language does not change the policy.",
                (insufficient,),
            ),
        )

    observed = _evidence(
        framework_repo,
        classification="observed",
        source_type="human-playtest",
    )
    result = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified",
            "Observed human playtest evidence satisfies the explicit policy.",
            (observed,),
        ),
    )

    assert result.details["criterion"]["support_status"] == "verified"


def test_verified_non_runtime_criterion_accepts_active_inferred_evidence(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo)
        .create_criterion(
            CriterionCreateRequest(
                description="Project intent is documented.",
                required=True,
                completion_condition="The game brief contains the approved intent.",
                verification_policy="document-review",
                verification_method="Document review.",
            )
        )
        .details["criterion"]["id"]
    )
    inferred = _evidence(
        framework_repo,
        classification="inferred",
        source_type="spec-review",
    )
    with pytest.raises(CriterionInputError, match="must name"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation("verified", "A document was reviewed.", (inferred,)),
        )
    result = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified",
            f"{inferred} records that criterion-evidence.txt contains the intent.",
            (inferred,),
        ),
    )
    assert result.details["criterion"]["support_status"] == "verified"


def test_automated_test_policy_accepts_test_output_and_rejects_user_note(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo)
        .create_criterion(_request(verification_policy="automated-test"))
        .details["criterion"]["id"]
    )
    user_note = _evidence(
        framework_repo,
        classification="observed",
        source_type="user-note",
    )
    with pytest.raises(CriterionInputError, match="automated-test"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation("verified", "A user note exists.", (user_note,)),
        )

    test_output = _evidence(
        framework_repo,
        classification="observed",
        source_type="test-output",
    )
    result = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified", "The automated test output passed.", (test_output,)
        ),
    )
    assert result.details["criterion"]["support_status"] == "verified"


def test_source_review_policy_requires_source_review_not_user_report(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo)
        .create_criterion(_request(verification_policy="source-review"))
        .details["criterion"]["id"]
    )
    reported = _evidence(
        framework_repo,
        classification="user-reported",
        source_type="source-review",
    )
    with pytest.raises(CriterionInputError, match="source-review"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation(
                "verified", "A user reported reviewing the source.", (reported,)
            ),
        )

    inferred = _evidence(
        framework_repo,
        classification="inferred",
        source_type="source-review",
    )
    result = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified", "The source review supports the condition.", (inferred,)
        ),
    )
    assert result.details["criterion"]["support_status"] == "verified"


def test_evaluation_history_preserved_and_exact_repeat_is_noop(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    evidence_id = _evidence(framework_repo)
    evaluation = CriterionEvaluation(
        "partially-supported",
        "One tester succeeded.",
        (evidence_id,),
        limitations=("More testers are required.",),
    )
    _service(framework_repo).evaluate_criterion(criterion_id, evaluation)
    before = managed_bytes(framework_repo)
    repeated = _service(framework_repo).evaluate_criterion(criterion_id, evaluation)
    assert repeated.details["no_op"] is True
    assert managed_bytes(framework_repo) == before

    reverted = _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation("unsupported", "The current build changed."),
    )
    criterion = reverted.details["criterion"]
    assert criterion["support_status"] == "unsupported"
    assert len(criterion["evaluation_history"]) == 2


def test_contradicted_requires_active_evidence(framework_repo: Path) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    with pytest.raises(CriterionInputError, match="active evidence"):
        _service(framework_repo).evaluate_criterion(
            criterion_id,
            CriterionEvaluation("contradicted", "Players could not finish."),
        )


def test_update_does_not_auto_evaluate_and_marks_definition_stale(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    evidence_id = _evidence(framework_repo)

    result = _service(framework_repo).update_criterion(
        criterion_id,
        CriterionPatch(
            values={"completion_condition": "Three of four testers finish."},
            add_evidence=(evidence_id,),
        ),
    )
    criterion = result.details["criterion"]
    assert criterion["support_status"] == "unsupported"
    assert criterion["evaluation_history"] == []
    assert criterion["supporting_evidence"] == [evidence_id]


def test_policy_change_stales_evaluation_and_critical_path(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    evidence_id = _evidence(framework_repo)
    _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified",
            "Observed testers met the completion condition.",
            (evidence_id,),
        ),
    )
    path_service = CriticalPathService(framework_repo, clock=lambda: NOW)
    path_service.apply_path(PathCalculationRequest())

    result = _service(framework_repo).update_criterion(
        criterion_id,
        CriterionPatch(values={"verification_policy": "mixed"}),
    )

    criterion = result.details["criterion"]
    assert criterion["verification_policy"] == "mixed"
    assert criterion["evaluation_freshness"]["status"] == "stale"
    assert len(criterion["evaluation_history"]) == 1
    assert result.details["recommended_next_command"] == "studio path calculate"
    assert (
        StateRepository(framework_repo).load_critical_path()["freshness"]["status"]
        == "stale"
    )
    freshness = path_service.check_freshness()
    assert any(
        "Milestone criterion definitions changed" in reason
        for reason in freshness.reasons
    )


def test_policy_noop_preserves_timestamps_and_reports(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    before = managed_bytes(framework_repo)

    result = _service(framework_repo).update_criterion(
        criterion_id,
        CriterionPatch(values={"verification_policy": "observed-player-behavior"}),
    )

    assert result.details["no_op"] is True
    assert managed_bytes(framework_repo) == before


def test_evidence_lifecycle_change_stales_explicit_evaluation(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    evidence_id = _evidence(framework_repo)
    _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "partially-supported",
            "One tester succeeded.",
            (evidence_id,),
            limitations=("More testers are required.",),
        ),
    )

    EvidenceService(framework_repo, clock=lambda: NOW).update_evidence(
        evidence_id, EvidencePatch(values={"status": "retracted"})
    )
    criterion = _service(framework_repo).get_criterion(criterion_id)

    assert criterion["evaluation_freshness"]["status"] == "stale"
    assert (
        StateRepository(framework_repo).load_critical_path()["freshness"]["status"]
        == "stale"
    )


def test_retire_preserves_history_and_warns_when_required(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    result = _service(framework_repo).retire_criterion(
        criterion_id, "The milestone no longer requires this behavior."
    )
    criterion = result.details["criterion"]
    assert criterion["lifecycle_status"] == "retired"
    assert criterion["retirement_reason"]
    assert result.warnings
    assert all(
        item["id"] != criterion_id for item in _service(framework_repo).list_criteria()
    )


def test_retired_ids_advance_allocation(framework_repo: Path) -> None:
    first = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    _service(framework_repo).retire_criterion(first, "Historical.")
    second = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    assert (first, second) == ("MC-002", "MC-003")


def test_criterion_support_drives_path_candidates(framework_repo: Path) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    path_service = CriticalPathService(framework_repo, clock=lambda: NOW)
    unsupported = {item.source_key: item for item in path_service.collect_candidates()}
    assert f"verification:{criterion_id}:observed-support" in unsupported

    evidence_id = _evidence(framework_repo)
    _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "contradicted",
            "Observed testers could not complete the loop.",
            (evidence_id,),
        ),
    )
    contradicted = {item.source_key: item for item in path_service.collect_candidates()}
    assert contradicted[f"milestone:{criterion_id}"].priority_tier == 1


def test_verified_criterion_is_removed_from_recalculated_path(
    framework_repo: Path,
) -> None:
    criterion_id = (
        _service(framework_repo).create_criterion(_request()).details["criterion"]["id"]
    )
    path_service = CriticalPathService(framework_repo, clock=lambda: NOW)
    path_service.apply_path(PathCalculationRequest())
    assert any(
        item["source_id"] == criterion_id
        for item in StateRepository(framework_repo).load_critical_path()["items"]
    )
    evidence_id = _evidence(framework_repo)
    _service(framework_repo).evaluate_criterion(
        criterion_id,
        CriterionEvaluation(
            "verified",
            "Observed testers met the completion condition.",
            (evidence_id,),
        ),
    )

    path_service.apply_path(PathCalculationRequest())
    path = StateRepository(framework_repo).load_critical_path()
    assert all(item["source_id"] != criterion_id for item in path["items"])
    assert any(item["source_id"] == criterion_id for item in path["history"])


def test_report_render_failure_writes_nothing(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)

    def fail_render(_: object) -> dict[str, str]:
        raise RuntimeError("injected criterion renderer failure")

    with pytest.raises(TransactionError, match="report-render"):
        CriterionService(
            framework_repo,
            clock=lambda: NOW,
            report_renderer=fail_render,
        ).create_criterion(_request())

    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))
