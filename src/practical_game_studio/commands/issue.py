"""`studio issue` — create, inspect, and update project issues."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..issues import IssueCreateRequest, IssueInputError, IssuePatch, IssueService
from ._shared import (
    _add_root_argument,
    _json_envelope,
    _mutation_envelope,
    _print_json,
    _recommended_workflow_block,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio issue` and its subcommands."""

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
    print(_recommended_workflow_block(result.details))
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


def run(args: argparse.Namespace, root: Path) -> int:
    if args.issue_command == "add":
        return _run_issue_add(args, root)
    if args.issue_command == "list":
        return _run_issue_list(args, root)
    if args.issue_command == "show":
        return _run_issue_show(args, root)
    if args.issue_command == "update":
        return _run_issue_update(args, root)
    raise IssueInputError(f"unknown issue command {args.issue_command}")
