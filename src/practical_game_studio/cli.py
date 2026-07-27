"""Command-line entry point for Practical Game Studio."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .evidence import (
    SOURCE_OPTIONAL_TYPES,
    SOURCE_TYPES,
    EvidenceCreateRequest,
    EvidenceInputError,
    EvidenceNotFoundError,
    EvidencePatch,
    EvidenceService,
)
from .initialization import (
    InitializationError,
    InitRequest,
    initialize_project,
    is_placeholder_project,
)
from .issues import (
    IssueCreateRequest,
    IssueInputError,
    IssueNotFoundError,
    IssuePatch,
    IssueService,
)
from .models import MutationResult
from .reporting import format_status, generate_reports
from .state import StateReadError, StateRepository, find_project_root, load_state
from .transaction import TransactionError
from .validation import validate_project


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        help="PGS repository root (defaults to current/parent discovery)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Practical Game Studio foundation tooling",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="validate framework, schemas, state, and references"
    )
    _add_root_argument(validate_parser)
    status_parser = subparsers.add_parser(
        "status", help="show current milestone direction"
    )
    _add_root_argument(status_parser)
    report_parser = subparsers.add_parser(
        "report", help="generate Markdown reports from canonical JSON"
    )
    _add_root_argument(report_parser)
    init_parser = subparsers.add_parser(
        "init", help="initialize or explicitly update project identity"
    )
    _add_root_argument(init_parser)
    init_parser.add_argument("--name", help="project name")
    init_parser.add_argument("--engine", help="game engine")
    init_parser.add_argument("--engine-version", help="game engine version")
    init_parser.add_argument("--platform", help="target platform")
    init_parser.add_argument("--genre", help="game genre")
    init_parser.add_argument(
        "--review-mode",
        choices=("fast", "guided", "strict"),
        help="review intensity (defaults to guided on first initialization)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="update only explicitly supplied identity fields",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and render the proposal without writing files",
    )
    init_parser.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge a non-interactive forced update",
    )
    issue_parser = subparsers.add_parser("issue", help="manage project issues")
    issue_subparsers = issue_parser.add_subparsers(dest="issue_command", required=True)

    add_parser = issue_subparsers.add_parser("add", help="create an issue")
    _add_root_argument(add_parser)
    add_parser.add_argument("--title")
    add_parser.add_argument("--severity")
    add_parser.add_argument("--description")
    add_parser.add_argument("--category")
    add_parser.add_argument("--player-impact")
    add_parser.add_argument("--milestone-impact")
    add_parser.add_argument("--recommended-action")
    add_parser.add_argument("--effort")
    add_parser.add_argument("--owner")
    add_parser.add_argument("--user-decision-required", action="store_true")
    add_parser.add_argument("--on-critical-path", action="store_true")
    add_parser.add_argument("--dry-run", action="store_true")
    add_parser.add_argument("--json", action="store_true")
    add_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm creation in guided/strict non-interactive use",
    )

    list_parser = issue_subparsers.add_parser("list", help="list issues")
    _add_root_argument(list_parser)
    list_parser.add_argument("--status")
    list_parser.add_argument("--severity")
    list_parser.add_argument("--category")
    list_parser.add_argument("--owner")
    list_parser.add_argument("--critical-path", action="store_true")
    list_parser.add_argument("--user-decision-required", action="store_true")
    list_parser.add_argument("--all", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    show_parser = issue_subparsers.add_parser("show", help="show one issue")
    show_parser.add_argument("issue_id")
    _add_root_argument(show_parser)
    show_parser.add_argument("--json", action="store_true")

    update_parser = issue_subparsers.add_parser("update", help="update an issue")
    update_parser.add_argument("issue_id")
    _add_root_argument(update_parser)
    for flag in (
        "title",
        "description",
        "severity",
        "category",
        "status",
        "phase-discovered",
        "player-impact",
        "milestone-impact",
        "recommended-action",
        "effort",
        "owner",
        "resolution",
    ):
        update_parser.add_argument(f"--{flag}")
    decision_group = update_parser.add_mutually_exclusive_group()
    decision_group.add_argument(
        "--user-decision-required",
        action="store_true",
        dest="user_decision_required",
    )
    decision_group.add_argument(
        "--no-user-decision-required",
        action="store_false",
        dest="user_decision_required",
    )
    decision_group.set_defaults(user_decision_required=None)
    path_group = update_parser.add_mutually_exclusive_group()
    path_group.add_argument(
        "--on-critical-path",
        action="store_true",
        dest="critical_path",
    )
    path_group.add_argument(
        "--off-critical-path",
        action="store_false",
        dest="critical_path",
    )
    path_group.set_defaults(critical_path=None)
    update_parser.add_argument("--add-dependency", action="append", default=[])
    update_parser.add_argument("--remove-dependency", action="append", default=[])
    update_parser.add_argument("--add-blocked-issue", action="append", default=[])
    update_parser.add_argument("--remove-blocked-issue", action="append", default=[])
    update_parser.add_argument("--add-evidence", action="append", default=[])
    update_parser.add_argument("--remove-evidence", action="append", default=[])
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.add_argument("--json", action="store_true")

    evidence_parser = subparsers.add_parser("evidence", help="manage project evidence")
    evidence_subparsers = evidence_parser.add_subparsers(
        dest="evidence_command", required=True
    )

    evidence_add = evidence_subparsers.add_parser("add", help="create evidence")
    _add_root_argument(evidence_add)
    evidence_add.add_argument("--title")
    evidence_add.add_argument("--claim")
    evidence_add.add_argument("--classification")
    evidence_add.add_argument("--source-type")
    evidence_add.add_argument("--source")
    evidence_add.add_argument("--description")
    evidence_add.add_argument("--related-hypothesis")
    evidence_add.add_argument("--issue", action="append", default=[])
    evidence_add.add_argument("--confidence")
    evidence_add.add_argument("--limitation", action="append", default=[])
    evidence_add.add_argument("--captured-at")
    evidence_add.add_argument("--dry-run", action="store_true")
    evidence_add.add_argument("--json", action="store_true")
    evidence_add.add_argument(
        "--yes",
        action="store_true",
        help="confirm creation in guided/strict non-interactive use",
    )

    evidence_list = evidence_subparsers.add_parser("list", help="list evidence")
    _add_root_argument(evidence_list)
    evidence_list.add_argument("--classification")
    evidence_list.add_argument("--source-type")
    evidence_list.add_argument("--confidence")
    evidence_list.add_argument("--status")
    evidence_list.add_argument("--issue")
    view_group = evidence_list.add_mutually_exclusive_group()
    view_group.add_argument("--active", action="store_true")
    view_group.add_argument("--all", action="store_true")
    evidence_list.add_argument("--json", action="store_true")

    evidence_show = evidence_subparsers.add_parser("show", help="show evidence")
    evidence_show.add_argument("evidence_id")
    _add_root_argument(evidence_show)
    evidence_show.add_argument("--json", action="store_true")

    evidence_update = evidence_subparsers.add_parser("update", help="update evidence")
    evidence_update.add_argument("evidence_id")
    _add_root_argument(evidence_update)
    for flag in (
        "title",
        "claim",
        "classification",
        "source-type",
        "source",
        "description",
        "related-hypothesis",
        "confidence",
        "status",
        "supersedes",
    ):
        evidence_update.add_argument(f"--{flag}")
    evidence_update.add_argument("--add-limitation", action="append", default=[])
    evidence_update.add_argument("--remove-limitation", action="append", default=[])
    evidence_update.add_argument("--add-issue", action="append", default=[])
    evidence_update.add_argument("--remove-issue", action="append", default=[])
    evidence_update.add_argument("--dry-run", action="store_true")
    evidence_update.add_argument("--json", action="store_true")
    evidence_update.add_argument(
        "--yes",
        action="store_true",
        help="confirm update in guided/strict non-interactive use",
    )
    return parser


def _display_value(value: object) -> str:
    return str(value) if value not in (None, "") else "Unknown"


def _format_init_result(result: MutationResult) -> str:
    project = result.details["project"]
    already_initialized = result.details["already_initialized"]
    lines: list[str] = []
    if result.dry_run:
        lines.extend(["Dry run — no files were written.", ""])
    elif already_initialized and not result.changed_files:
        lines.extend(["Practical Game Studio is already initialized.", ""])
    else:
        lines.extend(["Practical Game Studio initialized.", ""])

    lines.extend(
        [
            f"Project: {_display_value(project['project_name'])}",
            f"Engine: {_display_value(project['engine'])}",
            f"Platform: {_display_value(project['platform'])}",
            f"Phase: {project['current_phase'].replace('-', ' ').title()}",
            f"Milestone: {project['current_milestone']}",
            f"Review mode: {project['review_mode'].title()}",
            "",
        ]
    )
    if result.changed_fields:
        lines.append("Proposed changes:" if result.dry_run else "Changed fields:")
        for field, change in result.changed_fields.items():
            label = field.replace("_", " ").title()
            lines.append(
                f"- {label}: {_display_value(change['old'])} -> "
                f"{_display_value(change['new'])}"
            )
        lines.append("")

    state_count = sum(
        path.startswith(".studio/state/") for path in result.changed_files
    )
    lines.append(f"State files changed: {state_count}")
    if result.dry_run:
        lines.append(
            f"Reports rendered for validation: {result.report_summary['rendered']}"
        )
        lines.append(f"Affected files: {len(result.changed_files)}")
    elif already_initialized and not result.changed_files:
        lines.append("Reports regenerated: 0")
        lines.append(f"Reports verified in memory: {result.report_summary['rendered']}")
    else:
        lines.append(f"Reports regenerated: {result.report_summary['rendered']}")
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(
        [
            "",
            "Recommended next workflow:",
            result.details["recommended_next_workflow"],
        ]
    )
    if already_initialized and not result.changed_files and not result.dry_run:
        lines.extend(["", "Run `studio status` to review current direction."])
    return "\n".join(lines)


def _run_init(args: argparse.Namespace, root: Path) -> int:
    existing = StateRepository(root).load_project()
    name = args.name
    if is_placeholder_project(existing) and (name is None or not name.strip()):
        if sys.stdin.isatty():
            name = input("Project name: ").strip()
        else:
            print(
                "studio init: missing required values: --name",
                file=sys.stderr,
            )
            return 2

    acknowledged = args.yes
    if args.force and not args.dry_run and not acknowledged:
        if sys.stdin.isatty():
            answer = input(
                "Update only the explicitly supplied project fields? [y/N]: "
            ).strip()
            acknowledged = answer.casefold() in {"y", "yes"}
            if not acknowledged:
                print("studio init: forced update cancelled.", file=sys.stderr)
                return 2
        else:
            print(
                "studio init: --force in a non-interactive terminal requires --yes",
                file=sys.stderr,
            )
            return 2

    request = InitRequest(
        name=name,
        engine=args.engine,
        engine_version=args.engine_version,
        platform=args.platform,
        genre=args.genre,
        review_mode=args.review_mode,
        force=args.force,
        dry_run=args.dry_run,
        acknowledged=acknowledged,
    )
    result = initialize_project(root, request)
    print(_format_init_result(result))
    return 0


def _json_envelope(
    *,
    success: bool,
    operation: str,
    data: Any = None,
    dry_run: bool = False,
    changed_files: Sequence[str] = (),
    unchanged_files: Sequence[str] = (),
    changed_fields: dict[str, Any] | None = None,
    warnings: Sequence[str] = (),
    validation: dict[str, Any] | None = None,
    reports: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": success,
        "operation": operation,
        "dry_run": dry_run,
        "changed_files": list(changed_files),
        "unchanged_files": list(unchanged_files),
        "changed_fields": changed_fields or {},
        "warnings": list(warnings),
        "data": data,
        "validation": validation or {},
        "reports": reports or {},
    }
    if error is not None:
        payload["error"] = error
    return payload


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _mutation_envelope(result: MutationResult) -> dict[str, Any]:
    return _json_envelope(
        success=result.success,
        operation=result.operation,
        data=result.details,
        dry_run=result.dry_run,
        changed_files=result.changed_files,
        unchanged_files=result.unchanged_files,
        changed_fields=result.changed_fields,
        warnings=result.warnings,
        validation=result.validation_summary,
        reports=result.report_summary,
    )


def _issue_create_request(args: argparse.Namespace) -> IssueCreateRequest:
    interactive = sys.stdin.isatty() and not args.json
    title = args.title
    severity = args.severity
    description = args.description
    missing: list[str] = []
    if title is None or not title.strip():
        if interactive:
            title = input("Issue title: ")
        else:
            missing.append("--title")
    if severity is None or not severity.strip():
        if interactive:
            severity = input("Severity (blocker/critical/major/minor/later): ")
        else:
            missing.append("--severity")
    if not any(
        value is not None and value.strip()
        for value in (description, args.player_impact, args.milestone_impact)
    ):
        if interactive:
            description = input("Description (or rerun with player/milestone impact): ")
        else:
            missing.append(
                "one of --description, --player-impact, or --milestone-impact"
            )
    if missing:
        raise IssueInputError("missing required values: " + ", ".join(missing))
    return IssueCreateRequest(
        title=title or "",
        severity=severity or "",
        description=description,
        category=args.category,
        player_impact=args.player_impact,
        milestone_impact=args.milestone_impact,
        recommended_action=args.recommended_action,
        effort=args.effort,
        owner=args.owner,
        user_decision_required=args.user_decision_required,
        on_critical_path=args.on_critical_path,
    )


def _format_issue_summary(issue: dict[str, Any]) -> str:
    lines = [
        f"ID: {issue['id']}",
        f"Severity: {issue['severity'].title()}",
        f"Status: {issue['status'].replace('-', ' ').title()}",
        f"Title: {issue['title']}",
    ]
    if issue["player_impact"]:
        lines.extend(["", "Player impact:", issue["player_impact"]])
    return "\n".join(lines)


def _run_issue_add(args: argparse.Namespace, root: Path) -> int:
    service = IssueService(root)
    request = _issue_create_request(args)
    preview = service.preview_issue(request)
    review_mode = service.repository.load_project()["review_mode"]
    if not args.dry_run and review_mode in {"guided", "strict"} and not args.yes:
        if sys.stdin.isatty() and not args.json:
            print("Proposed issue.\n")
            print(_format_issue_summary(preview))
            answer = input("\nCreate this issue? [y/N]: ").strip().casefold()
            if answer not in {"y", "yes"}:
                raise IssueInputError("issue creation cancelled")
        else:
            raise IssueInputError(
                f"{review_mode} review mode requires --yes in a "
                "non-interactive terminal"
            )
    result = service.create_issue(request, dry_run=args.dry_run)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    issue = result.details["issue"]
    heading = (
        "Dry run — no files were written.\n\nProposed issue."
        if result.dry_run
        else "Issue created."
    )
    print(f"{heading}\n\n{_format_issue_summary(issue)}")
    if result.dry_run:
        print(
            f"\nAffected files: {len(result.changed_files)}\n"
            f"Reports rendered for validation: "
            f"{result.report_summary['rendered']}"
        )
    else:
        print(f"\nReports regenerated: {result.report_summary['rendered']}")
    print(
        f"\nRecommended next workflow:\n{result.details['recommended_next_workflow']}"
    )
    return 0


def _run_issue_list(args: argparse.Namespace, root: Path) -> int:
    issues = IssueService(root).list_issues(
        status=args.status,
        severity=args.severity,
        category=args.category,
        owner=args.owner,
        critical_path=args.critical_path,
        user_decision_required=args.user_decision_required,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="issue.list",
                data={"count": len(issues), "issues": issues},
            )
        )
        return 0
    if not issues:
        print("No matching issues.")
        return 0
    label = "Issues" if args.all else "Open issues"
    print(f"{label}: {len(issues)}\n")
    print(f"{'ID':<12}{'Severity':<11}{'Status':<14}Title")
    for issue in issues:
        status = issue["status"].replace("-", " ").title()
        print(
            f"{issue['id']:<12}{issue['severity'].title():<11}"
            f"{status:<14}{issue['title']}"
        )
    return 0


def _populated_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in issue.items()
        if value not in (None, "", [], False)
        or key
        in {
            "id",
            "title",
            "severity",
            "status",
            "on_critical_path",
            "user_decision_required",
            "created_at",
            "updated_at",
        }
    }


def _format_issue_detail(issue: dict[str, Any]) -> str:
    labels = {
        "id": "ID",
        "title": "Title",
        "severity": "Severity",
        "status": "Status",
        "phase_discovered": "Phase discovered",
        "evidence_type": "Evidence type",
        "evidence_references": "Evidence references",
        "player_impact": "Player impact",
        "milestone_impact": "Milestone impact",
        "recommended_action": "Recommended action",
        "alternative_actions": "Alternative actions",
        "dependencies": "Dependencies",
        "issues_blocked": "Issues blocked",
        "on_critical_path": "On critical path",
        "user_decision_required": "User decision required",
        "created_at": "Created",
        "updated_at": "Updated",
    }
    scalar_first = ("id", "title", "severity", "status", "category", "owner", "effort")
    lines = []
    for key in scalar_first:
        if key not in issue or issue[key] in (None, ""):
            continue
        value = issue[key]
        if key in {"severity", "status", "category", "owner", "effort"}:
            value = str(value).replace("-", " ").title()
        lines.append(f"{labels.get(key, key.replace('_', ' ').title())}: {value}")
    for key, value in issue.items():
        if key in scalar_first or value in (None, "", [], False):
            continue
        label = labels.get(key, key.replace("_", " ").title())
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        elif isinstance(value, bool):
            rendered = "Yes" if value else "No"
        else:
            rendered = str(value)
        lines.extend(["", f"{label}:", rendered])
    for key in ("on_critical_path", "user_decision_required"):
        if key in issue and not issue[key]:
            lines.extend(["", f"{labels[key]}:", "No"])
    return "\n".join(lines)


def _run_issue_show(args: argparse.Namespace, root: Path) -> int:
    issue = IssueService(root).get_issue(args.issue_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="issue.show",
                data={"issue": issue},
            )
        )
    else:
        print(_format_issue_detail(_populated_issue(issue)))
    return 0


def _issue_patch(args: argparse.Namespace) -> IssuePatch:
    values: dict[str, Any] = {}
    for argument, field_name in (
        ("title", "title"),
        ("description", "description"),
        ("severity", "severity"),
        ("category", "category"),
        ("status", "status"),
        ("phase_discovered", "phase_discovered"),
        ("player_impact", "player_impact"),
        ("milestone_impact", "milestone_impact"),
        ("recommended_action", "recommended_action"),
        ("effort", "effort"),
        ("owner", "owner"),
        ("resolution", "resolution"),
    ):
        value = getattr(args, argument)
        if value is not None:
            values[field_name] = value
    if args.user_decision_required is not None:
        values["user_decision_required"] = args.user_decision_required
    return IssuePatch(
        values=values,
        add_dependencies=tuple(args.add_dependency),
        remove_dependencies=tuple(args.remove_dependency),
        add_blocked_issues=tuple(args.add_blocked_issue),
        remove_blocked_issues=tuple(args.remove_blocked_issue),
        add_evidence=tuple(args.add_evidence),
        remove_evidence=tuple(args.remove_evidence),
        critical_path=args.critical_path,
    )


def _run_issue_update(args: argparse.Namespace, root: Path) -> int:
    result = IssueService(root).update_issue(
        args.issue_id,
        _issue_patch(args),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    issue = result.details["issue"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed issue update.")
    elif result.details["no_op"]:
        print("Issue unchanged.")
    else:
        print("Issue updated.")
    print(f"\nID: {issue['id']}\nStatus: {issue['status'].replace('-', ' ').title()}")
    if result.changed_fields:
        print("Changed fields:")
        for field_name in result.changed_fields:
            print(f"- {field_name}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if result.dry_run:
        print(f"\nAffected files: {len(result.changed_files)}")
    else:
        regenerated = (
            0 if result.details["no_op"] else result.report_summary["rendered"]
        )
        print(f"\nReports regenerated: {regenerated}")
    return 0


def _run_issue(args: argparse.Namespace, root: Path) -> int:
    if args.issue_command == "add":
        return _run_issue_add(args, root)
    if args.issue_command == "list":
        return _run_issue_list(args, root)
    if args.issue_command == "show":
        return _run_issue_show(args, root)
    if args.issue_command == "update":
        return _run_issue_update(args, root)
    raise IssueInputError(f"unknown issue command {args.issue_command}")


def _evidence_create_request(args: argparse.Namespace) -> EvidenceCreateRequest:
    interactive = sys.stdin.isatty() and not args.json
    values = {
        "title": args.title,
        "claim": args.claim,
        "classification": args.classification,
        "source_type": args.source_type,
    }
    flags = {
        "title": "--title",
        "claim": "--claim",
        "classification": "--classification",
        "source_type": "--source-type",
    }
    prompts = {
        "title": "Evidence title: ",
        "claim": "Evidence claim: ",
        "classification": (
            "Classification (observed/user-reported/inferred/unknown): "
        ),
        "source_type": "Source type: ",
    }
    missing: list[str] = []
    for field_name, value in values.items():
        if value is not None and value.strip():
            continue
        if interactive:
            values[field_name] = input(prompts[field_name])
        else:
            missing.append(flags[field_name])
    if missing:
        raise EvidenceInputError("missing required values: " + ", ".join(missing))

    source = args.source
    description = args.description
    normalized_source_type = (
        (values["source_type"] or "").strip().casefold().replace("_", "-")
    )
    if (
        source is None
        and normalized_source_type in SOURCE_TYPES
        and normalized_source_type not in SOURCE_OPTIONAL_TYPES
    ):
        if interactive:
            source = input("Source reference: ")
        else:
            raise EvidenceInputError(
                f"source is required for source type {normalized_source_type}"
            )
    if source is None and description is None:
        if interactive:
            description = input("Description: ")
        else:
            raise EvidenceInputError("description is required when source is omitted")
    return EvidenceCreateRequest(
        title=values["title"] or "",
        claim=values["claim"] or "",
        classification=values["classification"] or "",
        source_type=values["source_type"] or "",
        source=source,
        description=description,
        related_hypothesis=args.related_hypothesis,
        related_issues=tuple(args.issue),
        confidence=args.confidence,
        limitations=tuple(args.limitation),
        captured_at=args.captured_at,
    )


def _format_evidence_summary(record: dict[str, Any]) -> str:
    lines = [
        f"ID: {record['id']}",
        f"Classification: {record['classification'].replace('-', ' ').title()}",
        f"Source type: {record['source_type'].replace('-', ' ').title()}",
        f"Confidence: {record['confidence'].title()}",
        "",
        "Claim:",
        record["claim"],
    ]
    if record["related_issues"]:
        lines.extend(["", "Related issues:"])
        lines.extend(f"- {issue_id}" for issue_id in record["related_issues"])
    return "\n".join(lines)


def _run_evidence_add(args: argparse.Namespace, root: Path) -> int:
    service = EvidenceService(root)
    request = _evidence_create_request(args)
    preview = service.preview_evidence(request)
    review_mode = service.repository.load_project()["review_mode"]
    if not args.dry_run and review_mode in {"guided", "strict"} and not args.yes:
        if sys.stdin.isatty() and not args.json:
            print("Proposed evidence.\n")
            print(_format_evidence_summary(preview))
            answer = input("\nCreate this evidence? [y/N]: ").strip().casefold()
            if answer not in {"y", "yes"}:
                raise EvidenceInputError("evidence creation cancelled")
        else:
            raise EvidenceInputError(
                f"{review_mode} review mode requires --yes in a "
                "non-interactive terminal"
            )
    result = service.create_evidence(request, dry_run=args.dry_run)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["evidence"]
    heading = (
        "Dry run — no files were written.\n\nProposed evidence."
        if result.dry_run
        else "Evidence created."
    )
    print(f"{heading}\n\n{_format_evidence_summary(record)}")
    if result.dry_run:
        print(
            f"\nAffected files: {len(result.changed_files)}\n"
            "Reports rendered for validation: "
            f"{result.report_summary['rendered']}"
        )
    else:
        print(f"\nReports regenerated: {result.report_summary['rendered']}")
    print(
        f"\nRecommended next workflow:\n{result.details['recommended_next_workflow']}"
    )
    return 0


def _run_evidence_list(args: argparse.Namespace, root: Path) -> int:
    if (
        args.active
        and args.status is not None
        and args.status.strip().casefold() != "active"
    ):
        raise EvidenceInputError(
            "--active cannot be combined with a non-active --status"
        )
    records = EvidenceService(root).list_evidence(
        classification=args.classification,
        source_type=args.source_type,
        confidence=args.confidence,
        status="active" if args.active else args.status,
        issue_id=args.issue,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="evidence.list",
                data={"count": len(records), "evidence": records},
            )
        )
        return 0
    if not records:
        print("No matching evidence.")
        return 0
    label = "Evidence" if args.all or args.status else "Active evidence"
    print(f"{label}: {len(records)}\n")
    print(f"{'ID':<10}{'Class':<15}{'Confidence':<12}{'Source':<18}Claim")
    for record in records:
        classification = record["classification"].replace("-", " ").title()
        source = record["source_type"].replace("-", " ").title()
        print(
            f"{record['id']:<10}{classification:<15}"
            f"{record['confidence'].title():<12}{source:<18}{record['claim']}"
        )
    return 0


def _populated_evidence(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if value not in (None, "", [])
        or key
        in {
            "id",
            "title",
            "claim",
            "classification",
            "source_type",
            "confidence",
            "status",
            "captured_at",
            "created_at",
            "updated_at",
        }
    }


def _format_evidence_detail(record: dict[str, Any]) -> str:
    labels = {
        "id": "ID",
        "source_type": "Source type",
        "related_hypothesis": "Related hypothesis",
        "related_issues": "Related issues",
        "captured_at": "Captured",
        "created_at": "Created",
        "updated_at": "Updated",
        "superseded_by": "Superseded by",
    }
    scalar_first = (
        "id",
        "title",
        "status",
        "classification",
        "source_type",
        "confidence",
    )
    lines: list[str] = []
    for key in scalar_first:
        if key not in record:
            continue
        value = record[key]
        if key in {"status", "classification", "source_type", "confidence"}:
            value = str(value).replace("-", " ").title()
        lines.append(f"{labels.get(key, key.title())}: {value}")
    for key, value in record.items():
        if key in scalar_first or value in (None, "", []):
            continue
        label = labels.get(key, key.replace("_", " ").title())
        if isinstance(value, list):
            lines.extend(["", f"{label}:"])
            lines.extend(f"- {item}" for item in value)
        else:
            lines.extend(["", f"{label}:", str(value)])
    return "\n".join(lines)


def _run_evidence_show(args: argparse.Namespace, root: Path) -> int:
    record = EvidenceService(root).get_evidence(args.evidence_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="evidence.show",
                data={"evidence": record},
            )
        )
    else:
        print(_format_evidence_detail(_populated_evidence(record)))
    return 0


def _evidence_patch(args: argparse.Namespace) -> EvidencePatch:
    values: dict[str, Any] = {}
    for argument, field_name in (
        ("title", "title"),
        ("claim", "claim"),
        ("classification", "classification"),
        ("source_type", "source_type"),
        ("source", "source"),
        ("description", "description"),
        ("related_hypothesis", "related_hypothesis"),
        ("confidence", "confidence"),
        ("status", "status"),
    ):
        value = getattr(args, argument)
        if value is not None:
            values[field_name] = value
    return EvidencePatch(
        values=values,
        add_limitations=tuple(args.add_limitation),
        remove_limitations=tuple(args.remove_limitation),
        add_issues=tuple(args.add_issue),
        remove_issues=tuple(args.remove_issue),
        supersedes=args.supersedes,
    )


def _run_evidence_update(args: argparse.Namespace, root: Path) -> int:
    result = EvidenceService(root).update_evidence(
        args.evidence_id,
        _evidence_patch(args),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["evidence"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed evidence update.")
    elif result.details["no_op"]:
        print("Evidence unchanged.")
    else:
        print("Evidence updated.")
    print(f"\nID: {record['id']}\nStatus: {record['status'].title()}")
    if result.changed_fields:
        print("Changed fields:")
        for field_name in result.changed_fields:
            print(f"- {field_name}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    if result.dry_run:
        print(f"\nAffected files: {len(result.changed_files)}")
    else:
        regenerated = (
            0 if result.details["no_op"] else result.report_summary["rendered"]
        )
        print(f"\nReports regenerated: {regenerated}")
    return 0


def _run_evidence(args: argparse.Namespace, root: Path) -> int:
    if args.evidence_command == "add":
        return _run_evidence_add(args, root)
    if args.evidence_command == "list":
        return _run_evidence_list(args, root)
    if args.evidence_command == "show":
        return _run_evidence_show(args, root)
    if args.evidence_command == "update":
        return _run_evidence_update(args, root)
    raise EvidenceInputError(f"unknown evidence command {args.evidence_command}")


def _operation(args: argparse.Namespace) -> str:
    if getattr(args, "command", None) == "issue":
        return f"issue.{getattr(args, 'issue_command', 'unknown')}"
    if getattr(args, "command", None) == "evidence":
        return f"evidence.{getattr(args, 'evidence_command', 'unknown')}"
    return getattr(args, "command", "studio")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        root = find_project_root(explicit=args.root)
        if args.command == "evidence":
            return _run_evidence(args, root)
        if args.command == "issue":
            return _run_issue(args, root)
        if args.command == "init":
            return _run_init(args, root)
        if args.command == "validate":
            result = validate_project(root)
            if not result.ok:
                print(
                    f"Validation failed with {len(result.errors)} error(s):",
                    file=sys.stderr,
                )
                for error in result.errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print(
                "Validation passed: framework, schemas, state, and references are valid."
            )
            return 0
        if args.command == "status":
            print(format_status(load_state(root)))
            return 0
        if args.command == "report":
            generated = generate_reports(root)
            print(f"Generated {len(generated)} report(s):")
            for path in generated:
                print(f"- {path.relative_to(root).as_posix()}")
            return 0
    except (EvidenceNotFoundError, IssueNotFoundError) as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={"type": "not_found", "message": str(exc)},
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 3
    except (EvidenceInputError, IssueInputError) as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={"type": "usage", "message": str(exc)},
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 2
    except TransactionError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation=_operation(args),
                    dry_run=getattr(args, "dry_run", False),
                    error={
                        "type": "transaction",
                        "stage": exc.stage,
                        "message": exc.message,
                    },
                )
            )
        else:
            print(f"studio: {exc}", file=sys.stderr)
        return 1
    except (
        FileNotFoundError,
        InitializationError,
        KeyError,
        OSError,
        StateReadError,
        ValueError,
    ) as exc:
        print(f"studio: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
