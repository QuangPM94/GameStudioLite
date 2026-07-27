from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.decisions import (
    DecisionCreateRequest,
    DecisionInputError,
    DecisionOption,
    DecisionPatch,
    DecisionResolution,
    DecisionService,
)
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidencePatch,
    EvidenceService,
)
from practical_game_studio.issues import IssueCreateRequest, IssueService
from practical_game_studio.reporting import render_report_contents
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import (
    ConcurrentModificationError,
    TransactionError,
)
from tests.conftest import managed_bytes


def _clock() -> datetime:
    return datetime(2026, 7, 27, 5, tzinfo=UTC)


def _later_clock() -> datetime:
    return datetime(2026, 7, 27, 6, tzinfo=UTC)


def _options(count: int = 2) -> tuple[DecisionOption, ...]:
    return tuple(
        DecisionOption(
            id=f"OPT-{chr(ord('A') + index)}",
            label=f"Option {index + 1}",
            description=f"Description {index + 1}.",
            benefits=(f"Benefit {index + 1}.",),
            risks=(f"Risk {index + 1}.",),
            effort="medium",
        )
        for index in range(count)
    )


def _request(**changes: object) -> DecisionCreateRequest:
    values: dict[str, object] = {
        "question": "How should the player locate the delivery room?",
        "context": "The corridor currently lacks sufficient guidance.",
        "options": _options(),
        "recommended_option": "OPT-B",
        "recommendation_reason": "Environmental guidance preserves immersion.",
        "urgency": "high",
        "decision_owner": "user",
        "trade_offs": ("Less explicit than a waypoint.",),
        "status": "ready",
    }
    values.update(changes)
    return DecisionCreateRequest(**values)  # type: ignore[arg-type]


def _service(root: Path, *, later: bool = False, **kwargs: object) -> DecisionService:
    return DecisionService(
        root,
        clock=_later_clock if later else _clock,
        **kwargs,  # type: ignore[arg-type]
    )


def _issue(root: Path) -> str:
    result = IssueService(root, clock=_clock).create_issue(
        IssueCreateRequest(
            title="Player cannot find room",
            severity="critical",
            player_impact="Progress stops.",
        )
    )
    return result.details["issue"]["id"]


def _evidence(
    root: Path,
    *,
    classification: str = "observed",
    status: str = "active",
    limitations: tuple[str, ...] = (),
) -> str:
    result = EvidenceService(root, clock=_clock).create_evidence(
        EvidenceCreateRequest(
            title=f"{classification.title()} support",
            claim="The corridor guidance result was recorded.",
            classification=classification,
            source_type="runtime" if classification == "observed" else "source-review",
            description="A useful artifact description.",
            limitations=limitations,
        )
    )
    evidence_id = result.details["evidence"]["id"]
    if status != "active":
        EvidenceService(root, clock=_later_clock).update_evidence(
            evidence_id, EvidencePatch(values={"status": status})
        )
    return evidence_id


def test_create_minimum_decision_uses_project_defaults(framework_repo: Path) -> None:
    result = _service(framework_repo).create_decision(_request())
    record = StateRepository(framework_repo).load_decisions()["decisions"][0]
    assert result.details["decision"]["id"] == "DEC-0001"
    assert record["phase"] == "intake"
    assert record["milestone"] == "Clarify the game idea"
    assert record["final_decision"] is None
    assert record["resolution_history"] == []


@pytest.mark.parametrize("count", range(2, 7))
def test_two_through_six_options_are_valid(framework_repo: Path, count: int) -> None:
    result = _service(framework_repo).create_decision(
        _request(options=_options(count), recommended_option="OPT-A")
    )
    assert len(result.details["decision"]["options"]) == count


@pytest.mark.parametrize("count", (1, 7))
def test_invalid_option_count_writes_nothing(framework_repo: Path, count: int) -> None:
    before = managed_bytes(framework_repo)
    with pytest.raises(DecisionInputError, match="between two and six"):
        _service(framework_repo).create_decision(
            _request(options=_options(count), recommended_option="OPT-A")
        )
    assert managed_bytes(framework_repo) == before


