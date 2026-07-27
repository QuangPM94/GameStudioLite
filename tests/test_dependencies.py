from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from practical_game_studio.critical_path import (
    CriticalPathService,
    PathCalculationRequest,
)
from practical_game_studio.dependencies import (
    DependencyCreateRequest,
    DependencyCycleError,
    DependencyInputError,
    DependencyPatch,
    DependencyService,
)
from practical_game_studio.issues import IssueCreateRequest, IssueService
from practical_game_studio.state import StateRepository
from practical_game_studio.transaction import TransactionError
from tests.conftest import managed_bytes

NOW = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)


def _issue(root: Path, title: str, severity: str = "blocker") -> str:
    return (
        IssueService(root)
        .create_issue(
            IssueCreateRequest(
                title=title,
                severity=severity,
                description=f"{title} description.",
                milestone_impact=f"{title} gates the milestone.",
                recommended_action=f"Complete {title}.",
            )
        )
        .details["issue"]["id"]
    )


def _service(root: Path) -> DependencyService:
    return DependencyService(root, clock=lambda: NOW)


def test_create_allocates_deterministic_id_and_defaults(framework_repo: Path) -> None:
    prerequisite = _issue(framework_repo, "Prerequisite")
    dependent = _issue(framework_repo, "Dependent")

    result = _service(framework_repo).create_dependency(
        DependencyCreateRequest(
            prerequisite=prerequisite,
            dependent=dependent,
            reason="Dependent work requires the prerequisite.",
        )
    )

    record = result.details["dependency"]
    assert record["id"] == "DEP-0001"
    assert record["relationship"] == "requires"
    assert record["scope"] == "current-milestone"
    assert record["status"] == "active"
    assert result.details["path_stale"] is True


def test_dry_run_does_not_consume_id_or_write(framework_repo: Path) -> None:
    prerequisite = _issue(framework_repo, "Prerequisite")
    dependent = _issue(framework_repo, "Dependent")
    before = managed_bytes(framework_repo)
    request = DependencyCreateRequest(
        prerequisite=prerequisite,
        dependent=dependent,
        reason="Ordering is required.",
    )

    preview = _service(framework_repo).create_dependency(request, dry_run=True)
    assert managed_bytes(framework_repo) == before
    committed = _service(framework_repo).create_dependency(request)

    assert preview.details["dependency"]["id"] == "DEP-0001"
    assert committed.details["dependency"]["id"] == "DEP-0001"


def test_missing_self_and_duplicate_edges_fail(framework_repo: Path) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    with pytest.raises(DependencyInputError, match="depend on itself"):
        service.create_dependency(DependencyCreateRequest(first, first, "Invalid."))
    with pytest.raises(DependencyInputError, match="does not exist"):
        service.create_dependency(
            DependencyCreateRequest("ISS-999", second, "Missing.")
        )
    service.create_dependency(DependencyCreateRequest(first, second, "Valid ordering."))
    with pytest.raises(DependencyInputError, match="already represents"):
        service.create_dependency(DependencyCreateRequest(first, second, "Duplicate."))


def test_cycle_failure_preserves_registry(framework_repo: Path) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    service.create_dependency(
        DependencyCreateRequest(first, second, "Second requires first.")
    )
    before = managed_bytes(framework_repo)

    with pytest.raises(DependencyCycleError, match=r"ISS-0001.*ISS-0002"):
        service.create_dependency(
            DependencyCreateRequest(second, first, "First requires second.")
        )

    assert managed_bytes(framework_repo) == before


def test_deactivate_and_identical_add_reactivate_history(
    framework_repo: Path,
) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    created = service.create_dependency(
        DependencyCreateRequest(first, second, "Initial reason.")
    )
    service.deactivate_dependency(
        created.details["dependency"]["id"], "No longer used."
    )

    reactivated = service.create_dependency(
        DependencyCreateRequest(first, second, "Required again.", scope="project")
    )

    record = reactivated.details["dependency"]
    assert record["id"] == "DEP-0001"
    assert record["status"] == "active"
    assert record["deactivated_at"] is None
    assert reactivated.details["reactivated"] is True


def test_deactivate_dependency_used_by_current_path_marks_snapshot_stale(
    framework_repo: Path,
) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    service.create_dependency(
        DependencyCreateRequest(first, second, "Second requires first.")
    )
    CriticalPathService(framework_repo, clock=lambda: NOW).apply_path(
        PathCalculationRequest()
    )

    result = service.deactivate_dependency(
        "DEP-0001", "The ordering requirement was removed."
    )

    assert result.details["dependency"]["status"] == "inactive"
    assert result.details["path_stale"] is True
    assert (
        StateRepository(framework_repo).load_critical_path()["freshness"]["status"]
        == "stale"
    )


