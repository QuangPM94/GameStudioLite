"""Command-line entry point for Practical Game Studio."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .bootstrap import (
    BootstrapConflictError,
    BootstrapError,
    BootstrapRequest,
    BootstrapService,
)
from .criteria import (
    CriterionCreateRequest,
    CriterionEvaluation,
    CriterionInputError,
    CriterionNotFoundError,
    CriterionPatch,
    CriterionService,
)
from .critical_path import (
    CriticalPathInputError,
    CriticalPathNotFoundError,
    CriticalPathService,
    PathCalculationRequest,
)
from .decisions import (
    DecisionCreateRequest,
    DecisionInputError,
    DecisionNotFoundError,
    DecisionOption,
    DecisionPatch,
    DecisionResolution,
    DecisionService,
)
from .dependencies import (
    DependencyCreateRequest,
    DependencyInputError,
    DependencyNotFoundError,
    DependencyPatch,
    DependencyService,
)
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
from .validation import validate_framework, validate_project


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
    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="attach Practical Game Studio to a game repository"
    )
    bootstrap_parser.add_argument(
        "--root",
        type=Path,
        help="target game root (defaults to the current working directory)",
    )
    bootstrap_parser.add_argument("--name", help="project name")
    bootstrap_parser.add_argument("--engine", help="game engine")
    bootstrap_parser.add_argument("--engine-version", help="game engine version")
    bootstrap_parser.add_argument("--platform", help="target platform")
    bootstrap_parser.add_argument("--genre", help="game genre")
    bootstrap_parser.add_argument(
        "--review-mode",
        choices=("fast", "guided", "strict"),
        help="review intensity (defaults to guided during initialization)",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="replace conflicting framework-managed files only",
    )
    bootstrap_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the proposed scaffold without writing target files",
    )
    bootstrap_parser.add_argument(
        "--json", action="store_true", help="emit one JSON result envelope"
    )
    bootstrap_parser.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge non-interactive managed-file replacement",
    )
    validate_parser = subparsers.add_parser(
        "validate", help="validate a bootstrapped game project"
    )
    _add_root_argument(validate_parser)
    validate_parser.add_argument("--json", action="store_true")
    framework_parser = subparsers.add_parser(
        "framework", help="GameStudioLite framework development commands"
    )
    framework_subparsers = framework_parser.add_subparsers(
        dest="framework_command", required=True
    )
    framework_validate = framework_subparsers.add_parser(
        "validate", help="validate the GameStudioLite framework source repository"
    )
    _add_root_argument(framework_validate)
    framework_validate.add_argument("--json", action="store_true")
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

    decision_parser = subparsers.add_parser(
        "decision", help="manage meaningful project decisions"
    )
    decision_subparsers = decision_parser.add_subparsers(
        dest="decision_command", required=True
    )

    decision_add = decision_subparsers.add_parser("add", help="create a decision")
    _add_root_argument(decision_add)
    for flag in (
        "question",
        "context",
        "phase",
        "milestone",
        "urgency",
        "owner",
        "required-by",
        "recommended-option",
        "recommendation-reason",
        "revisit-condition",
        "status",
    ):
        decision_add.add_argument(f"--{flag}")
    decision_add.add_argument("--issue", action="append", default=[])
    decision_add.add_argument("--evidence", action="append", default=[])
    decision_add.add_argument("--option", action="append", default=[])
    decision_add.add_argument("--trade-off", action="append", default=[])
    decision_add.add_argument("--dry-run", action="store_true")
    decision_add.add_argument("--json", action="store_true")
    decision_add.add_argument("--yes", action="store_true")

    decision_list = decision_subparsers.add_parser("list", help="list decisions")
    _add_root_argument(decision_list)
    for flag in ("status", "urgency", "owner", "phase", "issue", "evidence"):
        decision_list.add_argument(f"--{flag}")
    decision_view = decision_list.add_mutually_exclusive_group()
    decision_view.add_argument("--pending", action="store_true")
    decision_view.add_argument("--resolved", action="store_true")
    decision_view.add_argument("--all", action="store_true")
    decision_list.add_argument("--json", action="store_true")

    decision_show = decision_subparsers.add_parser("show", help="show a decision")
    decision_show.add_argument("decision_id")
    _add_root_argument(decision_show)
    decision_show.add_argument("--json", action="store_true")

    decision_update = decision_subparsers.add_parser("update", help="update a decision")
    decision_update.add_argument("decision_id")
    _add_root_argument(decision_update)
    for flag in (
        "question",
        "context",
        "phase",
        "milestone",
        "urgency",
        "owner",
        "required-by",
        "status",
        "recommended-option",
        "recommendation-reason",
        "revisit-condition",
        "supersedes",
    ):
        decision_update.add_argument(f"--{flag}")
    decision_update.add_argument("--add-trade-off", action="append", default=[])
    decision_update.add_argument("--remove-trade-off", action="append", default=[])
    decision_update.add_argument("--add-issue", action="append", default=[])
    decision_update.add_argument("--remove-issue", action="append", default=[])
    decision_update.add_argument("--add-evidence", action="append", default=[])
    decision_update.add_argument("--remove-evidence", action="append", default=[])
    decision_update.add_argument("--add-option", action="append", default=[])
    decision_update.add_argument("--update-option", action="append", default=[])
    decision_update.add_argument("--remove-option", action="append", default=[])
    decision_update.add_argument("--dry-run", action="store_true")
    decision_update.add_argument("--json", action="store_true")
    decision_update.add_argument("--yes", action="store_true")

    decision_resolve = decision_subparsers.add_parser(
        "resolve", help="resolve a decision"
    )
    decision_resolve.add_argument("decision_id")
    _add_root_argument(decision_resolve)
    resolution_choice = decision_resolve.add_mutually_exclusive_group()
    resolution_choice.add_argument("--option")
    resolution_choice.add_argument("--custom-decision")
    decision_resolve.add_argument("--reason")
    decision_resolve.add_argument("--consequence", action="append", default=[])
    decision_resolve.add_argument("--follow-up", action="append", default=[])
    decision_resolve.add_argument("--revisit-condition")
    decision_resolve.add_argument("--dry-run", action="store_true")
    decision_resolve.add_argument("--json", action="store_true")
    decision_resolve.add_argument("--yes", action="store_true")

    dependency_parser = subparsers.add_parser(
        "dependency", help="manage explicit actionable dependencies"
    )
    dependency_subparsers = dependency_parser.add_subparsers(
        dest="dependency_command", required=True
    )
    dependency_add = dependency_subparsers.add_parser(
        "add", help="create or reactivate a dependency"
    )
    _add_root_argument(dependency_add)
    dependency_add.add_argument("--prerequisite")
    dependency_add.add_argument("--dependent")
    dependency_add.add_argument("--reason")
    dependency_add.add_argument(
        "--scope",
        choices=("current-milestone", "project"),
        default="current-milestone",
    )
    dependency_add.add_argument("--dry-run", action="store_true")
    dependency_add.add_argument("--json", action="store_true")
    dependency_add.add_argument("--yes", action="store_true")

    dependency_list = dependency_subparsers.add_parser("list", help="list dependencies")
    _add_root_argument(dependency_list)
    dependency_list.add_argument("--status", choices=("active", "inactive"))
    dependency_list.add_argument("--source")
    dependency_list.add_argument("--prerequisite")
    dependency_list.add_argument("--dependent")
    dependency_list.add_argument("--scope", choices=("current-milestone", "project"))
    dependency_view = dependency_list.add_mutually_exclusive_group()
    dependency_view.add_argument("--active", action="store_true")
    dependency_view.add_argument("--all", action="store_true")
    dependency_list.add_argument("--json", action="store_true")

    dependency_show = dependency_subparsers.add_parser(
        "show", help="show one dependency"
    )
    dependency_show.add_argument("dependency_id")
    _add_root_argument(dependency_show)
    dependency_show.add_argument("--json", action="store_true")

    dependency_update = dependency_subparsers.add_parser(
        "update", help="update a dependency"
    )
    dependency_update.add_argument("dependency_id")
    _add_root_argument(dependency_update)
    dependency_update.add_argument("--prerequisite")
    dependency_update.add_argument("--dependent")
    dependency_update.add_argument("--reason")
    dependency_update.add_argument("--scope", choices=("current-milestone", "project"))
    dependency_update.add_argument("--status", choices=("active", "inactive"))
    dependency_update.add_argument("--dry-run", action="store_true")
    dependency_update.add_argument("--json", action="store_true")
    dependency_update.add_argument("--yes", action="store_true")

    dependency_deactivate = dependency_subparsers.add_parser(
        "deactivate", help="deactivate a dependency without deleting history"
    )
    dependency_deactivate.add_argument("dependency_id")
    _add_root_argument(dependency_deactivate)
    dependency_deactivate.add_argument("--reason")
    dependency_deactivate.add_argument("--dry-run", action="store_true")
    dependency_deactivate.add_argument("--json", action="store_true")
    dependency_deactivate.add_argument("--yes", action="store_true")

    criterion_parser = subparsers.add_parser(
        "criterion", help="manage current-milestone success criteria"
    )
    criterion_subparsers = criterion_parser.add_subparsers(
        dest="criterion_command", required=True
    )
    criterion_add = criterion_subparsers.add_parser(
        "add", help="create a milestone criterion"
    )
    _add_root_argument(criterion_add)
    criterion_add.add_argument("--milestone")
    criterion_add.add_argument("--description")
    criterion_requirement = criterion_add.add_mutually_exclusive_group()
    criterion_requirement.add_argument(
        "--required", dest="required", action="store_true"
    )
    criterion_requirement.add_argument(
        "--optional", dest="required", action="store_false"
    )
    criterion_add.set_defaults(required=None)
    criterion_add.add_argument("--completion-condition")
    criterion_add.add_argument("--verification-method")
    criterion_add.add_argument(
        "--verification-policy",
        choices=(
            "observed-player-behavior",
            "observed-runtime",
            "automated-test",
            "document-review",
            "source-review",
            "manual-approval",
            "mixed",
        ),
    )
    criterion_add.add_argument("--issue", action="append", default=[])
    criterion_add.add_argument("--decision", action="append", default=[])
    criterion_add.add_argument("--evidence", action="append", default=[])
    criterion_add.add_argument("--dry-run", action="store_true")
    criterion_add.add_argument("--json", action="store_true")
    criterion_add.add_argument("--yes", action="store_true")

    criterion_list = criterion_subparsers.add_parser(
        "list", help="list milestone criteria"
    )
    _add_root_argument(criterion_list)
    criterion_list.add_argument("--milestone")
    criterion_filter = criterion_list.add_mutually_exclusive_group()
    criterion_filter.add_argument(
        "--required", dest="required_filter", action="store_true"
    )
    criterion_filter.add_argument(
        "--optional", dest="required_filter", action="store_false"
    )
    criterion_list.set_defaults(required_filter=None)
    criterion_list.add_argument("--support-status")
    criterion_list.add_argument("--lifecycle-status", choices=("active", "retired"))
    criterion_view = criterion_list.add_mutually_exclusive_group()
    criterion_view.add_argument("--active", action="store_true")
    criterion_view.add_argument("--all", action="store_true")
    criterion_list.add_argument("--json", action="store_true")

    criterion_show = criterion_subparsers.add_parser(
        "show", help="show one milestone criterion"
    )
    criterion_show.add_argument("criterion_id")
    _add_root_argument(criterion_show)
    criterion_show.add_argument("--json", action="store_true")

    criterion_update = criterion_subparsers.add_parser(
        "update", help="update a milestone criterion definition"
    )
    criterion_update.add_argument("criterion_id")
    _add_root_argument(criterion_update)
    criterion_update.add_argument("--milestone")
    criterion_update.add_argument("--description")
    criterion_update_requirement = criterion_update.add_mutually_exclusive_group()
    criterion_update_requirement.add_argument(
        "--required", dest="required", action="store_true"
    )
    criterion_update_requirement.add_argument(
        "--optional", dest="required", action="store_false"
    )
    criterion_update.set_defaults(required=None)
    criterion_update.add_argument("--completion-condition")
    criterion_update.add_argument("--verification-method")
    criterion_update.add_argument(
        "--verification-policy",
        choices=(
            "observed-player-behavior",
            "observed-runtime",
            "automated-test",
            "document-review",
            "source-review",
            "manual-approval",
            "mixed",
        ),
    )
    criterion_update.add_argument("--add-issue", action="append", default=[])
    criterion_update.add_argument("--remove-issue", action="append", default=[])
    criterion_update.add_argument("--add-decision", action="append", default=[])
    criterion_update.add_argument("--remove-decision", action="append", default=[])
    criterion_update.add_argument("--add-evidence", action="append", default=[])
    criterion_update.add_argument("--remove-evidence", action="append", default=[])
    criterion_update.add_argument("--dry-run", action="store_true")
    criterion_update.add_argument("--json", action="store_true")
    criterion_update.add_argument("--yes", action="store_true")

    criterion_evaluate = criterion_subparsers.add_parser(
        "evaluate", help="record an explicit criterion evaluation"
    )
    criterion_evaluate.add_argument("criterion_id")
    _add_root_argument(criterion_evaluate)
    criterion_evaluate.add_argument("--support")
    criterion_evaluate.add_argument("--reason")
    criterion_evaluate.add_argument("--evidence", action="append", default=[])
    criterion_evaluate.add_argument("--issue", action="append", default=[])
    criterion_evaluate.add_argument("--decision", action="append", default=[])
    criterion_evaluate.add_argument("--limitation", action="append", default=[])
    criterion_evaluate.add_argument("--dry-run", action="store_true")
    criterion_evaluate.add_argument("--json", action="store_true")
    criterion_evaluate.add_argument("--yes", action="store_true")

    criterion_retire = criterion_subparsers.add_parser(
        "retire", help="retire a criterion without deleting history"
    )
    criterion_retire.add_argument("criterion_id")
    _add_root_argument(criterion_retire)
    criterion_retire.add_argument("--reason")
    criterion_retire.add_argument("--dry-run", action="store_true")
    criterion_retire.add_argument("--json", action="store_true")
    criterion_retire.add_argument("--yes", action="store_true")

    path_parser = subparsers.add_parser(
        "path", help="calculate and inspect the milestone critical path"
    )
    path_subparsers = path_parser.add_subparsers(dest="path_command", required=True)
    path_calculate = path_subparsers.add_parser(
        "calculate", help="calculate the dependency-aware milestone path"
    )
    _add_root_argument(path_calculate)
    path_calculate.add_argument("--milestone")
    path_calculate.add_argument("--include", action="append", default=[])
    path_calculate.add_argument("--exclude", action="append", default=[])
    path_calculate.add_argument("--exclude-reason")
    path_calculate.add_argument("--max-items", type=int, default=7)
    path_calculate.add_argument("--dry-run", action="store_true")
    path_calculate.add_argument("--json", action="store_true")
    path_calculate.add_argument("--yes", action="store_true")

    path_show = path_subparsers.add_parser(
        "show", help="show the current milestone path"
    )
    _add_root_argument(path_show)
    path_show.add_argument("--all", action="store_true")
    path_show.add_argument("--json", action="store_true")

    path_explain = path_subparsers.add_parser(
        "explain", help="explain why one item gates the milestone"
    )
    path_explain.add_argument("path_item_id")
    _add_root_argument(path_explain)
    path_explain.add_argument("--json", action="store_true")

    path_check = path_subparsers.add_parser(
        "check", help="check whether the current path is stale"
    )
    _add_root_argument(path_check)
    path_check.add_argument("--json", action="store_true")
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


def _format_bootstrap_result(result: MutationResult) -> str:
    details = result.details
    changed = details["created_count"] + details["updated_count"]
    lines: list[str] = []
    if result.dry_run:
        lines.extend(
            [
                "Dry run — no files were written.",
                "",
                "Proposed Practical Game Studio scaffold.",
            ]
        )
    elif changed == 0:
        lines.append("Practical Game Studio project scaffold is already present.")
    else:
        lines.append("Practical Game Studio project scaffold created.")
    lines.extend(
        [
            "",
            "Root:",
            details["root"],
            "",
            (
                f"Files to create: {details['created_count']}"
                if result.dry_run
                else f"Files created: {details['created_count']}"
            ),
            (
                f"Files to update: {details['updated_count']}"
                if result.dry_run
                else f"Files updated: {details['updated_count']}"
            ),
            (
                f"Files to preserve: {details['preserved_count']}"
                if result.dry_run
                else f"Files preserved: {details['preserved_count']}"
            ),
            f"Conflicts: {details['conflict_count']}",
            "",
            "Project state:",
            "Initialized" if details["initialized"] else "Not initialized",
        ]
    )
    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(
        [
            "",
            "Recommended next command:",
            details["recommended_next_command"],
        ]
    )
    return "\n".join(lines)


def _run_bootstrap(args: argparse.Namespace, root: Path) -> int:
    def run(acknowledged: bool) -> MutationResult:
        return BootstrapService(root).bootstrap(
            BootstrapRequest(
                name=args.name,
                engine=args.engine,
                engine_version=args.engine_version,
                platform=args.platform,
                genre=args.genre,
                review_mode=args.review_mode,
                force=args.force,
                dry_run=args.dry_run,
                acknowledged=acknowledged,
            )
        )

    try:
        result = run(args.yes)
    except BootstrapError as exc:
        if exc.stage != "confirmation" or args.json or not sys.stdin.isatty():
            raise
        answer = input(
            "Replace conflicting framework-managed files while preserving "
            "project state and reports? [y/N]: "
        ).strip()
        if answer.casefold() not in {"y", "yes"}:
            print("studio bootstrap: forced refresh cancelled.", file=sys.stderr)
            return 2
        result = run(True)
    if args.json:
        _print_json(_mutation_envelope(result))
    else:
        print(_format_bootstrap_result(result))
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


def _parse_decision_option(spec: str, index: int) -> DecisionOption:
    parts = [part.strip() for part in spec.split("|")]
    if len(parts) < 3 or len(parts) > 6:
        raise DecisionInputError(
            "option specs use "
            "'OPT-ID|Label|Description|benefit1,benefit2|risk1,risk2|effort'"
        )
    while len(parts) < 6:
        parts.append("")
    option_id = parts[0] or f"OPT-{chr(ord('A') + index)}"
    benefits = tuple(item.strip() for item in parts[3].split(",") if item.strip())
    risks = tuple(item.strip() for item in parts[4].split(",") if item.strip())
    return DecisionOption(
        id=option_id,
        label=parts[1],
        description=parts[2],
        benefits=benefits,
        risks=risks,
        effort=parts[5] or None,
    )


def _decision_create_request(args: argparse.Namespace) -> DecisionCreateRequest:
    interactive = sys.stdin.isatty() and not args.json
    required = {
        "question": (args.question, "--question", "Decision question: "),
        "context": (args.context, "--context", "Decision context: "),
    }
    values: dict[str, str] = {}
    missing: list[str] = []
    for name, (value, flag, prompt) in required.items():
        if value is not None and value.strip():
            values[name] = value
        elif interactive:
            values[name] = input(prompt)
        else:
            missing.append(flag)

    specs = list(args.option)
    if interactive:
        while len(specs) < 2:
            specs.append(input(f"Option {len(specs) + 1} (OPT-ID|Label|Description): "))
    elif len(specs) < 2:
        missing.append("at least two --option values")

    recommended = args.recommended_option
    if recommended is None or not recommended.strip():
        if interactive:
            recommended = input("Recommended option ID: ")
        else:
            missing.append("--recommended-option")
    reason = args.recommendation_reason
    if reason is None or not reason.strip():
        if interactive:
            reason = input("Recommendation reason: ")
        else:
            missing.append("--recommendation-reason")
    if missing:
        raise DecisionInputError("missing required values: " + ", ".join(missing))

    options = tuple(
        _parse_decision_option(spec, index) for index, spec in enumerate(specs)
    )
    return DecisionCreateRequest(
        question=values["question"],
        context=values["context"],
        options=options,
        recommended_option=recommended or "",
        recommendation_reason=reason or "",
        phase=args.phase,
        milestone=args.milestone,
        urgency=args.urgency or "medium",
        decision_owner=args.owner or "user",
        decision_required_by=args.required_by,
        affected_issues=tuple(args.issue),
        supporting_evidence=tuple(args.evidence),
        trade_offs=tuple(args.trade_off),
        revisit_condition=args.revisit_condition,
        status=args.status or "open",
    )


def _decision_recommended_option(record: dict[str, Any]) -> dict[str, Any]:
    return next(
        option
        for option in record["options"]
        if option["id"] == record["recommended_option"]
    )


def _format_decision_summary(record: dict[str, Any]) -> str:
    recommended = _decision_recommended_option(record)
    lines = [
        f"ID: {record['id']}",
        f"Status: {record['status'].title()}",
        f"Urgency: {record['urgency'].title()}",
        "",
        "Question:",
        record["question"],
        "",
        "Recommended option:",
        f"{recommended['id']} — {recommended['label']}",
        "",
        (
            f"Evidence support: {record['evidence_support']['level'].title()}"
            if record["supporting_evidence"]
            else "Evidence support: None recorded"
        ),
    ]
    if record["supporting_evidence"]:
        lines.extend(f"- {item}" for item in record["supporting_evidence"])
    if record["affected_issues"]:
        lines.extend(["", "Affected issues:"])
        lines.extend(f"- {item}" for item in record["affected_issues"])
    if record["trade_offs"]:
        lines.extend(["", "Trade-offs:"])
        lines.extend(f"- {item}" for item in record["trade_offs"])
    return "\n".join(lines)


def _confirm_decision_write(
    *,
    root: Path,
    args: argparse.Namespace,
    preview: str,
    action: str,
) -> None:
    if args.dry_run:
        return
    review_mode = StateRepository(root).load_project()["review_mode"]
    if review_mode == "fast" or args.yes:
        return
    if sys.stdin.isatty() and not args.json:
        print(preview)
        answer = input(f"\n{action}? [y/N]: ").strip().casefold()
        if answer not in {"y", "yes"}:
            raise DecisionInputError(f"decision {action.casefold()} cancelled")
        return
    raise DecisionInputError(
        f"{review_mode} review mode requires --yes in a non-interactive terminal"
    )


def _run_decision_add(args: argparse.Namespace, root: Path) -> int:
    service = DecisionService(root)
    request = _decision_create_request(args)
    preview = service.preview_decision(request)
    _confirm_decision_write(
        root=root,
        args=args,
        preview=f"Proposed decision.\n\n{_format_decision_summary(preview)}",
        action="Create this decision",
    )
    result = service.create_decision(request, dry_run=args.dry_run)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    decision = result.details["decision"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed decision.")
    else:
        print("Decision created.")
    print(f"\n{_format_decision_summary(decision)}")
    if result.dry_run:
        print(
            f"\nAffected files: {len(result.changed_files)}\n"
            f"Reports rendered for validation: {result.report_summary['rendered']}"
        )
    else:
        print(f"\nReports regenerated: {result.report_summary['rendered']}")
    print(
        f"\nRecommended next workflow:\n{result.details['recommended_next_workflow']}"
    )
    return 0


def _run_decision_list(args: argparse.Namespace, root: Path) -> int:
    records = DecisionService(root).list_decisions(
        status=args.status,
        urgency=args.urgency,
        owner=args.owner,
        phase=args.phase,
        issue_id=args.issue,
        evidence_id=args.evidence,
        pending=args.pending,
        resolved=args.resolved,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="decision.list",
                data={"count": len(records), "decisions": records},
            )
        )
        return 0
    if not records:
        print("No matching decisions.")
        return 0
    label = (
        "Decisions"
        if args.all or args.status
        else "Resolved decisions"
        if args.resolved
        else "Pending decisions"
    )
    print(f"{label}: {len(records)}\n")
    print(f"{'ID':<10}{'Urgency':<10}{'Status':<11}{'Owner':<18}Question")
    for record in records:
        print(
            f"{record['id']:<10}{record['urgency'].title():<10}"
            f"{record['status'].title():<11}{record['decision_owner']:<18}"
            f"{record['question']}"
        )
    return 0


def _format_decision_detail(record: dict[str, Any]) -> str:
    lines = [
        f"ID: {record['id']}",
        f"Status: {record['status'].title()}",
        f"Urgency: {record['urgency'].title()}",
        f"Owner: {record['decision_owner']}",
        f"Phase: {record['phase']}",
        f"Milestone: {record['milestone']}",
        "",
        "Question:",
        record["question"],
        "",
        "Context:",
        record["context"],
        "",
        "Options:",
    ]
    for option in record["options"]:
        lines.extend(
            [
                f"- {option['id']} — {option['label']}",
                f"  {option['description']}",
            ]
        )
        if option["benefits"]:
            lines.append(f"  Benefits: {'; '.join(option['benefits'])}")
        if option["risks"]:
            lines.append(f"  Risks: {'; '.join(option['risks'])}")
        if option["effort"]:
            lines.append(f"  Effort: {option['effort']}")
    recommended = _decision_recommended_option(record)
    lines.extend(
        [
            "",
            "Recommended option:",
            f"{recommended['id']} — {recommended['label']}",
            "",
            "Recommendation reason:",
            record["recommendation_reason"],
            "",
            (
                f"Evidence support: {record['evidence_support']['level'].title()}"
                if record["supporting_evidence"]
                else "Evidence support: None recorded"
            ),
        ]
    )
    classifications = record["evidence_support"]["classifications"]
    if record["supporting_evidence"]:
        lines.extend(["", "Supporting evidence:"])
        lines.extend(f"- {item}" for item in record["supporting_evidence"])
        lines.append(
            "Classifications: "
            + ", ".join(f"{key}={value}" for key, value in classifications.items())
        )
    sections = (
        ("Trade-offs", record["trade_offs"]),
        ("Affected issues", record["affected_issues"]),
        ("Consequences", record["consequences"]),
        ("Follow-up actions", record["follow_up_actions"]),
    )
    for heading, values in sections:
        if values:
            lines.extend(["", f"{heading}:"])
            lines.extend(f"- {item}" for item in values)
    scalars = (
        ("Required by", record["decision_required_by"]),
        ("Final decision", record["final_decision"]),
        ("Decision reason", record["decision_reason"]),
        ("Revisit condition", record["revisit_condition"]),
        ("Resolved at", record["resolved_at"]),
        ("Supersedes", record["supersedes"]),
        ("Superseded by", ", ".join(record.get("superseded_by", [])) or None),
    )
    for heading, value in scalars:
        if value:
            lines.extend(["", f"{heading}:", str(value)])
    if record["recommendation_followed"] is not None:
        value = "Followed" if record["recommendation_followed"] else "Overridden"
        lines.extend(["", "Recommendation:", value])
    if record["resolution_history"]:
        lines.extend(["", "Resolution history:"])
        for item in record["resolution_history"]:
            recommendation = (
                "followed" if item["recommendation_followed"] else "overridden"
            )
            lines.extend(
                [
                    f"- {item['resolved_at']}: {item['final_decision']}",
                    f"  Reason: {item['decision_reason']}",
                    f"  Recommendation: {recommendation}",
                ]
            )
    lines.extend(
        [
            "",
            f"Created: {record['created_at']}",
            f"Updated: {record['updated_at']}",
        ]
    )
    return "\n".join(lines)


def _run_decision_show(args: argparse.Namespace, root: Path) -> int:
    record = DecisionService(root).get_decision(args.decision_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="decision.show",
                data={"decision": record},
            )
        )
    else:
        print(_format_decision_detail(record))
    return 0


def _decision_patch(args: argparse.Namespace) -> DecisionPatch:
    values: dict[str, Any] = {}
    for argument, field_name in (
        ("question", "question"),
        ("context", "context"),
        ("phase", "phase"),
        ("milestone", "milestone"),
        ("urgency", "urgency"),
        ("owner", "decision_owner"),
        ("required_by", "decision_required_by"),
        ("status", "status"),
        ("recommended_option", "recommended_option"),
        ("recommendation_reason", "recommendation_reason"),
        ("revisit_condition", "revisit_condition"),
    ):
        value = getattr(args, argument)
        if value is not None:
            values[field_name] = value
    return DecisionPatch(
        values=values,
        add_trade_offs=tuple(args.add_trade_off),
        remove_trade_offs=tuple(args.remove_trade_off),
        add_issues=tuple(args.add_issue),
        remove_issues=tuple(args.remove_issue),
        add_evidence=tuple(args.add_evidence),
        remove_evidence=tuple(args.remove_evidence),
        add_options=tuple(
            _parse_decision_option(spec, index)
            for index, spec in enumerate(args.add_option)
        ),
        update_options=tuple(
            _parse_decision_option(spec, index)
            for index, spec in enumerate(args.update_option)
        ),
        remove_options=tuple(args.remove_option),
        supersedes=args.supersedes,
    )


def _run_decision_update(args: argparse.Namespace, root: Path) -> int:
    result = DecisionService(root).update_decision(
        args.decision_id,
        _decision_patch(args),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["decision"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed decision update.")
    elif result.details["no_op"]:
        print("Decision unchanged.")
    else:
        print("Decision updated.")
    print(f"\nID: {record['id']}\nStatus: {record['status'].title()}")
    if result.changed_fields:
        print("Changed fields:")
        for field_name in result.changed_fields:
            print(f"- {field_name}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    regenerated = (
        result.report_summary["rendered"]
        if result.dry_run or not result.details["no_op"]
        else 0
    )
    label = (
        "Reports rendered for validation" if result.dry_run else "Reports regenerated"
    )
    print(f"\n{label}: {regenerated}")
    return 0


def _run_decision_resolve(args: argparse.Namespace, root: Path) -> int:
    if not args.reason or not args.reason.strip():
        raise DecisionInputError("missing required value: --reason")
    if (args.option is None) == (args.custom_decision is None):
        raise DecisionInputError("provide exactly one of --option or --custom-decision")
    service = DecisionService(root)
    current = service.get_decision(args.decision_id)
    choice = args.option or args.custom_decision
    _confirm_decision_write(
        root=root,
        args=args,
        preview=(
            f"Resolve {current['id']} — {current['question']}\n\n"
            f"Selected resolution: {choice}\nReason: {args.reason}"
        ),
        action="Resolve this decision",
    )
    result = service.resolve_decision(
        args.decision_id,
        DecisionResolution(
            option_id=args.option,
            custom_decision=args.custom_decision,
            reason=args.reason,
            consequences=tuple(args.consequence),
            follow_up_actions=tuple(args.follow_up),
            revisit_condition=args.revisit_condition,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["decision"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed decision resolution.")
    else:
        print("Decision resolved.")
    selected_label = (
        "Selected option" if record["final_option_id"] else "Custom decision"
    )
    print(f"\nID: {record['id']}\n{selected_label}:\n{record['final_decision']}")
    recommendation = "Followed" if record["recommendation_followed"] else "Overridden"
    print(f"\nRecommendation:\n{recommendation}")
    print(f"\nReason:\n{record['decision_reason']}")
    if record["follow_up_actions"]:
        print("\nFollow-up actions:")
        for action in record["follow_up_actions"]:
            print(f"- {action}")
    label = (
        "Reports rendered for validation" if result.dry_run else "Reports regenerated"
    )
    print(f"\n{label}: {result.report_summary['rendered']}")
    print(
        f"\nRecommended next workflow:\n{result.details['recommended_next_workflow']}"
    )
    return 0


def _run_decision(args: argparse.Namespace, root: Path) -> int:
    if args.decision_command == "add":
        return _run_decision_add(args, root)
    if args.decision_command == "list":
        return _run_decision_list(args, root)
    if args.decision_command == "show":
        return _run_decision_show(args, root)
    if args.decision_command == "update":
        return _run_decision_update(args, root)
    if args.decision_command == "resolve":
        return _run_decision_resolve(args, root)
    raise DecisionInputError(f"unknown decision command {args.decision_command}")


def _confirm_structural_write(
    args: argparse.Namespace,
    root: Path,
    *,
    prompt: str,
    error_type: type[ValueError],
) -> None:
    if args.dry_run:
        return
    review_mode = StateRepository(root).load_project()["review_mode"]
    if review_mode == "fast" or args.yes:
        return
    if sys.stdin.isatty() and not args.json:
        answer = input(f"{prompt} [y/N]: ").strip().casefold()
        if answer in {"y", "yes"}:
            return
        raise error_type("operation cancelled")
    raise error_type(
        f"{review_mode} review mode requires --yes in a non-interactive terminal"
    )


def _required_values(
    values: Sequence[tuple[str | None, str]], error_type: type[ValueError]
) -> None:
    missing = [flag for value, flag in values if value is None or not value.strip()]
    if missing:
        raise error_type("missing required values: " + ", ".join(missing))


def _path_impact_lines(details: dict[str, Any]) -> list[str]:
    impact = details.get("path_impact", "may-be-stale")
    if impact == "stale":
        message = "The current milestone critical path is stale."
    elif impact == "none":
        message = "The current milestone critical path was not changed."
    else:
        message = "The current milestone critical path may be stale."
    return [
        "",
        "Critical-path impact:",
        message,
        "",
        "Recommended next command:",
        details.get("recommended_next_command", "studio path check"),
    ]


def _run_dependency_add(args: argparse.Namespace, root: Path) -> int:
    _required_values(
        (
            (args.prerequisite, "--prerequisite"),
            (args.dependent, "--dependent"),
            (args.reason, "--reason"),
        ),
        DependencyInputError,
    )
    _confirm_structural_write(
        args,
        root,
        prompt="Create this explicit dependency?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).create_dependency(
        DependencyCreateRequest(
            prerequisite=args.prerequisite,
            dependent=args.dependent,
            reason=args.reason,
            scope=args.scope,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    record = result.details["dependency"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed dependency.")
    elif result.details["reactivated"]:
        print("Dependency reactivated.")
    else:
        print("Dependency created.")
    print(
        f"\nID: {record['id']}\n\nPrerequisite:\n{record['prerequisite']}"
        f"\n\nDependent:\n{record['dependent']}\n\nRelationship:\n"
        f"{record['dependent']} requires {record['prerequisite']}\n\nReason:\n"
        f"{record['reason']}"
    )
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_dependency_list(args: argparse.Namespace, root: Path) -> int:
    if args.active and args.status == "inactive":
        raise DependencyInputError("--active cannot be combined with inactive status")
    records = DependencyService(root).list_dependencies(
        status="active" if args.active else args.status,
        source=args.source,
        prerequisite=args.prerequisite,
        dependent=args.dependent,
        scope=args.scope,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="dependency.list",
                data={"count": len(records), "dependencies": records},
            )
        )
        return 0
    if not records:
        print("No matching dependencies.")
        return 0
    if args.all:
        label = "Dependencies"
    elif args.status == "inactive":
        label = "Inactive dependencies"
    else:
        label = "Active dependencies"
    print(f"{label}: {len(records)}\n")
    print(f"{'ID':<10}{'Prerequisite':<14}{'Dependent':<14}Scope")
    for record in records:
        print(
            f"{record['id']:<10}{record['prerequisite']:<14}"
            f"{record['dependent']:<14}"
            f"{record['scope'].replace('-', ' ').title()}"
        )
    return 0


def _format_dependency_detail(record: dict[str, Any]) -> str:
    prerequisite_state = {
        "active-unsatisfied": "Active and unsatisfied",
        "satisfied": "Satisfied",
        "terminal-unsatisfied": "Terminal but unsatisfied",
        "invalid-or-missing": "Invalid or missing",
    }[record["prerequisite_state"]]
    lines = [
        f"ID: {record['id']}",
        f"Status: {record['status'].title()}",
        f"Prerequisite: {record['prerequisite']}",
        f"Dependent: {record['dependent']}",
        f"Relationship: {record['dependent']} requires {record['prerequisite']}",
        f"Scope: {record['scope'].replace('-', ' ').title()}",
        f"Prerequisite state: {prerequisite_state}",
        f"Prerequisite source status: {record['prerequisite_status']}",
        f"Prerequisite satisfied: {'Yes' if record['prerequisite_satisfied'] else 'No'}",
        f"Critical-path presence: {'Yes' if record['on_critical_path'] else 'No'}",
        "",
        "Satisfaction reason:",
        record["prerequisite_satisfaction_reason"],
        "",
        "Reason:",
        record["reason"],
    ]
    for heading, values in (
        ("Upstream", record["upstream"]),
        ("Downstream", record["downstream"]),
    ):
        lines.extend(["", f"{heading}:"])
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- None")
    if record["deactivation_reason"]:
        lines.extend(["", "Deactivation reason:", record["deactivation_reason"]])
    lines.extend(
        [
            "",
            f"Created: {record['created_at']}",
            f"Updated: {record['updated_at']}",
        ]
    )
    return "\n".join(lines)


def _run_dependency_show(args: argparse.Namespace, root: Path) -> int:
    record = DependencyService(root).get_dependency(args.dependency_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="dependency.show",
                data={"dependency": record},
            )
        )
    else:
        print(_format_dependency_detail(record))
    return 0


def _run_dependency_update(args: argparse.Namespace, root: Path) -> int:
    _confirm_structural_write(
        args,
        root,
        prompt=f"Update {args.dependency_id}?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).update_dependency(
        args.dependency_id,
        DependencyPatch(
            prerequisite=args.prerequisite,
            dependent=args.dependent,
            reason=args.reason,
            scope=args.scope,
            status=args.status,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed dependency update.")
    elif result.details["no_op"]:
        print("Dependency unchanged.")
    else:
        print("Dependency updated.")
    print(f"\nID: {result.details['dependency']['id']}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_dependency_deactivate(args: argparse.Namespace, root: Path) -> int:
    _required_values(((args.reason, "--reason"),), DependencyInputError)
    _confirm_structural_write(
        args,
        root,
        prompt=f"Deactivate {args.dependency_id}?",
        error_type=DependencyInputError,
    )
    result = DependencyService(root).deactivate_dependency(
        args.dependency_id, args.reason, dry_run=args.dry_run
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    print(
        "Dry run — no files were written.\n\nProposed dependency deactivation."
        if result.dry_run
        else "Dependency deactivated."
    )
    print(f"\nID: {result.details['dependency']['id']}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_dependency(args: argparse.Namespace, root: Path) -> int:
    if args.dependency_command == "add":
        return _run_dependency_add(args, root)
    if args.dependency_command == "list":
        return _run_dependency_list(args, root)
    if args.dependency_command == "show":
        return _run_dependency_show(args, root)
    if args.dependency_command == "update":
        return _run_dependency_update(args, root)
    if args.dependency_command == "deactivate":
        return _run_dependency_deactivate(args, root)
    raise DependencyInputError(f"unknown dependency command {args.dependency_command}")


def _criterion_create_request(args: argparse.Namespace) -> CriterionCreateRequest:
    _required_values(
        (
            (args.description, "--description"),
            (args.completion_condition, "--completion-condition"),
            (args.verification_policy, "--verification-policy"),
        ),
        CriterionInputError,
    )
    if args.required is None:
        raise CriterionInputError("choose exactly one of --required or --optional")
    return CriterionCreateRequest(
        description=args.description,
        required=args.required,
        completion_condition=args.completion_condition,
        verification_policy=args.verification_policy,
        milestone=args.milestone,
        verification_method=args.verification_method,
        related_issues=tuple(args.issue),
        related_decisions=tuple(args.decision),
        supporting_evidence=tuple(args.evidence),
    )


def _run_criterion_add(args: argparse.Namespace, root: Path) -> int:
    request = _criterion_create_request(args)
    _confirm_structural_write(
        args,
        root,
        prompt="Create this milestone criterion?",
        error_type=CriterionInputError,
    )
    result = CriterionService(root).create_criterion(request, dry_run=args.dry_run)
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    criterion = result.details["criterion"]
    print(
        "Dry run — no files were written.\n\nProposed milestone criterion."
        if result.dry_run
        else "Milestone criterion created."
    )
    print(
        f"\nID: {criterion['id']}\nRequired: "
        f"{'Yes' if criterion['required'] else 'No'}\nSupport: "
        f"{criterion['support_status'].replace('-', ' ').title()}\n"
        f"Verification policy: "
        f"{criterion['verification_policy'].replace('-', ' ').title()}\n\n"
        f"Criterion:\n{criterion['description']}\n\nCompletion condition:\n"
        f"{criterion['completion_condition']}"
    )
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_criterion_list(args: argparse.Namespace, root: Path) -> int:
    records = CriterionService(root).list_criteria(
        milestone=args.milestone,
        required=args.required_filter,
        support_status=args.support_status,
        lifecycle_status="active" if args.active else args.lifecycle_status,
        include_all=args.all,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="criterion.list",
                data={"count": len(records), "criteria": records},
            )
        )
        return 0
    if not records:
        print("No matching milestone criteria.")
        return 0
    print(f"Current milestone criteria: {len(records)}\n")
    print(f"{'ID':<9}{'Required':<10}{'Support':<22}Criterion")
    for criterion in records:
        print(
            f"{criterion['id']:<9}"
            f"{('Yes' if criterion['required'] else 'No'):<10}"
            f"{criterion['support_status'].replace('-', ' ').title():<22}"
            f"{criterion['description']}"
        )
    return 0


def _format_criterion_detail(criterion: dict[str, Any]) -> str:
    lines = [
        f"ID: {criterion['id']}",
        f"Milestone: {criterion['milestone']}",
        f"Required: {'Yes' if criterion['required'] else 'No'}",
        f"Lifecycle: {criterion['lifecycle_status'].title()}",
        f"Support: {criterion['support_status'].replace('-', ' ').title()}",
        (
            "Verification policy: "
            f"{criterion['verification_policy'].replace('-', ' ').title()}"
        ),
        f"Evaluation freshness: {criterion['evaluation_freshness']['status'].title()}",
        f"Critical-path presence: {'Yes' if criterion['on_critical_path'] else 'No'}",
        "",
        "Criterion:",
        criterion["description"],
        "",
        "Completion condition:",
        criterion["completion_condition"],
    ]
    if criterion["verification_method"]:
        lines.extend(["", "Verification method:", criterion["verification_method"]])
    for heading, values in (
        ("Supporting evidence", criterion["evidence_details"]),
        ("Related issues", criterion["related_issues"]),
        ("Related decisions", criterion["related_decisions"]),
        ("Limitations", criterion["evaluation_limitations"]),
    ):
        if not values:
            continue
        lines.extend(["", f"{heading}:"])
        for value in values:
            if isinstance(value, dict):
                lines.append(
                    f"- {value['id']} [{value['classification']}/{value['status']}]"
                )
            else:
                lines.append(f"- {value}")
    if criterion["evaluation_reason"]:
        lines.extend(["", "Latest evaluation reason:", criterion["evaluation_reason"]])
    if criterion["evaluation_history"]:
        lines.extend(["", "Evaluation history:"])
        for entry in criterion["evaluation_history"]:
            lines.append(
                f"- {entry['evaluated_at']}: {entry['support_status']} — "
                f"{entry['reason']}"
            )
    if criterion["retirement_reason"]:
        lines.extend(["", "Retirement reason:", criterion["retirement_reason"]])
    lines.extend(
        [
            "",
            f"Created: {criterion['created_at']}",
            f"Updated: {criterion['updated_at']}",
        ]
    )
    if criterion["evaluated_at"]:
        lines.append(f"Evaluated: {criterion['evaluated_at']}")
    return "\n".join(lines)


def _run_criterion_show(args: argparse.Namespace, root: Path) -> int:
    criterion = CriterionService(root).get_criterion(args.criterion_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="criterion.show",
                data={"criterion": criterion},
            )
        )
    else:
        print(_format_criterion_detail(criterion))
    return 0


def _criterion_patch(args: argparse.Namespace) -> CriterionPatch:
    values: dict[str, Any] = {}
    for argument, field_name in (
        ("milestone", "milestone"),
        ("description", "description"),
        ("completion_condition", "completion_condition"),
        ("verification_method", "verification_method"),
        ("verification_policy", "verification_policy"),
    ):
        value = getattr(args, argument)
        if value is not None:
            values[field_name] = value
    if args.required is not None:
        values["required"] = args.required
    return CriterionPatch(
        values=values,
        add_issues=tuple(args.add_issue),
        remove_issues=tuple(args.remove_issue),
        add_decisions=tuple(args.add_decision),
        remove_decisions=tuple(args.remove_decision),
        add_evidence=tuple(args.add_evidence),
        remove_evidence=tuple(args.remove_evidence),
    )


def _run_criterion_update(args: argparse.Namespace, root: Path) -> int:
    _confirm_structural_write(
        args,
        root,
        prompt=f"Update {args.criterion_id}?",
        error_type=CriterionInputError,
    )
    result = CriterionService(root).update_criterion(
        args.criterion_id, _criterion_patch(args), dry_run=args.dry_run
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed criterion update.")
    elif result.details["no_op"]:
        print("Milestone criterion unchanged.")
    else:
        print("Milestone criterion updated.")
    print(f"\nID: {result.details['criterion']['id']}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_criterion_evaluate(args: argparse.Namespace, root: Path) -> int:
    _required_values(
        ((args.support, "--support"), (args.reason, "--reason")),
        CriterionInputError,
    )
    _confirm_structural_write(
        args,
        root,
        prompt=f"Record this evaluation for {args.criterion_id}?",
        error_type=CriterionInputError,
    )
    result = CriterionService(root).evaluate_criterion(
        args.criterion_id,
        CriterionEvaluation(
            support_status=args.support,
            reason=args.reason,
            evidence=tuple(args.evidence),
            issues=tuple(args.issue),
            decisions=tuple(args.decision),
            limitations=tuple(args.limitation),
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    criterion = result.details["criterion"]
    if result.dry_run:
        print("Dry run — no files were written.\n\nProposed criterion evaluation.")
    elif result.details["no_op"]:
        print("Milestone criterion evaluation is unchanged.")
    else:
        print("Milestone criterion evaluated.")
    print(
        f"\nID: {criterion['id']}\nSupport: "
        f"{criterion['support_status'].replace('-', ' ').title()}"
        f"\n\nReason:\n{criterion['evaluation_reason'] or args.reason}"
    )
    if criterion["evaluation_limitations"]:
        print("\nLimitations:")
        for limitation in criterion["evaluation_limitations"]:
            print(f"- {limitation}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_criterion_retire(args: argparse.Namespace, root: Path) -> int:
    _required_values(((args.reason, "--reason"),), CriterionInputError)
    _confirm_structural_write(
        args,
        root,
        prompt=f"Retire {args.criterion_id}?",
        error_type=CriterionInputError,
    )
    result = CriterionService(root).retire_criterion(
        args.criterion_id, args.reason, dry_run=args.dry_run
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    print(
        "Dry run — no files were written.\n\nProposed criterion retirement."
        if result.dry_run
        else "Milestone criterion retired."
    )
    print(f"\nID: {result.details['criterion']['id']}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    print("\n".join(_path_impact_lines(result.details)))
    return 0


def _run_criterion(args: argparse.Namespace, root: Path) -> int:
    if args.criterion_command == "add":
        return _run_criterion_add(args, root)
    if args.criterion_command == "list":
        return _run_criterion_list(args, root)
    if args.criterion_command == "show":
        return _run_criterion_show(args, root)
    if args.criterion_command == "update":
        return _run_criterion_update(args, root)
    if args.criterion_command == "evaluate":
        return _run_criterion_evaluate(args, root)
    if args.criterion_command == "retire":
        return _run_criterion_retire(args, root)
    raise CriterionInputError(f"unknown criterion command {args.criterion_command}")


def _confirm_path_calculation(args: argparse.Namespace, root: Path) -> None:
    if args.dry_run:
        return
    review_mode = StateRepository(root).load_project()["review_mode"]
    if review_mode == "fast" or args.yes:
        return
    if sys.stdin.isatty() and not args.json:
        answer = (
            input("Calculate and persist the proposed milestone critical path? [y/N]: ")
            .strip()
            .casefold()
        )
        if answer in {"y", "yes"}:
            return
        raise CriticalPathInputError("path calculation cancelled")
    raise CriticalPathInputError(
        f"{review_mode} review mode requires --yes in a non-interactive terminal"
    )


def _path_item_source(item: dict[str, Any]) -> str:
    return item.get("source_id") or item["source_key"]


def _recommended_type_label(item: dict[str, Any]) -> str:
    return {
        "decision": "Next required user decision",
        "issue": "Recommended implementation",
        "verification": "Recommended verification",
    }.get(item["type"], "Recommended action")


def _format_path_items(items: Sequence[dict[str, Any]]) -> str:
    if not items:
        return "No active milestone critical path.\nRun:\nstudio path calculate"
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item['id']} — {item['title']}",
                f"   Source: {_path_item_source(item)}",
                f"   Status: {item['status'].replace('-', ' ').title()}",
            ]
        )
        if item["dependencies"]:
            lines.append(f"   Depends on: {', '.join(item['dependencies'])}")
    return "\n".join(lines)


def _run_path_calculate(args: argparse.Namespace, root: Path) -> int:
    _confirm_path_calculation(args, root)
    result = CriticalPathService(root).apply_path(
        PathCalculationRequest(
            milestone=args.milestone,
            include=tuple(args.include),
            exclude=tuple(args.exclude),
            exclude_reason=args.exclude_reason,
            max_items=args.max_items,
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    details = result.details
    if result.dry_run:
        print("Dry run — no files were written.\n")
    if details["no_op"]:
        print("Milestone critical path is unchanged.")
    else:
        print("Milestone critical path calculated.")
    print(f"\nMilestone:\n{details['milestone']}")
    print(f"\nActive items: {details['active_count']}\n")
    print(_format_path_items(details["items"]))
    recommended = next(
        (
            item
            for item in details["items"]
            if item["id"] == details["recommended_next"]
        ),
        None,
    )
    print("\nRecommended next action:")
    print(
        f"{_recommended_type_label(recommended)}: "
        f"{recommended['id']} — {recommended['title']}"
        if recommended
        else "None identified."
    )
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    label = (
        "Reports rendered for validation" if result.dry_run else "Reports regenerated"
    )
    rendered = (
        result.report_summary["rendered"]
        if result.dry_run or not details["no_op"]
        else 0
    )
    print(f"\n{label}: {rendered}")
    return 0


def _run_path_show(args: argparse.Namespace, root: Path) -> int:
    data = CriticalPathService(root).show_path(include_history=args.all)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.show",
                data=data,
            )
        )
        return 0
    print(f"Current milestone:\n{data['milestone']}")
    print("\nMilestone critical path:\n")
    print(_format_path_items(data["items"]))
    if data["items"]:
        recommended = next(
            (item for item in data["items"] if item["id"] == data["recommended_next"]),
            None,
        )
        print("\nRecommended next action:")
        print(
            f"{_recommended_type_label(recommended)}: "
            f"{recommended['id']} — {recommended['title']}"
            if recommended
            else "None identified."
        )
    print("\nBlocked items:")
    print("\n".join(f"- {item}" for item in data["blocked_items"]) or "- None")
    print("\nManual inclusions:")
    print("\n".join(f"- {item}" for item in data["pinned_sources"]) or "- None")
    if data["excluded_sources"]:
        print("\nManual exclusions:")
        for source in data["excluded_sources"]:
            print(f"- {source}: {data['exclusion_reasons'][source]}")
    print("\nDo not work on yet:")
    for item in data["non_critical_work"]:
        print(f"- {item}")
    print(f"\nLast calculated: {data['calculated_at'] or 'Never'}")
    print(f"Freshness: {data['freshness']['status'].title()}")
    if args.all:
        print("\nCompleted and removed history:")
        history = data.get("history", [])
        if history:
            for item in history:
                print(f"- {item['id']} [{item['status']}] — {item['title']}")
        else:
            print("- None")
    return 0


def _run_path_explain(args: argparse.Namespace, root: Path) -> int:
    explanation = CriticalPathService(root).explain_item(args.path_item_id)
    data = explanation.to_dict()
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.explain",
                data=data,
            )
        )
        return 0
    item = data["item"]
    print(f"{item['id']} — {item['title']}")
    print(f"\nSource:\n{_path_item_source(item)}")
    print(f"\nSource state:\n{item['source_status']}")
    print(f"\nWhy this item is on the path:\n{item['reason']}")
    print(f"\nMilestone impact:\n{item['milestone_impact']}")
    print(f"\nPriority tier:\n{item['priority_tier']}")
    print("\nDependencies:")
    print("\n".join(f"- {value}" for value in item["dependencies"]) or "- None")
    print("\nPrerequisite states:")
    if data["dependency_states"]:
        labels = {
            "active-unsatisfied": "Active and unsatisfied",
            "satisfied": "Satisfied",
            "terminal-unsatisfied": "Terminal but unsatisfied",
            "invalid-or-missing": "Invalid or missing",
        }
        for dependency in data["dependency_states"]:
            dependency_label = dependency["dependency_id"] or "Derived relationship"
            print(
                f"- {dependency_label}: {dependency['prerequisite']}\n"
                f"  Prerequisite state: "
                f"{labels[dependency['prerequisite_state']]}\n"
                f"  {dependency['prerequisite_satisfaction_reason']}"
            )
    else:
        print("- None")
    print("\nDependency origin:")
    if item["dependency_origins"]:
        for origin in item["dependency_origins"]:
            if origin["origin"] == "explicit":
                print(f"- Explicit — {origin['dependency_id']}: {origin['reason']}")
            else:
                print(f"- Derived — {origin['reason']}")
    else:
        print("- None")
    print("\nBlocks:")
    print("\n".join(f"- {value}" for value in data["downstream_items"]) or "- None")
    print(f"\nEvidence state:\n{item['evidence_state']}")
    print(f"\nCompletion condition:\n{item['completion_condition']}")
    print(f"\nWhy delaying it delays the milestone:\n{item['milestone_impact']}")
    print("\nWhy lower-priority alternatives were not selected:")
    print(
        "\n".join(f"- {value}" for value in data["lower_priority_alternatives"])
        or "- No lower-priority milestone-gating alternative was identified."
    )
    if data["manual_context"]:
        print(f"\nManual context:\n{data['manual_context']}")
    source = data["source"]
    if source and str(item.get("source_id") or "").startswith("MC-"):
        print(f"\nCriterion:\n{source['description']}")
        print(f"\nCurrent support:\n{source['support_status']}")
        print(f"\nCriterion completion condition:\n{source['completion_condition']}")
        print(
            "\nCurrent evidence:\n"
            + (
                "\n".join(f"- {value}" for value in source["supporting_evidence"])
                or "- None"
            )
        )
        if source["evaluation_reason"]:
            print(f"\nEvaluation reason:\n{source['evaluation_reason']}")
    return 0


def _run_path_check(args: argparse.Namespace, root: Path) -> int:
    freshness = CriticalPathService(root).check_freshness()
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="path.check",
                data=freshness.to_dict(),
            )
        )
        return 0
    if freshness.status == "current":
        print("Critical path is current.")
        return 0
    if freshness.status == "absent":
        print("No active milestone critical path.")
        print("Run:\nstudio path calculate")
        return 0
    print("Critical path is stale.\n\nReasons:")
    for reason in freshness.reasons:
        print(f"- {reason}")
    print("\nRecommended action:\nstudio path calculate")
    return 0


def _run_path(args: argparse.Namespace, root: Path) -> int:
    if args.path_command == "calculate":
        return _run_path_calculate(args, root)
    if args.path_command == "show":
        return _run_path_show(args, root)
    if args.path_command == "explain":
        return _run_path_explain(args, root)
    if args.path_command == "check":
        return _run_path_check(args, root)
    raise CriticalPathInputError(f"unknown path command {args.path_command}")


def _operation(args: argparse.Namespace) -> str:
    if getattr(args, "command", None) == "bootstrap":
        return "project.bootstrap"
    if getattr(args, "command", None) == "framework":
        return f"framework.{getattr(args, 'framework_command', 'unknown')}"
    if getattr(args, "command", None) == "issue":
        return f"issue.{getattr(args, 'issue_command', 'unknown')}"
    if getattr(args, "command", None) == "evidence":
        return f"evidence.{getattr(args, 'evidence_command', 'unknown')}"
    if getattr(args, "command", None) == "decision":
        return f"decision.{getattr(args, 'decision_command', 'unknown')}"
    if getattr(args, "command", None) == "dependency":
        return f"dependency.{getattr(args, 'dependency_command', 'unknown')}"
    if getattr(args, "command", None) == "criterion":
        return f"criterion.{getattr(args, 'criterion_command', 'unknown')}"
    if getattr(args, "command", None) == "path":
        return f"path.{getattr(args, 'path_command', 'unknown')}"
    return getattr(args, "command", "studio")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "bootstrap":
            bootstrap_root = (
                args.root.expanduser().resolve()
                if args.root is not None
                else Path.cwd().resolve()
            )
            return _run_bootstrap(args, bootstrap_root)
        root = find_project_root(explicit=args.root)
        if args.command == "framework":
            result = validate_framework(root)
            if getattr(args, "json", False):
                _print_json(
                    _json_envelope(
                        success=result.ok,
                        operation="framework.validate",
                        data={"root": str(root), "error_count": len(result.errors)},
                        validation={
                            "framework": "passed" if result.ok else "failed",
                            "errors": result.errors,
                        },
                    )
                )
            elif not result.ok:
                print(
                    f"Framework validation failed with {len(result.errors)} error(s):",
                    file=sys.stderr,
                )
                for error in result.errors:
                    print(f"- {error}", file=sys.stderr)
            else:
                print(
                    "Framework validation passed: project scaffold, source "
                    "repository, and packaged resources are valid."
                )
            return 0 if result.ok else 1
        if args.command == "path":
            return _run_path(args, root)
        if args.command == "criterion":
            return _run_criterion(args, root)
        if args.command == "dependency":
            return _run_dependency(args, root)
        if args.command == "decision":
            return _run_decision(args, root)
        if args.command == "evidence":
            return _run_evidence(args, root)
        if args.command == "issue":
            return _run_issue(args, root)
        if args.command == "init":
            return _run_init(args, root)
        if args.command == "validate":
            result = validate_project(root)
            if getattr(args, "json", False):
                _print_json(
                    _json_envelope(
                        success=result.ok,
                        operation="project.validate",
                        data={"root": str(root), "error_count": len(result.errors)},
                        validation={
                            "project": "passed" if result.ok else "failed",
                            "errors": result.errors,
                        },
                    )
                )
                return 0 if result.ok else 1
            if not result.ok:
                print(
                    f"Validation failed with {len(result.errors)} error(s):",
                    file=sys.stderr,
                )
                for error in result.errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print(
                "Validation passed: project scaffold, schemas, state, reports, "
                "and references are valid."
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
    except BootstrapConflictError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation="project.bootstrap",
                    dry_run=getattr(args, "dry_run", False),
                    data={
                        "root": str(
                            args.root.expanduser().resolve()
                            if args.root is not None
                            else Path.cwd().resolve()
                        ),
                        "conflict_count": len(exc.conflicts),
                        "conflicts": list(exc.conflicts),
                    },
                    error={
                        "type": "conflict",
                        "stage": exc.stage,
                        "message": exc.message,
                        "paths": list(exc.conflicts),
                    },
                )
            )
        else:
            print(f"studio bootstrap: {exc.message}", file=sys.stderr)
        return 1
    except BootstrapError as exc:
        if getattr(args, "json", False):
            _print_json(
                _json_envelope(
                    success=False,
                    operation="project.bootstrap",
                    dry_run=getattr(args, "dry_run", False),
                    error={
                        "type": "bootstrap",
                        "stage": exc.stage,
                        "message": exc.message,
                    },
                )
            )
        else:
            print(f"studio bootstrap: {exc}", file=sys.stderr)
        return 2 if exc.stage in {"root", "confirmation", "initialization"} else 1
    except (
        CriticalPathNotFoundError,
        CriterionNotFoundError,
        DependencyNotFoundError,
        DecisionNotFoundError,
        EvidenceNotFoundError,
        IssueNotFoundError,
    ) as exc:
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
    except (
        CriticalPathInputError,
        CriterionInputError,
        DependencyInputError,
        DecisionInputError,
        EvidenceInputError,
        IssueInputError,
    ) as exc:
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