def test_duplicate_option_ids_and_labels_fail(framework_repo: Path) -> None:
    duplicate_id = replace(_options()[1], id="OPT-A")
    with pytest.raises(DecisionInputError, match="IDs"):
        _service(framework_repo).create_decision(
            _request(options=(_options()[0], duplicate_id))
        )
    duplicate_label = replace(_options()[1], label="option 1")
    with pytest.raises(DecisionInputError, match="labels"):
        _service(framework_repo).create_decision(
            _request(options=(_options()[0], duplicate_label))
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"question": " "}, "question"),
        ({"context": ""}, "context"),
        ({"recommendation_reason": ""}, "recommendation reason"),
        ({"recommended_option": "OPT-Z"}, "recommended option"),
    ),
)
def test_invalid_required_creation_values_fail(
    framework_repo: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(DecisionInputError, match=message):
        _service(framework_repo).create_decision(_request(**changes))


def test_historical_decisions_advance_ids_and_dry_run_does_not(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_decision(_request())
    service.resolve_decision(
        "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Selected.")
    )
    dry = service.create_decision(_request(question="Second question?"), dry_run=True)
    assert dry.details["decision"]["id"] == "DEC-0002"
    real = service.create_decision(_request(question="Second question?"))
    assert real.details["decision"]["id"] == "DEC-0002"


def test_dry_run_preserves_all_managed_files(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    result = _service(framework_repo).create_decision(_request(), dry_run=True)
    assert result.dry_run
    assert managed_bytes(framework_repo) == before


def test_creation_validates_issue_and_evidence_links(framework_repo: Path) -> None:
    issue_id = _issue(framework_repo)
    evidence_id = _evidence(framework_repo)
    result = _service(framework_repo).create_decision(
        _request(
            affected_issues=(issue_id,),
            supporting_evidence=(evidence_id,),
        )
    )
    assert result.details["decision"]["affected_issues"] == [issue_id]
    assert result.details["decision"]["evidence_support"]["level"] == "strong"
    with pytest.raises(DecisionInputError, match="ISS-9999"):
        _service(framework_repo).create_decision(
            _request(affected_issues=("ISS-9999",))
        )
    with pytest.raises(DecisionInputError, match="EVD-9999"):
        _service(framework_repo).create_decision(
            _request(supporting_evidence=("EVD-9999",))
        )


def test_fully_populated_decision_preserves_optional_fields(
    framework_repo: Path,
) -> None:
    issue_id = _issue(framework_repo)
    evidence_id = _evidence(framework_repo)
    record = (
        _service(framework_repo)
        .create_decision(
            _request(
                phase="evaluate",
                milestone="Evaluate corridor clarity",
                decision_required_by="2026-08-01",
                affected_issues=(issue_id,),
                supporting_evidence=(evidence_id,),
                revisit_condition="Revisit after two more testers.",
            )
        )
        .details["decision"]
    )
    assert record["phase"] == "evaluate"
    assert record["decision_required_by"] == "2026-08-01"
    assert record["revisit_condition"] == "Revisit after two more testers."


def test_retracted_evidence_is_historical_not_current_support(
    framework_repo: Path,
) -> None:
    evidence_id = _evidence(framework_repo, status="retracted")
    result = _service(framework_repo).create_decision(
        _request(supporting_evidence=(evidence_id,))
    )
    assert result.details["decision"]["evidence_support"]["level"] == "unsupported"
    assert result.warnings


def test_support_levels_are_deterministic(framework_repo: Path) -> None:
    inferred = _evidence(framework_repo, classification="inferred")
    user_reported = _evidence(framework_repo, classification="user-reported")
    service = _service(framework_repo)
    weak = service.create_decision(_request(supporting_evidence=(inferred,))).details[
        "decision"
    ]
    moderate = service.create_decision(
        _request(
            question="Second supported question?",
            supporting_evidence=(inferred, user_reported),
        )
    ).details["decision"]
    unsupported = service.create_decision(
        _request(question="Unsupported question?")
    ).details["decision"]
    assert weak["evidence_support"]["level"] == "weak"
    assert moderate["evidence_support"]["level"] == "moderate"
    assert unsupported["evidence_support"]["level"] == "unsupported"


def test_explicit_active_evidence_conflict_is_reported(
    framework_repo: Path,
) -> None:
    first = _evidence(framework_repo, classification="inferred")
    second = _evidence(
        framework_repo,
        classification="user-reported",
        limitations=(f"Conflicts with {first}",),
    )
    record = (
        _service(framework_repo)
        .create_decision(_request(supporting_evidence=(first, second)))
        .details["decision"]
    )
    assert record["evidence_support"]["level"] == "conflicted"


def test_list_filters_history_and_sorts_priority(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request(question="High?", urgency="high"))
    service.create_decision(
        _request(question="Blocking?", urgency="blocking", decision_owner="producer")
    )
    service.resolve_decision(
        "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Done.")
    )
    assert [item["id"] for item in service.list_decisions()] == ["DEC-0002"]
    assert len(service.list_decisions(include_all=True)) == 2
    assert len(service.list_decisions(resolved=True)) == 1
    assert len(service.list_decisions(urgency="blocking")) == 1
    assert len(service.list_decisions(owner="producer")) == 1


def test_list_filters_phase_issue_and_evidence(framework_repo: Path) -> None:
    issue_id = _issue(framework_repo)
    evidence_id = _evidence(framework_repo)
    service = _service(framework_repo)
    service.create_decision(
        _request(
            phase="evaluate",
            affected_issues=(issue_id,),
            supporting_evidence=(evidence_id,),
        )
    )
    assert len(service.list_decisions(phase="evaluate")) == 1
    assert len(service.list_decisions(issue_id=issue_id)) == 1
    assert len(service.list_decisions(evidence_id=evidence_id)) == 1


def test_update_metadata_references_and_options(framework_repo: Path) -> None:
    issue_id = _issue(framework_repo)
    evidence_id = _evidence(framework_repo)
    service = _service(framework_repo)
    service.create_decision(_request())
    result = _service(framework_repo, later=True).update_decision(
        "DEC-0001",
        DecisionPatch(
            values={
                "question": "Updated question?",
                "urgency": "blocking",
                "recommended_option": "OPT-C",
            },
            add_issues=(issue_id, issue_id),
            add_evidence=(evidence_id,),
            add_options=(
                DecisionOption("OPT-C", "Third option", "A third direction."),
            ),
            add_trade_offs=("New trade-off.",),
        ),
    )
    record = result.details["decision"]
    assert record["recommended_option"] == "OPT-C"
    assert record["affected_issues"] == [issue_id]
    assert record["supporting_evidence"] == [evidence_id]
    assert record["updated_at"] == "2026-07-27T06:00:00Z"


def test_update_and_remove_option_and_references(framework_repo: Path) -> None:
    issue_id = _issue(framework_repo)
    evidence_id = _evidence(framework_repo)
    service = _service(framework_repo)
    service.create_decision(
        _request(
            options=_options(3),
            affected_issues=(issue_id,),
            supporting_evidence=(evidence_id,),
        )
    )
    result = service.update_decision(
        "DEC-0001",
        DecisionPatch(
            update_options=(
                DecisionOption("OPT-A", "Updated option", "Updated description."),
            ),
            remove_options=("OPT-C",),
            remove_issues=(issue_id,),
            remove_evidence=(evidence_id,),
        ),
    )
    record = result.details["decision"]
    assert record["options"][0]["label"] == "Updated option"
    assert len(record["options"]) == 2
    assert record["affected_issues"] == []
    assert record["supporting_evidence"] == []


def test_remove_recommended_or_historical_option_fails(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request(options=_options(3)))
    with pytest.raises(DecisionInputError, match="recommended option"):
        service.update_decision("DEC-0001", DecisionPatch(remove_options=("OPT-B",)))
    service.resolve_decision(
        "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Done.")
    )
    service.update_decision("DEC-0001", DecisionPatch(values={"status": "open"}))
    with pytest.raises(TransactionError, match="resolution history"):
        service.update_decision(
            "DEC-0001",
            DecisionPatch(
                values={"recommended_option": "OPT-A"},
                remove_options=("OPT-B",),
            ),
        )


