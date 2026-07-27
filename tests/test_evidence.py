from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidenceInputError,
    EvidencePatch,
    EvidenceService,
    allocate_evidence_id,
)
from practical_game_studio.issues import (
    IssueCreateRequest,
    IssueService,
)
from practical_game_studio.reporting import render_report_contents
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import (
    ConcurrentModificationError,
    TransactionError,
)
from tests.conftest import managed_bytes

NOW = datetime(2026, 7, 27, 5, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 27, 6, 0, 0, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _later_clock() -> datetime:
    return LATER


def _request(**changes: object) -> EvidenceCreateRequest:
    values: dict[str, object] = {
        "title": "Player stopped in corridor",
        "claim": "The player could not identify the target apartment.",
        "classification": "user-reported",
        "source_type": "human-playtest",
        "description": "Tester remained in the corridor for forty seconds.",
    }
    values.update(changes)
    return EvidenceCreateRequest(**values)  # type: ignore[arg-type]


def _service(root: Path, *, later: bool = False) -> EvidenceService:
    return EvidenceService(root, clock=_later_clock if later else _clock)


def _create_issue(root: Path, title: str = "Room is unclear") -> str:
    result = IssueService(root, clock=_clock).create_issue(
        IssueCreateRequest(
            title=title,
            severity="critical",
            player_impact="The player cannot progress.",
        )
    )
    return result.details["issue"]["id"]


def test_create_minimum_evidence_uses_defaults(framework_repo: Path) -> None:
    result = _service(framework_repo).create_evidence(_request())
    record = StateRepository(framework_repo).load_evidence()["evidence"][0]

    assert result.success
    assert record["id"] == "EVD-0001"
    assert record["confidence"] == "medium"
    assert record["status"] == "active"
    assert record["source"] is None
    assert record["captured_at"] == "2026-07-27T05:00:00Z"
    assert record["created_at"] == record["updated_at"]


def test_create_fully_populated_evidence_normalizes_values(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    _service(framework_repo).create_evidence(
        _request(
            title="  Launch result  ",
            claim="  Prototype launches successfully.  ",
            classification=" OBSERVED ",
            source_type=" TEST_OUTPUT ",
            source="  pytest output  ",
            description="  Clean launch.  ",
            related_hypothesis="  The build is runnable.  ",
            related_issues=(issue_id, issue_id),
            confidence=" HIGH ",
            limitations=("  Windows only.  ", "Windows only."),
            captured_at="2026-07-26T22:00:00-07:00",
        )
    )
    record = StateRepository(framework_repo).load_evidence()["evidence"][0]

    assert record["title"] == "Launch result"
    assert record["classification"] == "observed"
    assert record["source_type"] == "test-output"
    assert record["source"] == "pytest output"
    assert record["related_issues"] == ["ISS-0001"]
    assert record["limitations"] == ["Windows only."]
    assert record["captured_at"] == "2026-07-27T05:00:00Z"


@pytest.mark.parametrize(
    ("classification", "confidence"),
    [
        ("observed", "medium"),
        ("user-reported", "medium"),
        ("inferred", "low"),
        ("unknown", "low"),
    ],
)
def test_default_confidence_by_classification(
    framework_repo: Path, classification: str, confidence: str
) -> None:
    result = _service(framework_repo).create_evidence(
        _request(classification=classification)
    )
    assert result.details["evidence"]["confidence"] == confidence


def test_explicit_confidence_overrides_default(framework_repo: Path) -> None:
    result = _service(framework_repo).create_evidence(
        _request(classification="inferred", confidence="high")
    )
    assert result.details["evidence"]["confidence"] == "high"


def test_id_allocation_uses_highest_historical_id() -> None:
    assert allocate_evidence_id([{"id": "EVD-0009"}, {"id": "EVD-0042"}]) == "EVD-0043"


def test_historical_evidence_advances_ids(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request())
    service.update_evidence("EVD-0001", EvidencePatch(values={"status": "retracted"}))
    result = service.create_evidence(_request(title="Second record"))
    assert result.details["evidence"]["id"] == "EVD-0002"


def test_dry_run_does_not_write_or_consume_id(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    preview = _service(framework_repo).create_evidence(_request(), dry_run=True)
    assert managed_bytes(framework_repo) == before
    real = _service(framework_repo).create_evidence(_request())

    assert preview.details["evidence"]["id"] == "EVD-0001"
    assert real.details["evidence"]["id"] == "EVD-0001"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"title": " "}, "title cannot be empty"),
        ({"claim": " "}, "claim cannot be empty"),
        ({"classification": "certain"}, "invalid classification"),
        ({"source_type": "memory"}, "invalid source type"),
    ],
)
def test_invalid_creation_writes_nothing(
    framework_repo: Path, changes: dict[str, object], message: str
) -> None:
    before = managed_bytes(framework_repo)
    with pytest.raises(EvidenceInputError, match=message):
        _service(framework_repo).create_evidence(_request(**changes))
    assert managed_bytes(framework_repo) == before


