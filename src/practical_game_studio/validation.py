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
    "dependencies": "dependencies.schema.json",
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
            "dependencies",
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
    "src/practical_game_studio/dependencies.py",
    "src/practical_game_studio/criteria.py",
    "src/practical_game_studio/critical_path.py",
    "src/practical_game_studio/validation.py",
    "src/practical_game_studio/reporting.py",
    "src/practical_game_studio/state.py",
    "src/practical_game_studio/models.py",
    "docs/decision-management.md",
    "docs/dependency-management.md",
    "docs/milestone-criteria-management.md",
    "docs/critical-path-engine.md",
    "tests/test_decisions.py",
    "tests/test_dependencies.py",
    "tests/test_criteria.py",
    "tests/test_decision_cli.py",
    "tests/test_dependency_cli.py",
    "tests/test_criterion_cli.py",
    "tests/test_critical_path.py",
    "tests/test_critical_path_cli.py",
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
    dependencies = state["dependencies"]["dependencies"]
    evidence = state["evidence"]["evidence"]
    critical_path = state["critical_path"]
    cp_items = critical_path["items"]
    cp_history = critical_path.get("history", [])
    issue_ids = {item["id"] for item in issues}
    decision_ids = {item["id"] for item in decisions}
    evidence_ids = {item["id"] for item in evidence}
    all_cp_items = [*cp_items, *cp_history]
    cp_ids = {item["id"] for item in cp_items}
    historical_cp_ids = {item["id"] for item in cp_history}
    issue_by_id = {item["id"]: item for item in issues}
    decision_by_id = {item["id"]: item for item in decisions}
    evidence_by_id = {item["id"]: item for item in evidence}
    dependency_by_id = {item["id"]: item for item in dependencies}
    criteria_records = state["milestone"]["criteria_results"]
    criterion_ids = {item["id"] for item in criteria_records}
    criterion_by_id = {item["id"]: item for item in criteria_records}

    for label, records in (
        ("issue", issues),
        ("decision", decisions),
        ("dependency", dependencies),
        ("evidence", evidence),
        ("critical-path", all_cp_items),
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

    manual_endpoints = {
        f"MANUAL:{item['source_key'].split(':', 1)[1]}"
        for item in all_cp_items
        if item.get("manual") and item.get("source_key", "").startswith("manual:")
    }
    known_endpoints = {
        *issue_ids,
        *decision_ids,
        *criterion_ids,
        *manual_endpoints,
    }
    active_edges: dict[tuple[str, str], str] = {}
    current_milestone = state["project"]["current_milestone"]
    for dependency in dependencies:
        prerequisite = dependency["prerequisite"]
        dependent = dependency["dependent"]
        if prerequisite not in known_endpoints:
            result.add(
                f"{dependency['id']}: missing prerequisite endpoint {prerequisite}"
            )
        if dependent not in known_endpoints:
            result.add(f"{dependency['id']}: missing dependent endpoint {dependent}")
        if prerequisite == dependent:
            result.add(f"{dependency['id']}: dependency cannot depend on itself")
        if dependency["scope"] == "current-milestone":
            if not dependency["milestone"]:
                result.add(
                    f"{dependency['id']}: current-milestone dependency needs "
                    "milestone context"
                )
        elif dependency["milestone"] is not None:
            result.add(
                f"{dependency['id']}: project dependency cannot have milestone context"
            )
        if dependency["status"] == "active":
            edge = (prerequisite, dependent)
            if edge in active_edges:
                result.add(
                    f"Duplicate active dependency edge: {dependent} requires "
                    f"{prerequisite} ({active_edges[edge]} and {dependency['id']})"
                )
            active_edges[edge] = dependency["id"]
            for endpoint in (prerequisite, dependent):
                if endpoint.startswith("MC-"):
                    criterion = criterion_by_id.get(endpoint)
                    if (
                        criterion is not None
                        and criterion["lifecycle_status"] == "retired"
                    ):
                        result.add(
                            f"{dependency['id']}: active dependency endpoint "
                            f"{endpoint} is retired"
                        )
            if dependency["deactivated_at"] is not None:
                result.add(
                    f"{dependency['id']}: active dependency has deactivation time"
                )
            if dependency["deactivation_reason"] is not None:
                result.add(
                    f"{dependency['id']}: active dependency has deactivation reason"
                )
        else:
            if not dependency["deactivated_at"]:
                result.add(
                    f"{dependency['id']}: inactive dependency needs deactivated_at"
                )
            if not dependency["deactivation_reason"]:
                result.add(
                    f"{dependency['id']}: inactive dependency needs a "
                    "deactivation reason"
                )
        try:
            created = datetime.fromisoformat(dependency["created_at"])
            updated = datetime.fromisoformat(dependency["updated_at"])
            if dependency["deactivated_at"] is not None:
                datetime.fromisoformat(dependency["deactivated_at"])
        except ValueError:
            continue
        if updated < created:
            result.add(
                f"{dependency['id']}: updated_at cannot be earlier than created_at"
            )

    legacy_edges: set[tuple[str, str]] = set()
    for issue in issues:
        for prerequisite in issue["dependencies"]:
            legacy_edges.add((prerequisite, issue["id"]))
        if issue["user_decision_required"]:
            for decision in decisions:
                if issue["id"] in decision["affected_issues"] and decision[
                    "status"
                ] in {"open", "ready", "blocked", "deferred"}:
                    legacy_edges.add((decision["id"], issue["id"]))
    for edge in sorted(set(active_edges) & legacy_edges):
        dependency_id = active_edges[edge]
        result.add(
            f"{dependency_id}: edge is represented both explicitly and by a "
            f"legacy derived relationship ({edge[1]} requires {edge[0]})"
        )

    graph_edges = set(legacy_edges)
    graph_edges.update(
        edge
        for edge, dependency_id in active_edges.items()
        if dependency_by_id[dependency_id]["scope"] == "project"
        or dependency_by_id[dependency_id]["milestone"] == current_milestone
    )
    endpoint_graph: dict[str, list[str]] = {}
    for prerequisite, dependent in graph_edges:
        endpoint_graph.setdefault(dependent, []).append(prerequisite)
        endpoint_graph.setdefault(prerequisite, [])
    for values in endpoint_graph.values():
        values.sort()
    dependency_stack: list[str] = []
    dependency_visited: set[str] = set()

    def visit_dependency(endpoint: str) -> list[str] | None:
        if endpoint in dependency_stack:
            index = dependency_stack.index(endpoint)
            return [*dependency_stack[index:], endpoint]
        if endpoint in dependency_visited:
            return None
        dependency_stack.append(endpoint)
        for prerequisite in endpoint_graph.get(endpoint, []):
            cycle = visit_dependency(prerequisite)
            if cycle:
                return cycle
        dependency_stack.pop()
        dependency_visited.add(endpoint)
        return None

    for endpoint in sorted(endpoint_graph):
        cycle = visit_dependency(endpoint)
        if cycle:
            result.add("Dependency cycle: " + " -> ".join(cycle))
            break

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
    source_keys = {item["source_key"] for item in all_cp_items}
    for duplicate in sorted(_duplicates(item["source_key"] for item in all_cp_items)):
        result.add(f"Critical path: duplicate source key {duplicate}")
    id_to_source: dict[str, str] = {}
    for item in all_cp_items:
        previous_source = id_to_source.get(item["id"])
        if previous_source is not None and previous_source != item["source_key"]:
            result.add(
                f"{item['id']}: reused CP ID for a different source key "
                f"({previous_source} and {item['source_key']})"
            )
        id_to_source[item["id"]] = item["source_key"]
        try:
            created = datetime.fromisoformat(item["created_at"])
            updated = datetime.fromisoformat(item["updated_at"])
        except ValueError:
            continue
        if updated < created:
            result.add(f"{item['id']}: updated_at cannot be earlier than created_at")

    active_statuses = {"pending", "ready", "blocked", "in-progress"}
    historical_statuses = {"completed", "removed"}
    path_is_current = critical_path["freshness"]["status"] == "current"
    for item in cp_items:
        if item["status"] not in active_statuses:
            result.add(
                f"{item['id']}: active path item has invalid status {item['status']}"
            )
        source_id = item["source_id"]
        source_key = item["source_key"]
        if item["type"] == "issue":
            source_issue = issue_by_id.get(source_id)
            if source_issue is None:
                result.add(f"{item['id']}: broken source issue {source_id}")
            else:
                if source_issue["status"] in {
                    "resolved",
                    "accepted",
                    "wont-fix",
                    "deferred",
                }:
                    result.add(
                        f"{item['id']}: inactive issue {source_id} cannot remain "
                        "on the active critical path"
                    )
                if not source_issue["on_critical_path"]:
                    result.add(
                        f"{item['id']}: source issue {source_id} is not marked "
                        "on_critical_path"
                    )
            if source_key != f"issue:{source_id}":
                result.add(f"{item['id']}: issue source key does not match source")
        elif item["type"] == "decision":
            source_decision = decision_by_id.get(source_id)
            if source_decision is None:
                result.add(f"{item['id']}: broken source decision {source_id}")
            elif source_decision["status"] in {
                "resolved",
                "rejected",
                "superseded",
            }:
                result.add(
                    f"{item['id']}: historical decision {source_id} cannot remain "
                    "on the active critical path"
                )
            if source_key != f"decision:{source_id}":
                result.add(f"{item['id']}: decision source key does not match source")
        elif item["type"] == "milestone-criterion":
            source_criterion = criterion_by_id.get(source_id)
            if source_criterion is None:
                result.add(
                    f"{item['id']}: invalid milestone criterion source {source_id}"
                )
            elif source_criterion["lifecycle_status"] == "retired":
                result.add(
                    f"{item['id']}: retired criterion {source_id} cannot remain "
                    "on the active critical path"
                )
            elif source_criterion["support_status"] == "verified":
                result.add(
                    f"{item['id']}: verified criterion {source_id} cannot remain "
                    "on the active critical path"
                )
            if source_key != f"milestone:{source_id}":
                result.add(f"{item['id']}: milestone source key does not match source")
        elif item["type"] == "verification":
            if source_id is None:
                result.add(f"{item['id']}: verification source is missing")
            elif source_id.startswith("ISS-") and source_id not in issue_ids:
                result.add(f"{item['id']}: broken verification issue {source_id}")
            elif source_id.startswith("DEC-") and source_id not in decision_ids:
                result.add(f"{item['id']}: broken verification decision {source_id}")
            elif source_id.startswith("MC-") and source_id not in criterion_ids:
                result.add(f"{item['id']}: broken verification criterion {source_id}")
            elif source_id.startswith("MC-"):
                source_criterion = criterion_by_id[source_id]
                if source_criterion["lifecycle_status"] == "retired":
                    result.add(
                        f"{item['id']}: retired criterion {source_id} cannot "
                        "generate active verification work"
                    )
                if (
                    source_criterion["support_status"] == "verified"
                    and source_criterion["required"]
                ):
                    result.add(
                        f"{item['id']}: required verified criterion {source_id} "
                        "cannot generate active verification work"
                    )
                if (
                    not source_criterion["required"]
                    and source_criterion["support_status"] == "unsupported"
                    and not item["pinned"]
                ):
                    result.add(
                        f"{item['id']}: optional unsupported criterion {source_id} "
                        "requires manual inclusion"
                    )
        elif item["type"] == "manual-action":
            if not item["manual"]:
                result.add(f"{item['id']}: manual action must set manual to true")
            if not source_key.startswith("manual:"):
                result.add(f"{item['id']}: invalid manual action source key")
        else:
            result.add(f"{item['id']}: invalid source type {item['type']}")
        for duplicate in sorted(_duplicates(item["dependencies"])):
            result.add(f"{item['id']}: duplicate dependency {duplicate}")
        origin_keys = [
            origin["prerequisite_source_key"] for origin in item["dependency_origins"]
        ]
        for duplicate in sorted(_duplicates(origin_keys)):
            result.add(f"{item['id']}: duplicate dependency origin for {duplicate}")
        dependency_source_keys = {
            next(
                (
                    value["source_key"]
                    for value in cp_items
                    if value["id"] == dependency
                ),
                "",
            )
            for dependency in item["dependencies"]
        }
        if set(origin_keys) != dependency_source_keys:
            result.add(
                f"{item['id']}: dependency origins do not match path dependencies"
            )
        for origin in item["dependency_origins"]:
            dependency_id = origin["dependency_id"]
            if origin["origin"] == "explicit":
                explicit = dependency_by_id.get(dependency_id)
                if explicit is None:
                    result.add(
                        f"{item['id']}: missing explicit dependency {dependency_id}"
                    )
                elif explicit["status"] != "active" and path_is_current:
                    result.add(
                        f"{item['id']}: explicit dependency {dependency_id} is inactive"
                    )
            elif dependency_id is not None:
                result.add(
                    f"{item['id']}: derived dependency origin cannot use "
                    f"{dependency_id}"
                )
        for dependency in item["dependencies"]:
            if dependency not in cp_ids:
                if dependency in historical_cp_ids:
                    result.add(
                        f"{item['id']}: active item depends on removed or completed "
                        f"item {dependency}"
                    )
                else:
                    result.add(
                        f"{item['id']}: missing critical-path dependency {dependency}"
                    )
            if dependency == item["id"]:
                result.add(f"{item['id']}: cannot depend on itself")
    for item in cp_history:
        if item["status"] not in historical_statuses:
            result.add(
                f"{item['id']}: historical path item has invalid status "
                f"{item['status']}"
            )

    cp_dependencies = {
        item["id"]: [
            dependency for dependency in item["dependencies"] if dependency in cp_ids
        ]
        for item in cp_items
    }
    stack: list[str] = []
    visited: set[str] = set()

    def visit_path(item_id: str) -> list[str] | None:
        if item_id in stack:
            index = stack.index(item_id)
            return [*stack[index:], item_id]
        if item_id in visited:
            return None
        stack.append(item_id)
        for dependency_id in cp_dependencies[item_id]:
            cycle = visit_path(dependency_id)
            if cycle:
                return cycle
        stack.pop()
        visited.add(item_id)
        return None

    for start in sorted(cp_dependencies):
        cycle = visit_path(start)
        if cycle:
            result.add("Critical path dependency cycle: " + " -> ".join(cycle))
            break
    max_items = critical_path["configured_max_items"]
    if len(cp_items) > max_items and not any(
        "more than" in warning and "mandatory dependency items" in warning
        for warning in critical_path["warnings"]
    ):
        result.add(
            "Critical path exceeds configured maximum without mandatory-dependency "
            "warning metadata"
        )
    freshness = critical_path["freshness"]
    snapshot = critical_path["calculation_snapshot"]
    calculated_at = critical_path["calculated_at"]
    if freshness["status"] == "current" and (snapshot is None or freshness["reasons"]):
        result.add("Critical path current freshness requires a snapshot and no reasons")
    if freshness["status"] == "stale" and not freshness["reasons"]:
        result.add("Critical path stale freshness requires at least one reason")
    if (snapshot is None) != (calculated_at is None):
        result.add(
            "Critical path calculation snapshot and timestamp must both be set "
            "or both be null"
        )
    if (
        snapshot is not None
        and snapshot["milestone"] != critical_path["current_milestone"]
    ):
        result.add("Critical path calculation snapshot milestone does not match")
    recommended = critical_path["recommended_next_id"]
    if recommended is not None:
        recommended_item = next(
            (item for item in cp_items if item["id"] == recommended), None
        )
        if recommended_item is None:
            result.add("Critical path recommended-next item is missing")
        elif recommended_item["dependencies"]:
            result.add("Critical path recommended-next item is blocked by dependencies")
        elif recommended_item["status"] not in {"ready", "in-progress"}:
            result.add("Critical path recommended-next item is not actionable")
        else:
            dependent_endpoint = recommended_item.get("source_id")
            for dependency in dependencies:
                if (
                    dependency["status"] != "active"
                    or dependency["dependent"] != dependent_endpoint
                    or (
                        dependency["scope"] == "current-milestone"
                        and dependency["milestone"] != current_milestone
                    )
                ):
                    continue
                prerequisite = dependency["prerequisite"]
                satisfied = False
                if prerequisite.startswith("ISS-") and prerequisite in issue_by_id:
                    satisfied = issue_by_id[prerequisite]["status"] in {
                        "resolved",
                        "accepted",
                        "wont-fix",
                    }
                elif prerequisite.startswith("DEC-") and prerequisite in decision_by_id:
                    satisfied = decision_by_id[prerequisite]["status"] == "resolved"
                elif prerequisite.startswith("MC-") and prerequisite in criterion_by_id:
                    criterion = criterion_by_id[prerequisite]
                    satisfied = (
                        criterion["lifecycle_status"] == "active"
                        and criterion["support_status"] == "verified"
                        and criterion["evaluation_freshness"]["status"] == "current"
                    )
                elif prerequisite.startswith("MANUAL:"):
                    source_key = f"manual:{prerequisite.split(':', 1)[1].casefold()}"
                    satisfied = any(
                        item["source_key"] == source_key
                        and item["status"] == "completed"
                        for item in cp_history
                    )
                if not satisfied and path_is_current:
                    result.add(
                        "Critical path recommended-next item is incompatible with "
                        f"unsatisfied explicit dependency {dependency['id']}"
                    )
    pinned = critical_path["pinned_sources"]
    excluded = critical_path["excluded_sources"]
    for duplicate in sorted(_duplicates(pinned)):
        result.add(f"Critical path: duplicate pinned source {duplicate}")
    for duplicate in sorted(_duplicates(excluded)):
        result.add(f"Critical path: duplicate excluded source {duplicate}")
    for source_key in sorted(set(pinned) & set(excluded)):
        result.add(f"Critical path: source both pinned and excluded: {source_key}")
    for source_key in excluded:
        if source_key not in critical_path["exclusion_reasons"]:
            result.add(f"Critical path: excluded source {source_key} has no reason")
    for source_key in critical_path["exclusion_reasons"]:
        if source_key not in excluded:
            result.add(
                f"Critical path: exclusion reason has no excluded source {source_key}"
            )
    active_source_keys = {item["source_key"] for item in cp_items}
    known_source_keys = {
        *(f"issue:{item}" for item in issue_ids),
        *(f"decision:{item}" for item in decision_ids),
        *(f"milestone:{item}" for item in criterion_ids),
        *active_source_keys,
        *source_keys,
    }
    for source_key in pinned:
        if source_key not in active_source_keys:
            result.add(f"Critical path: invalid pinned source {source_key}")
    for source_key in excluded:
        if source_key not in known_source_keys:
            result.add(f"Critical path: invalid excluded source {source_key}")

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
        criterion_id = criterion["id"]
        for field_name in (
            "related_issues",
            "related_decisions",
            "supporting_evidence",
            "evaluation_limitations",
        ):
            for duplicate in sorted(_duplicates(criterion[field_name])):
                result.add(
                    f"{criterion_id}: duplicate "
                    f"{field_name.replace('_', ' ')} value {duplicate}"
                )
        for reference in criterion["related_issues"]:
            if reference not in issue_ids:
                result.add(f"{criterion_id}: broken issue reference {reference}")
        for reference in criterion["related_decisions"]:
            if reference not in decision_ids:
                result.add(f"{criterion_id}: broken decision reference {reference}")
        current_evidence: list[dict[str, Any]] = []
        for reference in criterion["supporting_evidence"]:
            if reference not in evidence_ids:
                result.add(f"{criterion_id}: broken evidence reference {reference}")
                continue
            current_evidence.append(evidence_by_id[reference])
            if (
                evidence_by_id[reference]["status"] != "active"
                and criterion["evaluation_freshness"]["status"] == "current"
            ):
                result.add(
                    f"{criterion_id}: inactive evidence {reference} cannot support "
                    "a current evaluation"
                )
        active_evidence = [
            item for item in current_evidence if item["status"] == "active"
        ]
        support = criterion["support_status"]
        freshness_status = criterion["evaluation_freshness"]["status"]
        if freshness_status == "current" and criterion["lifecycle_status"] == "active":
            if criterion["evaluation_freshness"]["reasons"]:
                result.add(
                    f"{criterion_id}: current evaluation freshness cannot have reasons"
                )
            if (
                support
                in {
                    "verified",
                    "partially-supported",
                    "contradicted",
                }
                and not active_evidence
            ):
                result.add(
                    f"{criterion_id}: {support} criterion requires active evidence"
                )
            if (
                support == "partially-supported"
                and not criterion["evaluation_limitations"]
            ):
                result.add(
                    f"{criterion_id}: partially supported criterion needs a limitation"
                )
            if support == "verified" and active_evidence:
                text = " ".join(
                    (
                        criterion["description"],
                        criterion["completion_condition"],
                        criterion["verification_method"] or "",
                    )
                ).casefold()
                player_behavior = any(
                    token in text
                    for token in (
                        "player",
                        "tester",
                        "playtest",
                        "unaided",
                        "without assistance",
                        "complete the loop",
                    )
                )
                non_runtime = any(
                    token in (criterion["verification_method"] or "").casefold()
                    for token in (
                        "document review",
                        "documentation review",
                        "source review",
                        "spec review",
                        "static inspection",
                        "approval review",
                    )
                )
                observed = any(
                    item["classification"] == "observed" for item in active_evidence
                )
                if player_behavior and not observed:
                    result.add(
                        f"{criterion_id}: player-behavior verification requires "
                        "observed evidence"
                    )
                elif not player_behavior and not non_runtime and not observed:
                    result.add(
                        f"{criterion_id}: verification requires observed evidence "
                        "or a documented non-runtime method"
                    )
        elif (
            freshness_status == "stale"
            and not criterion["evaluation_freshness"]["reasons"]
        ):
            result.add(f"{criterion_id}: stale evaluation freshness requires a reason")
        if criterion["lifecycle_status"] == "retired":
            if not criterion["retired_at"] or not criterion["retirement_reason"]:
                result.add(f"{criterion_id}: retired criterion needs time and reason")
        elif (
            criterion["retired_at"] is not None
            or criterion["retirement_reason"] is not None
        ):
            result.add(f"{criterion_id}: active criterion has retirement metadata")
        history = criterion["evaluation_history"]
        if history:
            latest = history[-1]
            if freshness_status == "current":
                if latest["support_status"] != criterion["support_status"]:
                    result.add(
                        f"{criterion_id}: current evaluation differs from latest "
                        "history support"
                    )
                if latest["reason"] != criterion["evaluation_reason"]:
                    result.add(
                        f"{criterion_id}: current evaluation reason differs from "
                        "latest history"
                    )
                if latest["limitations"] != criterion["evaluation_limitations"]:
                    result.add(
                        f"{criterion_id}: current limitations differ from latest "
                        "evaluation history"
                    )
                if [item["id"] for item in latest["evidence_snapshot"]] != criterion[
                    "supporting_evidence"
                ]:
                    result.add(
                        f"{criterion_id}: current evidence differs from latest "
                        "evaluation history"
                    )
            if criterion["evaluated_at"] != latest["evaluated_at"]:
                result.add(f"{criterion_id}: evaluated_at differs from latest history")
        elif (
            criterion["evaluated_at"] is not None
            or criterion["evaluation_reason"] is not None
        ):
            result.add(f"{criterion_id}: evaluation metadata exists without history")
        try:
            created = datetime.fromisoformat(criterion["created_at"])
            updated = datetime.fromisoformat(criterion["updated_at"])
            evaluated = (
                datetime.fromisoformat(criterion["evaluated_at"])
                if criterion["evaluated_at"]
                else None
            )
            retired = (
                datetime.fromisoformat(criterion["retired_at"])
                if criterion["retired_at"]
                else None
            )
            history_times = [
                datetime.fromisoformat(item["evaluated_at"]) for item in history
            ]
        except ValueError:
            continue
        if updated < created:
            result.add(f"{criterion_id}: updated_at cannot be earlier than created_at")
        if evaluated is not None and evaluated < created:
            result.add(
                f"{criterion_id}: evaluated_at cannot be earlier than created_at"
            )
        if retired is not None and retired < created:
            result.add(f"{criterion_id}: retired_at cannot be earlier than created_at")
        if history_times != sorted(history_times) or any(
            item < created for item in history_times
        ):
            result.add(
                f"{criterion_id}: evaluation history timestamps are out of order"
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
    if state["critical_path"]["current_milestone"] != project[
        "current_milestone"
    ] and not state["critical_path"].get("milestone_override", False):
        result.add("Critical path milestone does not match project milestone")
    if milestone["milestone"] != project["current_milestone"]:
        result.add("Milestone review does not match project milestone")
    if milestone["verdict"] not in {"PROCEED", "ITERATE", "PIVOT", "PAUSE", "STOP"}:
        result.add(f"Milestone: invalid verdict {milestone['verdict']}")

    criterion_result_ids = [item["id"] for item in milestone["criteria_results"]]
    for duplicate in sorted(_duplicates(criterion_result_ids)):
        result.add(f"Milestone: duplicate criterion ID {duplicate}")

    referenced_issue_ids = {
        item["source_id"] for item in cp_items if item["type"] == "issue"
    }
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