def test_noop_and_dry_update_preserve_bytes(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request())
    before = managed_bytes(framework_repo)
    noop = _service(framework_repo, later=True).update_decision(
        "DEC-0001", DecisionPatch(values={"question": _request().question})
    )
    assert noop.details["no_op"] is True
    assert managed_bytes(framework_repo) == before
    dry = service.update_decision(
        "DEC-0001", DecisionPatch(values={"urgency": "blocking"}), dry_run=True
    )
    assert dry.dry_run
    assert managed_bytes(framework_repo) == before


def test_status_transitions_and_resolve_requires_resolve_command(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_decision(_request(status="open"))
    service.update_decision("DEC-0001", DecisionPatch(values={"status": "blocked"}))
    with pytest.raises(DecisionInputError, match="invalid decision transition"):
        service.update_decision(
            "DEC-0001", DecisionPatch(values={"status": "superseded"})
        )
    service.update_decision("DEC-0001", DecisionPatch(values={"status": "open"}))
    with pytest.raises(DecisionInputError, match="decision resolve"):
        service.update_decision(
            "DEC-0001", DecisionPatch(values={"status": "resolved"})
        )


def test_resolve_recommended_override_and_custom(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request())
    followed = service.resolve_decision(
        "DEC-0001",
        DecisionResolution(
            option_id="OPT-B",
            reason="Preserves immersion.",
            consequences=("Update signage.",),
            follow_up_actions=("Run another playtest.",),
            revisit_condition="Two testers still fail.",
        ),
    ).details["decision"]
    assert followed["recommendation_followed"] is True
    assert followed["final_option_id"] == "OPT-B"
    assert (
        followed["resolution_history"][0]["decision_reason"] == "Preserves immersion."
    )

    service.create_decision(_request(question="Override?"))
    override = service.resolve_decision(
        "DEC-0002", DecisionResolution(option_id="OPT-A", reason="Clarity wins.")
    ).details["decision"]
    assert override["recommendation_followed"] is False

    service.create_decision(_request(question="Custom?"))
    custom = service.resolve_decision(
        "DEC-0003",
        DecisionResolution(custom_decision="Combine both options.", reason="Best fit."),
    ).details["decision"]
    assert custom["final_option_id"] is None
    assert custom["recommendation_followed"] is False


def test_resolution_validation_and_duplicate_resolution(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request())
    with pytest.raises(DecisionInputError, match="exactly one"):
        service.resolve_decision("DEC-0001", DecisionResolution(reason="No choice."))
    with pytest.raises(DecisionInputError, match="OPT-Z"):
        service.resolve_decision(
            "DEC-0001", DecisionResolution(option_id="OPT-Z", reason="Invalid.")
        )
    with pytest.raises(DecisionInputError, match="reason"):
        service.resolve_decision(
            "DEC-0001", DecisionResolution(option_id="OPT-B", reason="")
        )
    service.resolve_decision(
        "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Done.")
    )
    with pytest.raises(DecisionInputError, match="already resolved"):
        service.resolve_decision(
            "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Again.")
        )


