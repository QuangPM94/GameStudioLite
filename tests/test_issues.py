from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.issues import (
    IssueCreateRequest,
    IssueInputError,
    IssuePatch,
    IssueService,
    allocate_issue_id,
)
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import (
    ConcurrentModificationError,
    StateTransaction,
    TransactionError,
)
from tests.conftest import managed_bytes

NOW = datetime(2026, 7, 27, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 7, 27, 4, 5, 6, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _request(**changes: object) -> IssueCreateRequest:
    values: dict[str, object] = {
        "title": "Player cannot identify the delivery room",
        "severity": "critical",
        "player_impact": "The player stops progressing in the corridor.",
    }
    values.update(changes)
    return IssueCreateRequest(**values)  # type: ignore[arg-type]


def _service(root: Path, *, later: bool = False) -> IssueService:
    return IssueService(root, clock=(lambda: LATER) if later else _clock)


def test_create_minimum_issue_uses_safe_defaults(framework_repo: Path) -> None:
    result = _service(framework_repo).create_issue(_request())
    issue = StateRepository(framework_repo).load_issues()["issues"][0]

    assert result.success
    assert issue["id"] == "ISS-0001"
    assert issue["status"] == "open"
    assert issue["category"] == "other"
    assert issue["description"] == "Not yet described."
    assert issue["effort"] == "unknown"
    assert issue["owner"] == "unassigned"
    assert issue["evidence_type"] == "UNKNOWN"
    assert issue["created_at"] == "2026-07-27T03:04:05Z"


def test_create_fully_populated_issue_normalizes_values(
    framework_repo: Path,
) -> None:
    _service(framework_repo).create_issue(
        _request(
            title="  Launch fails  ",
            severity=" BLOCKER ",
            description="  Build exits on launch.  ",
            category=" BUILD ",
            milestone_impact="No runnable prototype.",
            recommended_action="Fix startup scene.",
            effort=" SMALL ",
            owner=" DEVELOPER ",
            user_decision_required=True,
        )
    )
    issue = StateRepository(framework_repo).load_issues()["issues"][0]

    assert issue["title"] == "Launch fails"
    assert issue["severity"] == "blocker"
    assert issue["category"] == "build"
    assert issue["owner"] == "developer"
    assert issue["user_decision_required"] is True


def test_id_allocation_uses_highest_historical_id() -> None:
    assert allocate_issue_id([{"id": "ISS-0009"}, {"id": "ISS-0042"}]) == "ISS-0043"


def test_resolved_historical_issue_still_advances_id(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request())
    _service(framework_repo, later=True).update_issue(
        "ISS-0001",
        IssuePatch(values={"status": "resolved", "resolution": "Fixed signage."}),
    )
    result = _service(framework_repo).create_issue(
        _request(title="Second issue", severity="minor")
    )

    assert result.details["issue"]["id"] == "ISS-0002"


@pytest.mark.parametrize(
    ("issue_request", "message"),
    [
        (_request(title=" "), "title cannot be empty"),
        (_request(severity="urgent"), "invalid severity"),
        (
            _request(description=None, player_impact=None, milestone_impact=None),
            "provide at least one",
        ),
    ],
)
def test_invalid_creation_writes_nothing(
    framework_repo: Path, issue_request: IssueCreateRequest, message: str
) -> None:
    before = managed_bytes(framework_repo)
    with pytest.raises(IssueInputError, match=message):
        _service(framework_repo).create_issue(issue_request)
    assert managed_bytes(framework_repo) == before


def test_dry_run_does_not_write_or_consume_id(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    preview = _service(framework_repo).create_issue(_request(), dry_run=True)
    real = _service(framework_repo).create_issue(_request())

    assert preview.details["issue"]["id"] == "ISS-0001"
    assert preview.validation_summary["relationships"] == "passed"
    assert real.details["issue"]["id"] == "ISS-0001"
    assert managed_bytes(framework_repo) != before


def test_dry_run_alone_preserves_all_managed_bytes(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    _service(framework_repo).create_issue(_request(), dry_run=True)
    assert managed_bytes(framework_repo) == before


def test_list_defaults_filters_and_stable_priority(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request(title="Major", severity="major"))
    service.create_issue(_request(title="Blocker", severity="blocker"))
    service.create_issue(_request(title="Critical", severity="critical"))
    _service(framework_repo, later=True).update_issue(
        "ISS-0001",
        IssuePatch(
            values={"status": "accepted", "resolution": "Accepted for prototype."}
        ),
    )

    active = service.list_issues()
    assert [issue["id"] for issue in active] == ["ISS-0002", "ISS-0003"]
    assert len(service.list_issues(include_all=True)) == 3
    assert [item["id"] for item in service.list_issues(severity="critical")] == [
        "ISS-0003"
    ]


def test_list_filters_owner_path_and_user_decision(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(
        _request(
            owner="producer",
            category="clarity",
            on_critical_path=True,
            user_decision_required=True,
        )
    )
    assert len(service.list_issues(owner="producer")) == 1
    assert len(service.list_issues(category="clarity")) == 1
    assert len(service.list_issues(critical_path=True)) == 1
    assert len(service.list_issues(user_decision_required=True)) == 1
    assert len(service.list_issues(status="open")) == 1


def test_list_same_severity_prioritizes_path_then_blocked_then_oldest(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_issue(_request(title="Ordinary", severity="major"))
    service.create_issue(
        _request(title="Path", severity="major", on_critical_path=True)
    )
    service.create_issue(_request(title="Blocked", severity="major"))
    service.update_issue("ISS-0003", IssuePatch(values={"status": "blocked"}))

    assert [item["id"] for item in service.list_issues()] == [
        "ISS-0002",
        "ISS-0003",
        "ISS-0001",
    ]


def test_update_one_and_several_fields(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    result = _service(framework_repo, later=True).update_issue(
        "ISS-0001",
        IssuePatch(
            values={
                "title": "Visible-room problem",
                "severity": "major",
                "owner": "developer",
            }
        ),
    )

    assert set(result.changed_fields) == {"title", "severity", "owner", "updated_at"}
    assert result.details["issue"]["updated_at"] == "2026-07-27T04:05:06Z"


def test_noop_update_preserves_timestamp_and_reports(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request())
    before = managed_bytes(framework_repo)
    result = _service(framework_repo, later=True).update_issue(
        "ISS-0001", IssuePatch(values={"title": _request().title})
    )

    assert result.details["no_op"] is True
    assert result.changed_fields == {}
    assert managed_bytes(framework_repo) == before


def test_update_dry_run_preserves_all_managed_bytes(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request())
    before = managed_bytes(framework_repo)
    result = _service(framework_repo, later=True).update_issue(
        "ISS-0001",
        IssuePatch(values={"status": "in-progress", "owner": "developer"}),
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.validation_summary["relationships"] == "passed"
    assert result.details["issue"]["status"] == "in-progress"
    assert managed_bytes(framework_repo) == before


@pytest.mark.parametrize("status", ["resolved", "accepted", "wont-fix"])
def test_terminal_status_requires_resolution(framework_repo: Path, status: str) -> None:
    _service(framework_repo).create_issue(_request())
    with pytest.raises(IssueInputError, match="resolution is required"):
        _service(framework_repo).update_issue(
            "ISS-0001", IssuePatch(values={"status": status})
        )


def test_resolve_and_reopen_preserves_resolution(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    _service(framework_repo, later=True).update_issue(
        "ISS-0001",
        IssuePatch(values={"status": "resolved", "resolution": "Added signage."}),
    )
    result = _service(framework_repo).update_issue(
        "ISS-0001", IssuePatch(values={"status": "open"})
    )

    assert result.details["issue"]["status"] == "open"
    assert result.details["issue"]["resolution"] == "Added signage."


def test_resolution_cannot_be_cleared_with_empty_text(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    with pytest.raises(IssueInputError, match="resolution cannot be empty"):
        _service(framework_repo).update_issue(
            "ISS-0001", IssuePatch(values={"resolution": "  "})
        )


def test_invalid_transition_fails(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    _service(framework_repo).update_issue(
        "ISS-0001",
        IssuePatch(values={"status": "resolved", "resolution": "Fixed."}),
    )
    with pytest.raises(IssueInputError, match="cannot transition"):
        _service(framework_repo).update_issue(
            "ISS-0001", IssuePatch(values={"status": "accepted"})
        )


def test_unknown_status_fails_before_write(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    before = managed_bytes(framework_repo)
    with pytest.raises(IssueInputError, match="invalid status"):
        _service(framework_repo).update_issue(
            "ISS-0001", IssuePatch(values={"status": "done"})
        )
    assert managed_bytes(framework_repo) == before


def test_dependency_and_blocked_issue_updates(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request())
    service.create_issue(_request(title="Second", severity="major"))
    added = service.update_issue(
        "ISS-0001",
        IssuePatch(
            add_dependencies=("ISS-0002", "ISS-0002"),
            add_blocked_issues=("ISS-0002",),
        ),
    )
    removed = service.update_issue(
        "ISS-0001",
        IssuePatch(
            remove_dependencies=("ISS-0002",),
            remove_blocked_issues=("ISS-0002",),
        ),
    )

    assert added.details["issue"]["dependencies"] == ["ISS-0002"]
    assert removed.details["issue"]["dependencies"] == []
    assert removed.details["issue"]["issues_blocked"] == []


@pytest.mark.parametrize(
    "patch",
    [
        IssuePatch(add_dependencies=("ISS-0001",)),
        IssuePatch(add_blocked_issues=("ISS-0001",)),
        IssuePatch(add_dependencies=("ISS-9999",)),
    ],
)
def test_invalid_issue_relationship_fails(
    framework_repo: Path, patch: IssuePatch
) -> None:
    _service(framework_repo).create_issue(_request())
    with pytest.raises(IssueInputError):
        _service(framework_repo).update_issue("ISS-0001", patch)


def _seed_evidence(root: Path) -> None:
    with StateTransaction(root) as transaction:
        state = transaction.state
        state["evidence"]["evidence"].append(
            {
                "id": "EVD-0001",
                "title": "Issue reproduced",
                "claim": "The issue reproduced in the test log.",
                "classification": "observed",
                "source_type": "test-output",
                "source": "test log",
                "description": "The issue reproduced.",
                "related_hypothesis": None,
                "related_issues": [],
                "confidence": "high",
                "limitations": [],
                "captured_at": "2026-07-27T00:00:00Z",
                "created_at": "2026-07-27T00:00:00Z",
                "updated_at": "2026-07-27T00:00:00Z",
                "status": "active",
                "supersedes": None,
            }
        )
        transaction.set_evidence(state["evidence"])
        transaction.commit()


def test_attach_and_remove_existing_evidence(framework_repo: Path) -> None:
    _seed_evidence(framework_repo)
    service = _service(framework_repo)
    service.create_issue(_request())
    attached = service.update_issue(
        "ISS-0001", IssuePatch(add_evidence=("EVD-0001", "EVD-0001"))
    )
    linked_evidence = StateRepository(framework_repo).load_evidence()["evidence"][0]
    removed = service.update_issue(
        "ISS-0001", IssuePatch(remove_evidence=("EVD-0001",))
    )

    assert attached.details["issue"]["evidence_references"] == ["EVD-0001"]
    assert attached.details["issue"]["evidence_type"] == "OBSERVED"
    assert linked_evidence["related_issues"] == ["ISS-0001"]
    assert removed.details["issue"]["evidence_type"] == "UNKNOWN"
    evidence = StateRepository(framework_repo).load_evidence()["evidence"][0]
    assert evidence["related_issues"] == []


def test_missing_evidence_fails_without_write(framework_repo: Path) -> None:
    _service(framework_repo).create_issue(_request())
    before = managed_bytes(framework_repo)
    with pytest.raises(IssueInputError, match="does not exist"):
        _service(framework_repo).update_issue(
            "ISS-0001", IssuePatch(add_evidence=("EVD-999",))
        )
    assert managed_bytes(framework_repo) == before


def test_critical_path_membership_is_transactionally_consistent(
    framework_repo: Path,
) -> None:
    service = _service(framework_repo)
    service.create_issue(_request(on_critical_path=True))
    state = StateRepository(framework_repo).load_all()
    assert state["issues"]["issues"][0]["on_critical_path"] is True
    assert state["critical_path"]["items"][-1]["source_id"] == "ISS-0001"

    service.update_issue("ISS-0001", IssuePatch(critical_path=False))
    state = StateRepository(framework_repo).load_all()
    assert state["issues"]["issues"][0]["on_critical_path"] is False
    assert all(
        item["source_id"] != "ISS-0001" for item in state["critical_path"]["items"]
    )
    assert state["critical_path"]["history"][-1]["source_id"] == "ISS-0001"


def test_terminal_path_issue_moves_to_completed_history(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request(on_critical_path=True))
    result = service.update_issue(
        "ISS-0001",
        IssuePatch(values={"status": "resolved", "resolution": "Fixed."}),
    )
    assert result.details["issue"]["status"] == "resolved"
    path = StateRepository(framework_repo).load_critical_path()
    assert path["history"][-1]["status"] == "completed"


def test_deferred_path_issue_moves_to_removed_history(framework_repo: Path) -> None:
    service = _service(framework_repo)
    service.create_issue(_request(on_critical_path=True))
    service.update_issue("ISS-0001", IssuePatch(values={"status": "deferred"}))
    path = StateRepository(framework_repo).load_critical_path()
    assert path["history"][-1]["status"] == "removed"


def test_report_render_failure_rolls_back_issue(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)

    def fail(_: object) -> dict[str, str]:
        raise RuntimeError("injected issue report failure")

    with pytest.raises(TransactionError, match="report-render"):
        IssueService(framework_repo, clock=_clock, report_renderer=fail).create_issue(
            _request()
        )
    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))


def test_issue_transaction_detects_concurrent_change(framework_repo: Path) -> None:
    before_reports = {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    }
    issue_path = framework_repo / ".studio" / "state" / "issues.json"

    from practical_game_studio.reporting import render_report_contents

    def modify_during_render(state: object) -> dict[str, str]:
        issue_path.write_bytes(issue_path.read_bytes() + b" ")
        return render_report_contents(state)  # type: ignore[arg-type]

    with pytest.raises(ConcurrentModificationError, match="Reload and retry"):
        IssueService(
            framework_repo, clock=_clock, report_renderer=modify_during_render
        ).create_issue(_request())
    assert StateRepository(framework_repo).load_issues()["issues"] == []
    assert {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    } == before_reports
