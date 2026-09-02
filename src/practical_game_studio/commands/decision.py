"""`studio decision` — record, inspect, update, and resolve decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..decisions import (
    DecisionCreateRequest,
    DecisionInputError,
    DecisionOption,
    DecisionPatch,
    DecisionResolution,
    DecisionService,
)
from ..state import StateRepository
from ._shared import _add_root_argument, _json_envelope, _mutation_envelope, _print_json


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio decision` and its subcommands."""

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


def run(args: argparse.Namespace, root: Path) -> int:
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
