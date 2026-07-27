from __future__ import annotations

import copy
from pathlib import Path

import pytest

import practical_game_studio.transaction as transaction_module
from practical_game_studio.state import StateRepository, find_project_root
from practical_game_studio.transaction import (
    ConcurrentModificationError,
    StateTransaction,
    TransactionError,
)
from tests.conftest import managed_bytes


def _updated_project(root: Path, name: str = "Transactional Game") -> dict[str, object]:
    project = StateRepository(root).load_project()
    project["project_name"] = name
    return project


def test_successful_mutation_updates_state_and_reports(framework_repo: Path) -> None:
    with StateTransaction(framework_repo, operation="test") as transaction:
        transaction.set_project(_updated_project(framework_repo))
        result = transaction.commit()

    assert result.success
    assert (
        StateRepository(framework_repo).load_project()["project_name"]
        == "Transactional Game"
    )
    current_report = (
        framework_repo / ".studio" / "reports" / "current-state.md"
    ).read_text(encoding="utf-8")
    assert "Transactional Game" in current_report
    assert result.report_summary["rendered"] == 5


def test_schema_failure_writes_nothing(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    project = _updated_project(framework_repo)
    project["review_mode"] = "reckless"

    with (
        pytest.raises(TransactionError, match="validation"),
        StateTransaction(framework_repo) as transaction,
    ):
        transaction.set_project(project)
        transaction.commit()

    assert managed_bytes(framework_repo) == before


def test_cross_reference_failure_writes_nothing(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)
    critical_path = StateRepository(framework_repo).load_critical_path()
    critical_path["items"][0].update(
        {
            "type": "issue",
            "source_id": "ISS-999",
            "source_key": "issue:ISS-999",
            "manual": False,
        }
    )

    with (
        pytest.raises(TransactionError, match="broken source issue"),
        StateTransaction(framework_repo) as transaction,
    ):
        transaction.set_critical_path(critical_path)
        transaction.commit()

    assert managed_bytes(framework_repo) == before


def test_report_render_failure_writes_nothing(framework_repo: Path) -> None:
    before = managed_bytes(framework_repo)

    def fail_render(state: object) -> dict[str, str]:
        raise RuntimeError("injected renderer failure")

    with (
        pytest.raises(TransactionError, match="report-render"),
        StateTransaction(framework_repo, report_renderer=fail_render) as transaction,
    ):
        transaction.set_project(_updated_project(framework_repo))
        transaction.commit()

    assert managed_bytes(framework_repo) == before


def test_concurrent_modification_aborts_without_overwrite(framework_repo: Path) -> None:
    project_path = framework_repo / ".studio" / "state" / "project.json"
    reports_before = {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    }

    with (
        pytest.raises(ConcurrentModificationError, match="Reload and retry"),
        StateTransaction(framework_repo) as transaction,
    ):
        transaction.set_project(_updated_project(framework_repo))
        project_path.write_bytes(project_path.read_bytes() + b" ")
        external_content = project_path.read_bytes()
        transaction.commit()

    assert project_path.read_bytes() == external_content
    assert {
        path.name: path.read_bytes()
        for path in (framework_repo / ".studio" / "reports").glob("*.md")
    } == reports_before


def test_replace_failure_rolls_back_and_cleans_temporaries(
    framework_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = managed_bytes(framework_repo)
    real_replace = transaction_module.os.replace
    calls = 0

    def fail_second_replace(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replace failure")
        real_replace(source, target)

    monkeypatch.setattr(transaction_module.os, "replace", fail_second_replace)

    with (
        pytest.raises(TransactionError, match="rolled back"),
        StateTransaction(framework_repo) as transaction,
    ):
        transaction.set_project(_updated_project(framework_repo))
        transaction.commit()

    assert managed_bytes(framework_repo) == before
    assert not list(framework_repo.rglob(".*.pgs-*.tmp"))


def test_transient_windows_permission_error_is_retried(
    framework_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = transaction_module.os.replace
    calls = 0

    def fail_once(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("injected transient scanner lock")
        real_replace(source, target)

    monkeypatch.setattr(transaction_module.os, "replace", fail_once)

    with StateTransaction(framework_repo) as transaction:
        transaction.set_project(_updated_project(framework_repo))
        result = transaction.commit()

    assert result.success
    assert calls > 1
    assert (
        StateRepository(framework_repo).load_project()["project_name"]
        == "Transactional Game"
    )


def test_loaded_state_is_isolated_from_repository(framework_repo: Path) -> None:
    repository = StateRepository(framework_repo)
    first = repository.load_all()
    untouched = copy.deepcopy(first)
    first["project"]["project_name"] = "Mutated in memory"

    assert repository.load_all() == untouched


def test_state_repository_errors_include_path(framework_repo: Path) -> None:
    project_path = framework_repo / ".studio" / "state" / "project.json"
    project_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="project.json"):
        StateRepository(framework_repo).load_project()


def test_result_is_structured_for_future_json_output(framework_repo: Path) -> None:
    with StateTransaction(framework_repo, dry_run=True) as transaction:
        transaction.set_project(_updated_project(framework_repo))
        result = transaction.commit(
            changed_fields={
                "project_name": {"old": "Untitled Game", "new": "Transactional Game"}
            }
        )

    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["operation"] == "state-mutation"
    assert payload["dry_run"] is True
    assert payload["validation_summary"]["relationships"] == "passed"


def test_root_discovery_supports_explicit_and_parent_search(
    framework_repo: Path,
) -> None:
    nested = framework_repo / "game" / "scripts"
    nested.mkdir(parents=True)

    assert find_project_root(explicit=framework_repo) == framework_repo.resolve()
    assert find_project_root(start=nested) == framework_repo.resolve()
