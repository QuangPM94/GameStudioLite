"""`studio artifact` — register, inspect, and re-check files a run produced."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..artifacts import (
    ARTIFACT_TYPES,
    STATUSES,
    ArtifactCreateRequest,
    ArtifactFilter,
    ArtifactInputError,
    ArtifactService,
    filter_artifacts,
    find_artifact,
)
from ..provenance import (
    CAPTURE_SOURCES,
    MEDIA_TYPES,
    capture_source,
    limitations_for,
    strongest_supported_classification,
)
from ..safety import authorize
from ..state import StateRepository
from ._shared import (
    _add_root_argument,
    _json_envelope,
    _mutation_envelope,
    _print_json,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio artifact` and its subcommands."""

    artifact_parser = subparsers.add_parser(
        "artifact", help="register and verify execution artifacts"
    )
    artifact_subparsers = artifact_parser.add_subparsers(
        dest="artifact_command", required=True
    )

    artifact_add = artifact_subparsers.add_parser(
        "add", help="register a file as an artifact"
    )
    _add_root_argument(artifact_add)
    artifact_add.add_argument("--type", required=True, choices=ARTIFACT_TYPES)
    artifact_add.add_argument("--path", required=True)
    artifact_add.add_argument("--source-run", help="the RUN that produced the file")
    artifact_add.add_argument("--description")
    artifact_add.add_argument("--revision")
    artifact_add.add_argument("--captured-at")
    artifact_add.add_argument("--mime-type")
    artifact_add.add_argument(
        "--capture-source",
        choices=CAPTURE_SOURCES,
        default="unknown",
        help="who or what produced this file; decides what may be claimed",
    )
    artifact_add.add_argument(
        "--metadata", help="additional provenance as a JSON object"
    )
    artifact_add.add_argument("--dry-run", action="store_true")
    artifact_add.add_argument(
        "--yes",
        action="store_true",
        help="authorise this medium-risk operation without a prompt",
    )
    artifact_add.add_argument("--json", action="store_true")

    artifact_list = artifact_subparsers.add_parser("list", help="list artifacts")
    _add_root_argument(artifact_list)
    artifact_list.add_argument("--type", choices=ARTIFACT_TYPES)
    artifact_list.add_argument("--status", choices=STATUSES)
    artifact_list.add_argument("--source-run")
    artifact_list.add_argument("--limit", type=int)
    artifact_list.add_argument("--json", action="store_true")

    artifact_show = artifact_subparsers.add_parser("show", help="show one artifact")
    _add_root_argument(artifact_show)
    artifact_show.add_argument("artifact_id")
    artifact_show.add_argument("--json", action="store_true")

    artifact_verify = artifact_subparsers.add_parser(
        "verify", help="re-check artifacts against the files on disk"
    )
    _add_root_argument(artifact_verify)
    artifact_verify.add_argument(
        "artifact_id", nargs="?", help="verify one artifact instead of all of them"
    )
    artifact_verify.add_argument(
        "--record",
        action="store_true",
        help="store the result in each artifact's status (otherwise read-only)",
    )
    artifact_verify.add_argument("--dry-run", action="store_true")
    artifact_verify.add_argument("--json", action="store_true")


