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


def test_shipped_catalog_references_workflows_by_id_not_legacy_alias() -> None:
    """The shipped catalog itself has migrated phase membership and "next"
    relationships from legacy slash aliases to internal workflow ids."""

    catalog = _load_catalog()
    known_ids = {workflow["id"] for workflow in catalog["workflows"]}
    for phase in catalog["phases"]:
        for reference in phase["workflows"]:
            assert not reference.startswith("/"), reference
            assert reference in known_ids
    for workflow in catalog["workflows"]:
        for reference in workflow["next"]:
            assert not reference.startswith("/"), reference
            assert reference in known_ids


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


def test_legacy_catalog_without_id_or_canonical_fields_still_validates(
    framework_repo: Path,
) -> None:
    """A catalog written before GS:<workflow> canonical invocations existed
    has no "id"/"canonical" fields and references workflows by their legacy
    slash alias everywhere (phase membership, "next" relationships). It must
    continue to validate exactly as before, without silent migration."""

    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    id_to_alias = {
        workflow["id"]: workflow["alias"] for workflow in catalog["workflows"]
    }
    for workflow in catalog["workflows"]:
        workflow.pop("id", None)
        workflow.pop("canonical", None)
        workflow["next"] = [id_to_alias[ref] for ref in workflow.get("next", [])]
    for phase in catalog["phases"]:
        phase["workflows"] = [id_to_alias[ref] for ref in phase.get("workflows", [])]
    catalog["catalog_version"] = "1.1"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert result.ok, "\n".join(result.errors)


def test_catalog_version_1_2_requires_id_field(framework_repo: Path) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["catalog_version"] >= "1.2"
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            del workflow["id"]
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any(
        "/clarify is missing the required 'id' field" in error
        for error in result.errors
    )


def test_catalog_version_1_2_requires_canonical_field(framework_repo: Path) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["catalog_version"] >= "1.2"
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            del workflow["canonical"]
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any(
        "/clarify is missing the required 'canonical' field" in error
        for error in result.errors
    )


def test_catalog_version_below_1_2_does_not_require_id_or_canonical(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            del workflow["id"]
            del workflow["canonical"]
    catalog["catalog_version"] = "1.1"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert not any("is missing the required" in error for error in result.errors)


def test_phase_and_next_references_accept_either_alias_or_id_form(
    framework_repo: Path,
) -> None:
    """The migration from legacy slash-alias references to internal-id
    references in "workflows"/"next" lists is backward compatible: a catalog
    may mix both forms and still validate, which is what lets an existing
    catalog migrate incrementally instead of all at once."""

    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    # The shipped catalog already references "next"/"workflows" by id; flip a
    # couple of entries back to the legacy alias form to prove both work.
    catalog["phases"][0]["workflows"] = ["/start"]
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/start":
            workflow["next"] = ["/clarify", "prototype-plan", "/review-build"]
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert result.ok, "\n".join(result.errors)


def test_every_canonical_invocation_is_unique_and_disjoint_from_legacy_aliases() -> (
    None
):
    catalog = _load_catalog()
    canonicals = [workflow["canonical"] for workflow in catalog["workflows"]]
    aliases = {workflow["alias"] for workflow in catalog["workflows"]}

    assert len(canonicals) == len(set(canonicals))
    assert set(canonicals).isdisjoint(aliases)
    for canonical in canonicals:
        assert canonical.startswith("GS:")
        assert not canonical.startswith(("/", "\\", "@", "!"))


def test_canonical_invocation_id_and_alias_stay_consistent() -> None:
    catalog = _load_catalog()
    for workflow in catalog["workflows"]:
        assert workflow["canonical"] == f"GS:{workflow['id']}"
        assert workflow["alias"] == f"/{workflow['id']}"


def test_duplicate_canonical_invocation_fails_validation(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/next-step":
            workflow["canonical"] = "GS:critical-path"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any("duplicate canonical invocation" in error for error in result.errors)


def test_malformed_canonical_invocation_fails_validation(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            workflow["canonical"] = "GS:Clarify"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any("malformed canonical invocation" in error for error in result.errors)


def test_slash_prefixed_canonical_invocation_fails_validation(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            workflow["canonical"] = "/GS:clarify"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any(
        "must not start with a special character" in error for error in result.errors
    )


def test_canonical_invocation_conflicting_with_a_legacy_alias_fails_validation(
    framework_repo: Path,
) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            workflow["canonical"] = "/critical-path"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any("conflicts with a legacy alias" in error for error in result.errors)


def test_mismatched_workflow_id_fails_validation(framework_repo: Path) -> None:
    catalog_path = framework_repo / ".studio" / "workflow-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for workflow in catalog["workflows"]:
        if workflow["alias"] == "/clarify":
            workflow["id"] = "clarification"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = validate_project(framework_repo)

    assert any("does not match alias" in error for error in result.errors)