def test_new_dependency_can_stale_the_current_recommended_item(
    framework_repo: Path,
) -> None:
    prerequisite = _issue(framework_repo, "Required first")
    CriticalPathService(framework_repo, clock=lambda: NOW).apply_path(
        PathCalculationRequest()
    )

    result = _service(framework_repo).create_dependency(
        DependencyCreateRequest(
            prerequisite,
            "MANUAL:guided-intake",
            "Guided intake now requires the blocker first.",
        )
    )

    assert result.details["path_stale"] is True
    assert (
        StateRepository(framework_repo).load_critical_path()["freshness"]["status"]
        == "stale"
    )


def test_recalculation_clears_stale_state_when_reactivated_graph_is_unchanged(
    framework_repo: Path,
) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    service.create_dependency(
        DependencyCreateRequest(first, second, "Second requires first.")
    )
    path_service = CriticalPathService(framework_repo, clock=lambda: NOW)
    path_service.apply_path(PathCalculationRequest())
    service.deactivate_dependency("DEP-0001", "Temporarily removed.")
    service.reactivate_dependency("DEP-0001")

    recalculated = path_service.apply_path(PathCalculationRequest())

    assert recalculated.details["no_op"] is False
    assert StateRepository(framework_repo).load_critical_path()["freshness"] == {
        "status": "current",
        "reasons": [],
    }
    assert path_service.check_freshness().status == "current"


def test_update_list_filters_and_satisfaction(framework_repo: Path) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    service.create_dependency(DependencyCreateRequest(first, second, "Initial."))

    update = service.update_dependency(
        "DEP-0001", DependencyPatch(reason="Clarified reason.", scope="project")
    )
    records = service.list_dependencies(source=second, scope="project")

    assert update.details["dependency"]["id"] == "DEP-0001"
    assert records[0]["reason"] == "Clarified reason."
    assert records[0]["prerequisite_satisfied"] is False
    assert service.find_upstream(second) == (first,)
    assert service.find_downstream(first) == (second,)


def test_explicit_dependency_orders_path_and_records_origin(
    framework_repo: Path,
) -> None:
    prerequisite = _issue(framework_repo, "Lower priority", "major")
    dependent = _issue(framework_repo, "Hard blocker", "blocker")
    _service(framework_repo).create_dependency(
        DependencyCreateRequest(
            prerequisite,
            dependent,
            "The blocker cannot be completed first.",
        )
    )

    calculated = CriticalPathService(framework_repo, clock=lambda: NOW).calculate_path(
        PathCalculationRequest()
    )
    items = list(calculated.active_items)
    keys = [item.source_key for item in items]
    dependent_item = next(item for item in items if item.source_id == dependent)

    assert keys.index(f"issue:{prerequisite}") < keys.index(f"issue:{dependent}")
    assert dependent_item.dependency_origins[0]["dependency_id"] == "DEP-0001"
    assert dependent_item.dependency_origins[0]["origin"] == "explicit"


def test_manual_endpoint_must_exist(framework_repo: Path) -> None:
    issue = _issue(framework_repo, "Dependent")
    result = _service(framework_repo).create_dependency(
        DependencyCreateRequest(
            "MANUAL:guided-intake",
            issue,
            "Intake must finish first.",
        )
    )
    assert result.details["dependency"]["prerequisite"] == "MANUAL:guided-intake"
    with pytest.raises(DependencyInputError, match="does not exist"):
        _service(framework_repo).create_dependency(
            DependencyCreateRequest(
                "MANUAL:missing-action", issue, "Missing manual action."
            )
        )


def test_noop_update_preserves_timestamp_and_reports(framework_repo: Path) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    service = _service(framework_repo)
    service.create_dependency(DependencyCreateRequest(first, second, "Stable reason."))
    before = managed_bytes(framework_repo)

    result = service.update_dependency(
        "DEP-0001", DependencyPatch(reason="Stable reason.")
    )

    assert result.details["no_op"] is True
    assert managed_bytes(framework_repo) == before
    assert (
        StateRepository(framework_repo).load_dependencies()["dependencies"][0][
            "updated_at"
        ]
        == "2026-07-28T00:00:00Z"
    )


def test_report_render_failure_writes_nothing(framework_repo: Path) -> None:
    first = _issue(framework_repo, "First")
    second = _issue(framework_repo, "Second")
    before = managed_bytes(framework_repo)

    def fail_render(_: object) -> dict[str, str]:
        raise RuntimeError("injected dependency renderer failure")

    with pytest.raises(TransactionError, match="report-render"):
        DependencyService(
            framework_repo,
            clock=lambda: NOW,
            report_renderer=fail_render,
        ).create_dependency(
            DependencyCreateRequest(first, second, "Ordering is required.")
        )

    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))
