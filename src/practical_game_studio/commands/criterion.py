"""`studio criterion` — manage current-milestone success criteria."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..criteria import (
    CriterionCreateRequest,
    CriterionEvaluation,
    CriterionInputError,
    CriterionPatch,
    CriterionService,
)
from ..criterion_support import SupportAssessment, assess_support
from ._shared import (
    _add_root_argument,
    _confirm_structural_write,
    _json_envelope,
    _mutation_envelope,
    _path_impact_lines,
    _print_json,
    _required_values,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio criterion` and its subcommands."""

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

    criterion_support = criterion_subparsers.add_parser(
        "support",
        help="show what a criterion's evidence supports (read-only)",
    )
    criterion_support.add_argument("criterion_id")
    _add_root_argument(criterion_support)
    criterion_support.add_argument("--json", action="store_true")


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


def _evidence_rows(rows: tuple, empty: str) -> list[str]:
    if not rows:
        return [f"- {empty}"]
    lines: list[str] = []
    for row in rows:
        suffix = f" — {row['reason']}" if row.get("reason") else ""
        lines.append(
            f"- {row['id']} [{row['classification']}/{row['source_type']}] "
            f"{row['title']}{suffix}"
        )
        provenance = [*row["related_runs"], *row["related_artifacts"]]
        if provenance:
            lines.append("    provenance: " + ", ".join(provenance))
    return lines


def _format_support(assessment: SupportAssessment) -> str:
    """Render the assessment, keeping advice visibly separate from a verdict."""

    lines = [
        f"{assessment.criterion_id} — {assessment.description}",
        "",
        f"Verification policy: {assessment.policy}",
        f"Recorded support status: {assessment.support_status}",
        "",
        "Required by this policy:",
        f"- {assessment.required_policy}",
        "",
        "Available evidence:",
    ]
    lines.extend(_evidence_rows(assessment.qualifying_evidence, "none"))
    lines.extend(["", "Linked evidence that does not meet this policy:"])
    lines.extend(_evidence_rows(assessment.non_qualifying_evidence, "none"))
    lines.extend(["", "Conflicting evidence:"])
    lines.extend(_evidence_rows(assessment.conflicting_evidence, "none"))

    # Always printed. An empty section is the difference between "nothing is
    # missing" and "we forgot to check", and someone deciding whether to mark
    # a milestone criterion verified needs to tell those apart.
    lines.extend(["", "Missing evidence:"])
    lines.extend(f"- {item}" for item in assessment.missing or ("none",))
    lines.extend(["", "Limitations of the available evidence:"])
    lines.extend(f"- {item}" for item in assessment.limitations or ("none recorded",))
    lines.extend(
        [
            "",
            "Recommended evaluation:",
            assessment.recommendation,
            "",
            "This command is read-only; it has not evaluated anything.",
            "",
            "Recommended next command:",
            assessment.recommended_command,
        ]
    )
    return "\n".join(lines)


def _run_criterion_support(args: argparse.Namespace, root: Path) -> int:
    """Report what a criterion's evidence supports, without evaluating it."""

    assessment = assess_support(root, args.criterion_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="criterion.support",
                data=assessment.to_dict(),
            )
        )
        return 0
    print(_format_support(assessment))
    return 0


def run(args: argparse.Namespace, root: Path) -> int:
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
    if args.criterion_command == "support":
        return _run_criterion_support(args, root)
    raise CriterionInputError(f"unknown criterion command {args.criterion_command}")
