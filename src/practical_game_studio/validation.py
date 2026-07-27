"""Framework, JSON Schema, reference, and state relationship validation."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from .models import ValidationResult
from .state import STATE_FILES, CanonicalState, load_json

REQUIRED_ROLE_SECTIONS = (
    "Purpose",
    "Responsibilities",
    "Inputs",
    "Outputs",
    "Decision authority",
    "Escalation conditions",
    "Evidence rules",
    "Anti-patterns",
)
REQUIRED_PLAYBOOK_SECTIONS = (
    "Purpose",
    "When to use",
    "Required inputs",
    "Optional inputs",
    "Files to read",
    "State changes",
    "Execution procedure",
    "User decision points",
    "Outputs",
    "Validation",
    "Completion criteria",
    "Next recommended workflows",
    "Failure and blocker behavior",
    "Direction Summary",
)
GENERATED_WARNING = "<!-- Generated file. Do not edit manually. -->"
PHASES = {
    "intake",
    "clarify",
    "prototype-plan",
    "prototype-build",
    "evaluate",
    "iterate",
    "vertical-slice-decision",
    "vertical-slice",
    "production",
}
SCHEMA_FILES = {
    "project": "project.schema.json",
    "issues": "issues.schema.json",
    "decisions": "decisions.schema.json",
    "critical_path": "critical-path.schema.json",
    "evidence": "evidence.schema.json",
    "milestone": "milestone.schema.json",
}
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "docs/state-mutation-safety.md",
    ".studio/config.json",
    ".studio/workflow-catalog.json",
    *(
        f".studio/roles/{name}.md"
        for name in (
            "producer",
            "game-designer",
            "technical-lead",
            "developer",
            "player-advocate",
        )
    ),
    *(
        f".studio/playbooks/{name}.md"
        for name in (
            "start",
            "clarify",
            "prototype-plan",
            "build-prototype",
            "review-build",
            "playtest-review",
            "issue-map",
            "critical-path",
            "next-step",
            "iterate",
            "vertical-slice",
            "milestone-review",
        )
    ),
    *(
        f".studio/schemas/{name}.schema.json"
        for name in (
            "project",
            "issues",
            "decisions",
            "critical-path",
            "evidence",
            "milestone",
        )
    ),
    *(f".studio/state/{filename}" for filename in STATE_FILES.values()),
    *(
        f".studio/templates/{name}.md"
        for name in (
            "game-brief",
            "prototype-scope",
            "prototype-success-criteria",
            "player-review",
            "direction-report",
            "milestone-review",
            "assumption-log",
            "optional-adr",
        )
    ),
    *(
        f".studio/reports/{name}.md"
        for name in (
            "current-state",
            "direction-report",
            "open-issues",
            "critical-path",
            "milestone-review",
        )
    ),
    "src/practical_game_studio/__init__.py",
    "src/practical_game_studio/cli.py",
    "src/practical_game_studio/decisions.py",
    "src/practical_game_studio/validation.py",
    "src/practical_game_studio/reporting.py",
    "src/practical_game_studio/state.py",
    "src/practical_game_studio/models.py",
    "docs/decision-management.md",
    "tests/test_decisions.py",
    "tests/test_decision_cli.py",
    "src/practical_game_studio/transaction.py",
    "src/practical_game_studio/initialization.py",
    "src/practical_game_studio/issues.py",
    "src/practical_game_studio/evidence.py",
    "tests/test_validation.py",
    "tests/test_reporting.py",
    "tests/test_catalog.py",
    "tests/test_initialization.py",
    "tests/test_transaction.py",
    "tests/test_cli.py",
    "tests/test_issues.py",
    "tests/test_issue_cli.py",
    "tests/test_evidence.py",
    "tests/test_evidence_cli.py",
    "tests/conftest.py",
    "tests/__init__.py",
    "tests/fixtures/README.md",
    "docs/issue-management.md",
    "docs/evidence-management.md",
    "examples/delivery-horror/README.md",
    "examples/delivery-horror/sample-game-brief.md",
    "examples/delivery-horror/sample-evaluation.md",
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _load_json_files(root: Path, result: ValidationResult) -> dict[Path, Any]:
    loaded: dict[Path, Any] = {}
    for path in sorted((root / ".studio").rglob("*.json")):
        try:
            loaded[path] = load_json(path)
        except (OSError, ValueError) as exc:
            result.add(str(exc))
    return loaded


def _check_sections(
    path: Path, headings: Iterable[str], result: ValidationResult
) -> None:
    text = path.read_text(encoding="utf-8")
    for heading in headings:
        if f"## {heading}" not in text:
            result.add(f"{path.as_posix()}: missing required section '## {heading}'")


def _validate_documents(root: Path, result: ValidationResult) -> None:
    role_paths = sorted((root / ".studio" / "roles").glob("*.md"))
    playbook_paths = sorted((root / ".studio" / "playbooks").glob("*.md"))
    if len(role_paths) != 5:
        result.add(
            f".studio/roles: expected exactly 5 role files, found {len(role_paths)}"
        )
    if len(playbook_paths) != 12:
        result.add(
            f".studio/playbooks: expected exactly 12 playbook files, found {len(playbook_paths)}"
        )
    for path in role_paths:
        _check_sections(path, REQUIRED_ROLE_SECTIONS, result)
    for path in playbook_paths:
        _check_sections(path, REQUIRED_PLAYBOOK_SECTIONS, result)
        text = path.read_text(encoding="utf-8")
        for reference in re.findall(r"`((?:\.studio/|AGENTS\.md)[^`\n ]+)", text):
            if not (root / reference).exists():
                result.add(
                    f"{_relative(root, path)}: broken internal reference '{reference}'"
                )
    for path in sorted((root / ".studio" / "reports").glob("*.md")):
        if not path.read_text(encoding="utf-8").startswith(GENERATED_WARNING):
            result.add(f"{_relative(root, path)}: missing generated-file warning")


def _validate_schemas(
    root: Path, loaded: dict[Path, Any], result: ValidationResult
) -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for state_name in STATE_FILES:
        schema_path = root / ".studio" / "schemas" / SCHEMA_FILES[state_name]
        schema = loaded.get(schema_path)
        if schema is None:
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            result.add(
                f"{_relative(root, schema_path)}: invalid JSON Schema: {exc.message}"
            )
            continue
        schemas[state_name] = schema

        state_path = root / ".studio" / "state" / STATE_FILES[state_name]
        instance = loaded.get(state_path)
        if instance is None:
            continue
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for error in sorted(
            validator.iter_errors(instance), key=lambda item: list(item.path)
        ):
            location = ".".join(str(part) for part in error.path) or "<root>"
            result.add(f"{_relative(root, state_path)}:{location}: {error.message}")
    return schemas


def _validate_catalog(
    root: Path, catalog: dict[str, Any], result: ValidationResult
) -> None:
    phases = catalog.get("phases", [])
    workflows = catalog.get("workflows", [])
    phase_ids = [phase.get("id") for phase in phases]
    aliases = [workflow.get("alias") for workflow in workflows]
    alias_set = set(aliases)

    if len(phase_ids) != len(set(phase_ids)):
        result.add(".studio/workflow-catalog.json: duplicate phase id")
    if len(aliases) != len(alias_set):
        result.add(".studio/workflow-catalog.json: duplicate workflow alias")
    for phase in phases:
        phase_id = phase.get("id")
        if phase_id not in PHASES:
            result.add(f".studio/workflow-catalog.json: invalid phase '{phase_id}'")
        for alias in phase.get("workflows", []):
            if alias not in alias_set:
                result.add(
                    f".studio/workflow-catalog.json: phase references unknown alias '{alias}'"
                )
    for workflow in workflows:
        alias = workflow.get("alias", "<missing>")
        if workflow.get("phase") not in phase_ids:
            result.add(
                f".studio/workflow-catalog.json: {alias} references unknown phase"
            )
        for key in ("playbook",):
            reference = workflow.get(key)
            if not reference or not (root / reference).is_file():
                result.add(
                    f".studio/workflow-catalog.json: {alias} has broken {key} reference '{reference}'"
                )
        for role in workflow.get("roles", []):
            if not (root / role).is_file():
                result.add(
                    f".studio/workflow-catalog.json: {alias} has broken role reference '{role}'"
                )
        for next_alias in workflow.get("next", []):
            if next_alias not in alias_set:
                result.add(
                    f".studio/workflow-catalog.json: {alias} references unknown next alias '{next_alias}'"
                )


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return duplicate


def _validate_relationships(
    state: dict[str, Any], catalog: dict[str, Any], result: ValidationResult
) -> None:
    issues = state["issues"]["issues"]
    decisions = state["decisions"]["decisions"]
    evidence = state["evidence"]["evidence"]
    cp_items = state["critical_path"]["items"]
    issue_ids = {item["id"] for item in issues}
    decision_ids = {item["id"] for item in decisions}
    evidence_ids = {item["id"] for item in evidence}
    cp_ids = {item["id"] for item in cp_items}
    issue_by_id = {item["id"]: item for item in issues}
    decision_by_id = {item["id"]: item for item in decisions}
    evidence_by_id = {item["id"]: item for item in evidence}

    for label, records in (
        ("issue", issues),
        ("decision", decisions),
        ("evidence", evidence),
        ("critical-path", cp_items),
    ):
        for duplicate in sorted(_duplicates(item["id"] for item in records)):
            result.add(f"Duplicate {label} id: {duplicate}")

    for issue in issues:
        for field_name in ("dependencies", "issues_blocked"):
            references = issue[field_name]
            for duplicate in sorted(_duplicates(references)):
                result.add(
                    f"{issue['id']}: duplicate {field_name.replace('_', ' ')} "
                    f"reference {duplicate}"
                )
            for related in references:
                if related == issue["id"]:
                    relationship = (
                        "depend on itself"
                        if field_name == "dependencies"
                        else "block itself"
                    )
                    result.add(f"{issue['id']}: cannot {relationship}")
                if related not in issue_ids:
                    result.add(f"{issue['id']}: broken issue relationship {related}")
        for duplicate in sorted(_duplicates(issue["evidence_references"])):
            result.add(f"{issue['id']}: duplicate evidence reference {duplicate}")
        for reference in issue["evidence_references"]:
            if reference not in evidence_ids:
                result.add(f"{issue['id']}: broken evidence reference {reference}")
            elif issue["id"] not in evidence_by_id[reference]["related_issues"]:
                result.add(f"{issue['id']}: evidence link {reference} is one-sided")
        active_classifications = [
            evidence_by_id[reference]["classification"]
            for reference in issue["evidence_references"]
            if reference in evidence_by_id
            and evidence_by_id[reference]["status"] == "active"
        ]
        priority = {
            "observed": 0,
            "user-reported": 1,
            "inferred": 2,
            "unknown": 3,
        }
        expected_type = (
            min(active_classifications, key=priority.__getitem__)
            .replace("-", "_")
            .upper()
            if active_classifications
            else "UNKNOWN"
        )
        if issue["evidence_type"] != expected_type:
            result.add(
                f"{issue['id']}: evidence_type {issue['evidence_type']} does not "
                f"match active linked evidence ({expected_type})"
            )
        if (
            issue["status"] in {"resolved", "accepted", "wont-fix"}
            and not issue["resolution"]
        ):
            result.add(
                f"{issue['id']}: resolution is required for status {issue['status']}"
            )
        try:
            created = datetime.fromisoformat(issue["created_at"])
            updated = datetime.fromisoformat(issue["updated_at"])
        except ValueError:
            # JSON Schema's date-time format error is already more precise.
            continue
        if updated < created:
            result.add(f"{issue['id']}: updated_at cannot be earlier than created_at")
    for decision in decisions:
        option_ids = [option["id"] for option in decision["options"]]
        option_labels = [option["label"].casefold() for option in decision["options"]]
        for duplicate in sorted(_duplicates(option_ids)):
            result.add(f"{decision['id']}: duplicate option ID {duplicate}")
        for duplicate in sorted(_duplicates(option_labels)):
            result.add(f"{decision['id']}: duplicate option label {duplicate}")
        if not 2 <= len(option_ids) <= 6:
            result.add(f"{decision['id']}: must contain between two and six options")
        if decision["recommended_option"] not in option_ids:
            result.add(f"{decision['id']}: recommended option does not exist")
        if (
            decision["final_option_id"] is not None
            and decision["final_option_id"] not in option_ids
        ):
            result.add(f"{decision['id']}: final option does not exist")
        for field_name, known_ids, label in (
            ("affected_issues", issue_ids, "issue"),
            ("supporting_evidence", evidence_ids, "evidence"),
        ):
            references = decision[field_name]
            for duplicate in sorted(_duplicates(references)):
                result.add(f"{decision['id']}: duplicate {label} reference {duplicate}")
            for reference in references:
                if reference not in known_ids:
                    result.add(
                        f"{decision['id']}: broken {label} reference {reference}"
                    )
        for field_name in (
            "trade_offs",
            "consequences",
            "follow_up_actions",
        ):
            for duplicate in sorted(_duplicates(decision[field_name])):
                result.add(
                    f"{decision['id']}: duplicate "
                    f"{field_name.replace('_', ' ')} {duplicate}"
                )
        if decision["status"] == "resolved":
            if not decision["final_decision"]:
                result.add(f"{decision['id']}: resolved decision needs final decision")
            if not decision["decision_reason"]:
                result.add(f"{decision['id']}: resolved decision needs a reason")
            if not decision["resolved_at"]:
                result.add(f"{decision['id']}: resolved decision needs resolved_at")
            if not decision["resolution_history"]:
                result.add(
                    f"{decision['id']}: resolved decision needs resolution history"
                )
        if decision["status"] in {"open", "ready", "blocked", "deferred"}:
            if not decision["decision_owner"]:
                result.add(f"{decision['id']}: pending decision needs a decision owner")
            if any(
                decision[field_name] is not None
                for field_name in (
                    "final_decision",
                    "final_option_id",
                    "decision_reason",
                    "resolved_at",
                )
            ):
                result.add(
                    f"{decision['id']}: unresolved decision has active resolution fields"
                )
        for history in decision["resolution_history"]:
            if (
                history["final_option_id"] is not None
                and history["final_option_id"] not in option_ids
            ):
                result.add(
                    f"{decision['id']}: resolution history has invalid final option"
                )
        try:
            created = datetime.fromisoformat(decision["created_at"])
            updated = datetime.fromisoformat(decision["updated_at"])
            if decision["resolved_at"] is not None:
                datetime.fromisoformat(decision["resolved_at"])
            if decision["decision_required_by"] is not None:
                datetime.fromisoformat(decision["decision_required_by"])
            for history in decision["resolution_history"]:
                datetime.fromisoformat(history["resolved_at"])
        except ValueError:
            # JSON Schema's date/date-time format error is already more precise.
            continue
        if updated < created:
            result.add(
                f"{decision['id']}: updated_at cannot be earlier than created_at"
            )

    decision_supersession = {
        item["id"]: item["supersedes"]
        for item in decisions
        if item["supersedes"] is not None
    }
    superseded_decisions = set(decision_supersession.values())
    for duplicate in sorted(_duplicates(decision_supersession.values())):
        result.add(f"Decision: {duplicate} has more than one replacement")
    for decision in decisions:
        target_id = decision["supersedes"]
        if target_id is not None:
            if target_id not in decision_ids:
                result.add(f"{decision['id']}: missing superseded decision {target_id}")
            if target_id == decision["id"]:
                result.add(f"{decision['id']}: decision cannot supersede itself")
        if (
            decision["status"] == "superseded"
            and decision["id"] not in superseded_decisions
        ):
            result.add(
                f"{decision['id']}: superseded status has no replacement decision"
            )
        if (
            decision["status"] in {"open", "ready", "blocked", "deferred"}
            and decision["id"] in superseded_decisions
        ):
            result.add(f"{decision['id']}: superseded decision cannot remain pending")
    for start in decision_supersession:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                result.add(f"Decision: circular supersession at {current}")
                break
            seen.add(current)
            current = decision_supersession.get(current)
    source_optional = {
        "runtime",
        "human-playtest",
        "user-note",
        "source-review",
        "spec-review",
    }
    for item in evidence:
        for duplicate in sorted(_duplicates(item["related_issues"])):
            result.add(f"{item['id']}: duplicate related issue {duplicate}")
        for issue_id in item["related_issues"]:
            if issue_id not in issue_ids:
                result.add(f"{item['id']}: broken related issue {issue_id}")
            elif item["id"] not in issue_by_id[issue_id]["evidence_references"]:
                result.add(f"{item['id']}: issue link {issue_id} is one-sided")
        for duplicate in sorted(_duplicates(item["limitations"])):
            result.add(f"{item['id']}: duplicate limitation {duplicate}")
        if item["source"] is None and item["source_type"] not in source_optional:
            result.add(
                f"{item['id']}: source is required for source type "
                f"{item['source_type']}"
            )
        if (
            item["source"] is None
            and item["source_type"] in source_optional
            and not item["description"]
        ):
            result.add(f"{item['id']}: description is required when source is omitted")
        try:
            created = datetime.fromisoformat(item["created_at"])
            updated = datetime.fromisoformat(item["updated_at"])
            datetime.fromisoformat(item["captured_at"])
        except ValueError:
            # JSON Schema's date-time format error is already more precise.
            continue
        if updated < created:
            result.add(f"{item['id']}: updated_at cannot be earlier than created_at")
        target_id = item["supersedes"]
        if target_id is not None:
            if target_id not in evidence_ids:
                result.add(f"{item['id']}: missing superseded evidence {target_id}")
            if target_id == item["id"]:
                result.add(f"{item['id']}: evidence cannot supersede itself")
            target = evidence_by_id.get(target_id)
            if (
                item["status"] == "active"
                and target is not None
                and target["status"] != "superseded"
            ):
                result.add(
                    f"{item['id']}: active superseding evidence requires "
                    f"{target_id} to have status superseded"
                )

    supersession = {
        item["id"]: item["supersedes"]
        for item in evidence
        if item["supersedes"] is not None
    }
    superseded_targets = set(supersession.values())
    for duplicate in sorted(_duplicates(supersession.values())):
        result.add(f"Evidence: {duplicate} has more than one superseding record")
    for item in evidence:
        if item["status"] == "superseded" and item["id"] not in superseded_targets:
            result.add(f"{item['id']}: status superseded has no replacement evidence")
        if item["status"] == "active" and item["id"] in superseded_targets:
            result.add(
                f"{item['id']}: active evidence cannot have a superseding record"
            )
    for start in supersession:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                result.add(f"Evidence: circular supersession chain at {current}")
                break
            seen.add(current)
            current = supersession.get(current)
    for item in cp_items:
        if (
            item["source_issue_id"] is not None
            and item["source_issue_id"] not in issue_ids
        ):
            result.add(f"{item['id']}: broken source issue {item['source_issue_id']}")
        if (
            item["source_decision_id"] is not None
            and item["source_decision_id"] not in decision_ids
        ):
            result.add(
                f"{item['id']}: broken source decision {item['source_decision_id']}"
            )
        source_decision = decision_by_id.get(item["source_decision_id"])
        if source_decision is not None and source_decision["status"] in {
            "resolved",
            "rejected",
            "superseded",
        }:
            result.add(
                f"{item['id']}: closed decision {source_decision['id']} cannot "
                "remain on the active critical path"
            )
        source_issue = issue_by_id.get(item["source_issue_id"])
        if source_issue is not None:
            if source_issue["status"] in {
                "resolved",
                "accepted",
                "wont-fix",
                "deferred",
            }:
                result.add(
                    f"{item['id']}: closed issue {source_issue['id']} cannot remain "
                    "on the active critical path"
                )
            if not source_issue["on_critical_path"]:
                result.add(
                    f"{item['id']}: source issue {source_issue['id']} is not marked "
                    "on_critical_path"
                )
        for dependency in item["dependencies"]:
            if dependency not in cp_ids:
                result.add(
                    f"{item['id']}: broken critical-path dependency {dependency}"
                )
            if dependency == item["id"]:
                result.add(f"{item['id']}: cannot depend on itself")

    milestone = state["milestone"]
    for reference in milestone["supporting_evidence"]:
        if reference not in evidence_ids:
            result.add(f"Milestone: broken evidence reference {reference}")
        elif evidence_by_id[reference]["status"] != "active":
            result.add(
                f"Milestone: inactive evidence {reference} cannot be current support"
            )
    for reference in milestone["blocking_issues"]:
        if reference not in issue_ids:
            result.add(f"Milestone: broken issue reference {reference}")
    for criterion in milestone["criteria_results"]:
        for reference in criterion["evidence_references"]:
            if reference not in evidence_ids:
                result.add(
                    f"Milestone criterion: broken evidence reference {reference}"
                )
            elif evidence_by_id[reference]["status"] != "active":
                result.add(
                    f"Milestone criterion: inactive evidence {reference} cannot "
                    "be current support"
                )

    project = state["project"]
    aliases = {workflow["alias"] for workflow in catalog["workflows"]}
    catalog_phases = {phase["id"] for phase in catalog["phases"]}
    if project["current_phase"] not in PHASES:
        result.add(f"Project: invalid phase {project['current_phase']}")
    if project["current_phase"] not in catalog_phases:
        result.add("Project: current phase is not present in the workflow catalog")
    if project["recommended_next_playbook"] not in aliases:
        result.add("Project: recommended next playbook is not in workflow catalog")
    if state["critical_path"]["current_milestone"] != project["current_milestone"]:
        result.add("Critical path milestone does not match project milestone")
    if milestone["milestone"] != project["current_milestone"]:
        result.add("Milestone review does not match project milestone")
    if milestone["verdict"] not in {"PROCEED", "ITERATE", "PIVOT", "PAUSE", "STOP"}:
        result.add(f"Milestone: invalid verdict {milestone['verdict']}")

    criteria = milestone["success_criteria"]
    result_criteria = [item["criterion"] for item in milestone["criteria_results"]]
    if len(result_criteria) != len(set(result_criteria)):
        result.add("Milestone: duplicate criterion result")
    if set(criteria) != set(result_criteria):
        result.add("Milestone: success criteria and criterion results do not match")

    referenced_issue_ids = {
        item["source_issue_id"]
        for item in cp_items
        if item["source_issue_id"] is not None
    }
    for duplicate in sorted(
        _duplicates(
            item["source_issue_id"]
            for item in cp_items
            if item["source_issue_id"] is not None
        )
    ):
        result.add(
            f"Critical path: issue {duplicate} appears in more than one active item"
        )
    for issue in issues:
        if issue["on_critical_path"] and issue["id"] not in referenced_issue_ids:
            result.add(
                f"{issue['id']}: marked on_critical_path but no active item references it"
            )


def validate_state(root: Path, state: CanonicalState) -> ValidationResult:
    """Validate proposed canonical state without reading current state or reports."""

    root = root.resolve()
    result = ValidationResult()
    catalog_path = root / ".studio" / "workflow-catalog.json"
    try:
        catalog = load_json(catalog_path)
    except (OSError, ValueError) as exc:
        result.add(str(exc))
        return result
    if not isinstance(catalog, dict):
        result.add(f"{catalog_path}: expected a JSON object")
        return result

    for state_name in STATE_FILES:
        schema_path = root / ".studio" / "schemas" / SCHEMA_FILES[state_name]
        try:
            schema = load_json(schema_path)
        except (OSError, ValueError) as exc:
            result.add(str(exc))
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            result.add(
                f"{_relative(root, schema_path)}: invalid JSON Schema: {exc.message}"
            )
            continue
        instance = state.get(state_name)
        if instance is None:
            result.add(f"Proposed state is missing '{state_name}'")
            continue
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for error in sorted(
            validator.iter_errors(instance), key=lambda item: list(item.path)
        ):
            location = ".".join(str(part) for part in error.path) or "<root>"
            state_path = root / ".studio" / "state" / STATE_FILES[state_name]
            result.add(f"{_relative(root, state_path)}:{location}: {error.message}")

    if not result.errors:
        _validate_relationships(state, catalog, result)
    return result


def _validate_generated_reports(
    root: Path, state: CanonicalState, result: ValidationResult
) -> None:
    from .reporting import render_report_contents

    try:
        expected = render_report_contents(state)
    except Exception as exc:  # noqa: BLE001 - validation must report renderer faults
        result.add(f"Generated reports: rendering failed: {exc}")
        return
    for filename, content in expected.items():
        path = root / ".studio" / "reports" / filename
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as exc:
            result.add(
                f"{_relative(root, path)}: could not read generated report: {exc}"
            )
            continue
        if actual != content:
            result.add(
                f"{_relative(root, path)}: generated report is stale; run 'studio report'"
            )


def validate_project(root: Path) -> ValidationResult:
    """Validate the complete Phase A framework."""

    root = root.resolve()
    result = ValidationResult()
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            result.add(f"Missing required file: {relative}")

    loaded = _load_json_files(root, result)
    _validate_documents(root, result)
    _validate_schemas(root, loaded, result)

    catalog_path = root / ".studio" / "workflow-catalog.json"
    catalog = loaded.get(catalog_path)
    if isinstance(catalog, dict):
        _validate_catalog(root, catalog, result)

    try:
        state = {
            name: loaded[root / ".studio" / "state" / filename]
            for name, filename in STATE_FILES.items()
        }
    except KeyError:
        state = {}
    if state and isinstance(catalog, dict):
        _validate_relationships(state, catalog, result)
        _validate_generated_reports(root, state, result)
    return result
