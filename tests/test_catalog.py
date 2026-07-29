from __future__ import annotations

import copy
import json
from pathlib import Path

from practical_game_studio.validation import validate_project

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

NEW_CROSS_PHASE_ALIASES = {
    "/resume",
    "/project-status",
    "/report-issue",
    "/record-evidence",
    "/decision",
    "/milestone-criteria",
}
ORIGINAL_TWELVE_ALIASES = {
    "/start",
    "/clarify",
    "/prototype-plan",
    "/build-prototype",
    "/review-build",
    "/playtest-review",
    "/issue-map",
    "/critical-path",
    "/next-step",
    "/iterate",
    "/vertical-slice",
    "/milestone-review",
}


def _load_catalog() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / ".studio" / "workflow-catalog.json").read_text(
            encoding="utf-8"
        )
    )


def test_catalog_has_seven_phases_and_eighteen_resolved_workflows() -> None:
    catalog = _load_catalog()
    assert [phase["number"] for phase in catalog["phases"]] == list(range(7))
    assert len(catalog["workflows"]) == 18
    assert len({workflow["alias"] for workflow in catalog["workflows"]}) == 18
    for workflow in catalog["workflows"]:
        assert (REPOSITORY_ROOT / workflow["playbook"]).is_file()
        assert all((REPOSITORY_ROOT / role).is_file() for role in workflow["roles"])


def test_original_twelve_aliases_remain_present() -> None:
    catalog = _load_catalog()
    aliases = {workflow["alias"] for workflow in catalog["workflows"]}
    assert ORIGINAL_TWELVE_ALIASES <= aliases


def test_each_new_alias_appears_exactly_once() -> None:
    catalog = _load_catalog()
    aliases = [workflow["alias"] for workflow in catalog["workflows"]]
    for alias in NEW_CROSS_PHASE_ALIASES:
        assert aliases.count(alias) == 1


def test_new_aliases_are_cross_phase_with_no_phase_assignment() -> None:
    catalog = _load_catalog()
    by_alias = {workflow["alias"]: workflow for workflow in catalog["workflows"]}
    for alias in NEW_CROSS_PHASE_ALIASES:
        workflow = by_alias[alias]
        assert workflow["scope"] == "cross-phase"
        assert workflow["phase"] is None
        # Cross-phase utility workflows must not be falsely folded into a
        # single phase's workflow list (for example "intake").
        for phase in catalog["phases"]:
            assert alias not in phase.get("workflows", [])


def test_existing_phase_workflows_are_unaffected_by_the_new_representation() -> None:
    catalog = _load_catalog()
    by_alias = {workflow["alias"]: workflow for workflow in catalog["workflows"]}
    for alias in ORIGINAL_TWELVE_ALIASES:
        workflow = by_alias[alias]
        assert workflow.get("scope", "phase") == "phase"
        assert workflow["phase"] is not None


def test_catalog_version_was_bumped_for_the_cross_phase_representation() -> None:
    catalog = _load_catalog()
    assert catalog["catalog_version"] != "1.0"


def test_cross_phase_workflow_validates_successfully(framework_repo: Path) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert any(
        workflow.get("scope") == "cross-phase" for workflow in catalog["workflows"]
    )

    result = validate_project(framework_repo)

    assert result.ok, "\n".join(result.errors)


def test_cross_phase_workflow_declaring_a_phase_fails_validation(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/resume":
            workflow["phase"] = "intake"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any(
        "/resume is cross-phase and must not declare a phase" in error
        for error in result.errors
    )


def test_invalid_workflow_scope_fails_validation(framework_repo: Path) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/project-status":
            workflow["scope"] = "nonsense"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any(
        "/project-status has invalid scope 'nonsense'" in error
        for error in result.errors
    )


def test_legacy_catalog_without_scope_field_still_validates(
    framework_repo: Path,
) -> None:
    """A catalog written before the cross-phase representation existed (an
    already-bootstrapped project that was never re-bootstrapped) must
    continue to validate exactly as before, without silent migration."""

    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    legacy_workflows = [
        workflow
        for workflow in catalog["workflows"]
        if workflow["alias"] not in NEW_CROSS_PHASE_ALIASES
    ]
    legacy_catalog = copy.deepcopy(catalog)
    legacy_catalog["workflows"] = legacy_workflows
    legacy_catalog["catalog_version"] = "1.0"
    project_path = framework_repo / ".studio" / "state" / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["recommended_next_playbook"] = "/start"
    project_path.write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    catalog_path.write_text(
        json.dumps(legacy_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = validate_project(framework_repo)

    assert result.ok, "\n".join(result.errors)
