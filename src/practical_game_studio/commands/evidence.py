"""`studio evidence` — create, inspect, and update project evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..evidence import (
    SOURCE_OPTIONAL_TYPES,
    SOURCE_TYPES,
    EvidenceCreateRequest,
    EvidenceInputError,
    EvidencePatch,
    EvidenceService,
)
from ._shared import (
    _add_root_argument,
    _json_envelope,
    _mutation_envelope,
    _print_json,
    _recommended_workflow_block,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio evidence` and its subcommands."""

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
    print(_recommended_workflow_block(result.details))
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


def run(args: argparse.Namespace, root: Path) -> int:
    if args.evidence_command == "add":
        return _run_evidence_add(args, root)
    if args.evidence_command == "list":
        return _run_evidence_list(args, root)
    if args.evidence_command == "show":
        return _run_evidence_show(args, root)
    if args.evidence_command == "update":
        return _run_evidence_update(args, root)
    raise EvidenceInputError(f"unknown evidence command {args.evidence_command}")