def test_resolution_dry_run_and_reopen_preserve_history(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_decision(_request())
    before = managed_bytes(framework_repo)
    dry = service.resolve_decision(
        "DEC-0001",
        DecisionResolution(option_id="OPT-B", reason="Preview."),
        dry_run=True,
    )
    assert dry.details["decision"]["status"] == "resolved"
    assert managed_bytes(framework_repo) == before
    service.resolve_decision(
        "DEC-0001", DecisionResolution(option_id="OPT-B", reason="Final.")
    )
    reopened = service.update_decision(
        "DEC-0001", DecisionPatch(values={"status": "open"})
    ).details["decision"]
    assert reopened["status"] == "open"
    assert reopened["final_decision"] is None
    assert reopened["resolution_history"][0]["decision_reason"] == "Final."


def test_supersession_marks_old_and_rejects_invalid_targets(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_decision(_request(question="Old?"))
    service.create_decision(_request(question="Replacement?"))
    result = service.update_decision("DEC-0002", DecisionPatch(supersedes="DEC-0001"))
    state = StateRepository(framework_repo).load_decisions()["decisions"]
    assert result.details["decision"]["supersedes"] == "DEC-0001"
    assert state[0]["status"] == "superseded"
    with pytest.raises(DecisionInputError, match="itself"):
        service.update_decision("DEC-0002", DecisionPatch(supersedes="DEC-0002"))
    with pytest.raises(DecisionInputError, match="does not exist"):
        service.create_decision(_request(question="Third?"))
        service.update_decision("DEC-0003", DecisionPatch(supersedes="DEC-9999"))


def test_report_failure_and_concurrent_change_write_nothing(
    framework_repo: Path,
) -> None:
    before = managed_bytes(framework_repo)

    def fail(_: object) -> dict[str, str]:
        raise RuntimeError("injected decision renderer failure")

    with pytest.raises(TransactionError, match="report-render"):
        _service(framework_repo, report_renderer=fail).create_decision(_request())
    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))

    decision_path = framework_repo / ".studio" / "state" / "decisions.json"

    def modify(state: object) -> dict[str, str]:
        decision_path.write_bytes(decision_path.read_bytes() + b" ")
        return render_report_contents(state)  # type: ignore[arg-type]

    with pytest.raises(ConcurrentModificationError, match="Reload and retry"):
        _service(framework_repo, report_renderer=modify).create_decision(_request())
    assert StateRepository(framework_repo).load_decisions()["decisions"] == []