def test_source_required_for_artifact_types(framework_repo: Path) -> None:
    with pytest.raises(EvidenceInputError, match="source is required"):
        _service(framework_repo).create_evidence(
            _request(source_type="screenshot", source=None)
        )


def test_optional_source_requires_useful_description(framework_repo: Path) -> None:
    with pytest.raises(EvidenceInputError, match="description is required"):
        _service(framework_repo).create_evidence(
            _request(source_type="runtime", source=None, description=None)
        )
    result = _service(framework_repo).create_evidence(
        _request(source_type="runtime", source=None, description="Observed directly.")
    )
    assert result.success


def test_create_links_evidence_and_issue_bidirectionally(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    _service(framework_repo).create_evidence(
        _request(
            classification="observed",
            source_type="runtime",
            related_issues=(issue_id,),
        )
    )
    state = StateRepository(framework_repo).load_all()

    assert state["evidence"]["evidence"][0]["related_issues"] == [issue_id]
    assert state["issues"]["issues"][0]["evidence_references"] == ["EVD-0001"]
    assert state["issues"]["issues"][0]["evidence_type"] == "OBSERVED"


def test_missing_related_issue_fails_transactionally(
    framework_repo: Path,
) -> None:
    before = managed_bytes(framework_repo)
    with pytest.raises(EvidenceInputError, match="does not exist"):
        _service(framework_repo).create_evidence(_request(related_issues=("ISS-9999",)))
    assert managed_bytes(framework_repo) == before


def test_list_defaults_filters_and_historical_visibility(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    service = _service(framework_repo)
    service.create_evidence(
        _request(
            title="Observed",
            classification="observed",
            source_type="test-output",
            source="test.log",
            confidence="high",
            related_issues=(issue_id,),
            captured_at="2026-07-27T05:00:00Z",
        )
    )
    service.create_evidence(
        _request(
            title="Inferred",
            classification="inferred",
            source_type="source-review",
            captured_at="2026-07-27T06:00:00Z",
        )
    )
    service.update_evidence("EVD-0001", EvidencePatch(values={"status": "retracted"}))

    active = service.list_evidence()
    assert [record["id"] for record in active] == ["EVD-0002"]
    assert len(service.list_evidence(include_all=True)) == 2
    assert [item["id"] for item in service.list_evidence(status="retracted")] == [
        "EVD-0001"
    ]
    assert len(service.list_evidence(classification="inferred")) == 1
    assert len(service.list_evidence(source_type="source-review")) == 1
    assert len(service.list_evidence(confidence="low")) == 1
    assert len(service.list_evidence(issue_id=issue_id, include_all=True)) == 1


def test_list_sorts_newest_capture_then_creation_then_id(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request(title="Older", captured_at="2026-07-26T00:00:00Z"))
    service.create_evidence(_request(title="Newer", captured_at="2026-07-27T00:00:00Z"))
    assert [item["id"] for item in service.list_evidence()] == [
        "EVD-0002",
        "EVD-0001",
    ]


def test_update_metadata_without_changing_confidence(
    framework_repo: Path,
) -> None:
    _service(framework_repo).create_evidence(_request())
    result = _service(framework_repo, later=True).update_evidence(
        "EVD-0001",
        EvidencePatch(
            values={
                "title": "Updated title",
                "claim": "Updated claim.",
                "classification": "inferred",
            }
        ),
    )
    assert result.details["evidence"]["classification"] == "inferred"
    assert result.details["evidence"]["confidence"] == "medium"
    assert result.details["evidence"]["updated_at"] == "2026-07-27T06:00:00Z"


def test_add_and_remove_issue_links_bidirectionally(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    service = _service(framework_repo)
    service.create_evidence(_request())
    linked = service.update_evidence(
        "EVD-0001", EvidencePatch(add_issues=(issue_id, issue_id))
    )
    unlinked = service.update_evidence(
        "EVD-0001", EvidencePatch(remove_issues=(issue_id,))
    )

    assert linked.details["evidence"]["related_issues"] == [issue_id]
    assert unlinked.details["evidence"]["related_issues"] == []
    issue = StateRepository(framework_repo).load_issues()["issues"][0]
    assert issue["evidence_references"] == []
    assert issue["evidence_type"] == "UNKNOWN"


def test_duplicate_link_and_missing_removal_are_warning_noops(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    unlinked_issue_id = _create_issue(framework_repo, "Second issue")
    service = _service(framework_repo)
    service.create_evidence(_request(related_issues=(issue_id,)))
    before = managed_bytes(framework_repo)
    duplicate = service.update_evidence(
        "EVD-0001", EvidencePatch(add_issues=(issue_id,))
    )
    missing = service.update_evidence(
        "EVD-0001", EvidencePatch(remove_issues=(unlinked_issue_id,))
    )

    assert duplicate.details["no_op"] is True
    assert duplicate.warnings
    assert missing.details["no_op"] is True
    assert missing.warnings
    assert managed_bytes(framework_repo) == before


def test_add_and_remove_limitations(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request())
    added = service.update_evidence(
        "EVD-0001",
        EvidencePatch(add_limitations=("One tester.", "One tester.")),
    )
    removed = service.update_evidence(
        "EVD-0001", EvidencePatch(remove_limitations=("One tester.",))
    )
    assert added.details["evidence"]["limitations"] == ["One tester."]
    assert removed.details["evidence"]["limitations"] == []


def test_noop_update_preserves_timestamp_and_reports(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request())
    before = managed_bytes(framework_repo)
    result = _service(framework_repo, later=True).update_evidence(
        "EVD-0001",
        EvidencePatch(values={"title": _request().title}),
    )
    assert result.details["no_op"] is True
    assert result.changed_fields == {}
    assert managed_bytes(framework_repo) == before


def test_update_dry_run_preserves_state_reports_and_issue_links(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    service = _service(framework_repo)
    service.create_evidence(_request())
    before = managed_bytes(framework_repo)
    result = service.update_evidence(
        "EVD-0001",
        EvidencePatch(add_issues=(issue_id,), values={"confidence": "high"}),
        dry_run=True,
    )
    assert result.dry_run
    assert managed_bytes(framework_repo) == before


def test_retract_and_reactivate_evidence_updates_issue_support(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    service = _service(framework_repo)
    service.create_evidence(
        _request(
            classification="observed",
            source_type="runtime",
            related_issues=(issue_id,),
        )
    )
    service.update_evidence("EVD-0001", EvidencePatch(values={"status": "retracted"}))
    issue = StateRepository(framework_repo).load_issues()["issues"][0]
    assert issue["evidence_type"] == "UNKNOWN"

    service.update_evidence("EVD-0001", EvidencePatch(values={"status": "active"}))
    issue = StateRepository(framework_repo).load_issues()["issues"][0]
    assert issue["evidence_type"] == "OBSERVED"


def test_supersession_marks_old_record_and_preserves_links(
    framework_repo: Path,
) -> None:
    issue_id = _create_issue(framework_repo)
    service = _service(framework_repo)
    service.create_evidence(_request(related_issues=(issue_id,)))
    service.create_evidence(
        _request(
            title="Replacement",
            claim="A broader playtest supersedes the first report.",
            related_issues=(issue_id,),
        )
    )
    result = service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-0001"))
    state = StateRepository(framework_repo).load_all()

    assert result.details["evidence"]["supersedes"] == "EVD-0001"
    assert state["evidence"]["evidence"][0]["status"] == "superseded"
    assert state["issues"]["issues"][0]["evidence_references"] == [
        "EVD-0001",
        "EVD-0002",
    ]
    assert [item["id"] for item in service.list_evidence()] == ["EVD-0002"]


def test_self_missing_and_replaced_supersession_fail(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request())
    service.create_evidence(_request(title="Second"))
    with pytest.raises(EvidenceInputError, match="itself"):
        service.update_evidence("EVD-0001", EvidencePatch(supersedes="EVD-0001"))
    with pytest.raises(EvidenceInputError, match="does not exist"):
        service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-9999"))


def test_one_record_cannot_have_multiple_replacements(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    for title in ("Original", "Replacement one", "Replacement two"):
        service.create_evidence(_request(title=title))
    service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-0001"))

    with pytest.raises(EvidenceInputError, match="already superseded by EVD-0002"):
        service.update_evidence("EVD-0003", EvidencePatch(supersedes="EVD-0001"))


def test_circular_supersession_fails_without_write(framework_repo: Path) -> None:
    service = _service(framework_repo)
    for title in ("First", "Second", "Third"):
        service.create_evidence(_request(title=title))
    service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-0001"))
    service.update_evidence("EVD-0003", EvidencePatch(supersedes="EVD-0002"))
    before = managed_bytes(framework_repo)
    with pytest.raises(EvidenceInputError, match="circular"):
        service.update_evidence(
            "EVD-0001",
            EvidencePatch(
                values={"status": "active"},
                supersedes="EVD-0003",
            ),
        )
    assert managed_bytes(framework_repo) == before


def test_superseded_record_cannot_reactivate_while_referenced(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_evidence(_request())
    service.create_evidence(_request(title="Replacement"))
    service.update_evidence("EVD-0002", EvidencePatch(supersedes="EVD-0001"))
    with pytest.raises(EvidenceInputError, match="cannot be active"):
        service.update_evidence("EVD-0001", EvidencePatch(values={"status": "active"}))


def test_report_render_failure_rolls_back_and_cleans_temporaries(
    framework_repo: Path,
) -> None:
    before = managed_bytes(framework_repo)

    def fail(_: object) -> dict[str, str]:
        raise RuntimeError("injected evidence renderer failure")

    with pytest.raises(TransactionError, match="report-render"):
        EvidenceService(
            framework_repo, clock=_clock, report_renderer=fail
        ).create_evidence(_request())
    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))


def test_evidence_transaction_detects_concurrent_change(
    framework_repo: Path,
) -> None:
    before_reports = {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    }
    evidence_path = framework_repo / ".studio" / "state" / "evidence.json"

    def modify_during_render(state: object) -> dict[str, str]:
        evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
        return render_report_contents(state)  # type: ignore[arg-type]

    with pytest.raises(ConcurrentModificationError, match="Reload and retry"):
        EvidenceService(
            framework_repo,
            clock=_clock,
            report_renderer=modify_during_render,
        ).create_evidence(_request())
    assert StateRepository(framework_repo).load_evidence()["evidence"] == []
    assert {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    } == before_reports