def _metadata(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArtifactInputError(f"--metadata is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactInputError("--metadata must be a JSON object")
    return value


def _format_summary(artifact: dict[str, Any]) -> str:
    size = artifact["size_bytes"]
    size_text = f"{size} B" if size is not None else "unknown size"
    return (
        f"{artifact['id']}  {artifact['status']:<11} {artifact['type']:<12} "
        f"{size_text:<15} {artifact['path']}"
    )


def _format_detail(artifact: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"{artifact['id']} — {artifact['type']}",
            "",
            f"Path: {artifact['path']}",
            f"Status: {artifact['status']}",
            f"MIME type: {artifact['mime_type'] or 'unknown'}",
            f"SHA-256: {artifact['sha256'] or 'not hashed'}",
            f"Size: {artifact['size_bytes']} bytes"
            if artifact["size_bytes"] is not None
            else "Size: unknown",
            f"Source run: {artifact['source_run'] or 'none'}",
            f"Revision: {artifact['revision'] or 'unknown'}",
            f"Captured at: {artifact['captured_at'] or 'unknown'}",
            f"Created at: {artifact['created_at']}",
            f"Description: {artifact['description'] or 'none'}",
            "",
            "Metadata:",
            json.dumps(
                artifact["metadata"], ensure_ascii=False, indent=2, sort_keys=True
            ),
        ]
    )


def _run_add(args: argparse.Namespace, root: Path) -> int:
    # Registering an artifact hashes and records a file path the project
    # will later treat as provenance, so it is gated like other writes.
    if not args.dry_run:
        authorize(
            root,
            "artifact.add",
            acknowledged=args.yes,
            json_output=args.json,
            prompt_detail=f"Register {args.path} as a {args.type} artifact.",
        )
    service = ArtifactService(root)
    result = service.add(
        ArtifactCreateRequest(
            type=args.type,
            path=args.path,
            source_run=args.source_run,
            description=args.description,
            revision=args.revision,
            captured_at=args.captured_at,
            mime_type=args.mime_type,
            # Provenance lives in metadata so it travels with the record and
            # survives every later read of it.
            metadata={
                **(_metadata(args.metadata) or {}),
                "capture_source": args.capture_source,
            },
        ),
        dry_run=args.dry_run,
    )
    if args.json:
        _print_json(_mutation_envelope(result))
        return 0
    artifact = result.details["artifact"]
    label = "Would register" if result.dry_run else "Registered"
    print(f"{label} {artifact['id']}.\n")
    print(_format_detail(artifact))
    if artifact["type"] in MEDIA_TYPES:
        # Printed on registration, not only when someone tries to over-claim:
        # the constraint is most useful before the claim is written.
        source = capture_source(artifact)
        strongest = strongest_supported_classification(source)
        print(
            f"\nProvenance: captured as {source!r}. "
            f"This supports at most {strongest!r} evidence."
        )
        print("Limitations that must travel with any claim from it:")
        for item in limitations_for(source, artifact["type"]):
            print(f"- {item}")
    if artifact["status"] == "missing":
        # Registering an absent file is allowed, but never silently: a build that
        # did not produce what it promised is exactly what this should surface.
        print(
            "\nWarning: no file exists at that path. The artifact is recorded as "
            "missing rather than assumed present."
        )
    return 0


def _run_list(args: argparse.Namespace, root: Path) -> int:
    state = StateRepository(root).load_artifacts()
    selected = filter_artifacts(
        state["artifacts"],
        ArtifactFilter(
            type=args.type,
            status=args.status,
            source_run=args.source_run,
            limit=args.limit,
        ),
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="artifact.list",
                data={"count": len(selected), "artifacts": selected},
            )
        )
        return 0
    if not selected:
        print("No artifacts match the given filters.")
        return 0
    print(f"Artifacts ({len(selected)}):")
    for artifact in selected:
        print(_format_summary(artifact))
    return 0


def _run_show(args: argparse.Namespace, root: Path) -> int:
    state = StateRepository(root).load_artifacts()
    artifact = find_artifact(state, args.artifact_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True, operation="artifact.show", data={"artifact": artifact}
            )
        )
        return 0
    print(_format_detail(artifact))
    return 0


def _run_verify(args: argparse.Namespace, root: Path) -> int:
    service = ArtifactService(root)
    if args.record:
        if args.artifact_id is not None:
            raise ArtifactInputError(
                "--record re-checks every artifact; drop the artifact id"
            )
        result = service.record_verification(dry_run=args.dry_run)
        if args.json:
            _print_json(_mutation_envelope(result))
            return 0
        problems = result.details["problems"]
        print(
            f"Checked {result.details['checked']} artifact(s); "
            f"{problems} did not match."
        )
        for entry in result.details["verifications"]:
            print(f"- {entry['artifact_id']}: {entry['status']} — {entry['detail']}")
        return 1 if problems else 0

    verifications = service.verify(args.artifact_id)
    problems = [item for item in verifications if not item.ok]
    if args.json:
        _print_json(
            _json_envelope(
                success=not problems,
                operation="artifact.verify",
                data={
                    "checked": len(verifications),
                    "problems": len(problems),
                    "verifications": [item.to_dict() for item in verifications],
                },
            )
        )
        return 1 if problems else 0
    if not verifications:
        print("No artifacts are registered.")
        return 0
    print(f"Checked {len(verifications)} artifact(s); {len(problems)} did not match.")
    for item in verifications:
        print(f"- {item.artifact_id}: {item.status} — {item.detail}")
    return 1 if problems else 0


_SUBCOMMANDS = {
    "add": _run_add,
    "list": _run_list,
    "show": _run_show,
    "verify": _run_verify,
}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio artifact` subcommand."""

    return _SUBCOMMANDS[args.artifact_command](args, root)
