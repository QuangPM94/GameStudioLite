"""`studio release` — produce and check a distributable build.

Four steps, deliberately separate, because none of them concludes the next.
Producing a package does not verify it; verifying a file exists does not mean it
runs. Every step prints what it did not establish alongside what it did.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..release import (
    ReleaseCheck,
    ReleaseReadiness,
    build_release,
    check_release_readiness,
    package_release,
    verify_package,
)
from ..safety import authorize
from ._shared import (
    _add_root_argument,
    _json_envelope,
    _print_json,
)
from .execute import EXIT_FAILED, EXIT_OK, EXIT_UNKNOWN, _authorization

#: How a release step's status maps onto an exit code, reusing the execution
#: vocabulary so a script does not need two tables.
_EXIT = {"ready": EXIT_OK, "passed": EXIT_OK, "blocked": EXIT_FAILED}


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio release` and its subcommands."""

    release_parser = subparsers.add_parser(
        "release", help="produce and check a distributable build"
    )
    release_subparsers = release_parser.add_subparsers(
        dest="release_command", required=True
    )

    release_doctor = release_subparsers.add_parser(
        "doctor", help="report whether this project could be released"
    )
    _add_root_argument(release_doctor)
    release_doctor.add_argument("--json", action="store_true")

    release_build = release_subparsers.add_parser(
        "build", help="produce a release build"
    )
    _add_root_argument(release_build)
    release_build.add_argument("--target", help="export preset or build target")
    release_build.add_argument("--output", help="where to write the package")
    release_build.add_argument("--yes", action="store_true")
    release_build.add_argument("--json", action="store_true")

    release_package = release_subparsers.add_parser(
        "package", help="register a produced package as a traceable artifact"
    )
    release_package.add_argument("path")
    _add_root_argument(release_package)
    release_package.add_argument("--source-run", help="the RUN that produced it")
    release_package.add_argument("--description")
    release_package.add_argument("--yes", action="store_true")
    release_package.add_argument("--json", action="store_true")

    release_verify = release_subparsers.add_parser(
        "verify", help="check a recorded package against the file on disk"
    )
    release_verify.add_argument("artifact_id")
    _add_root_argument(release_verify)
    release_verify.add_argument("--json", action="store_true")


def _format_checks(checks: tuple[ReleaseCheck, ...]) -> list[str]:
    return [f"- {check.name}: {check.status} — {check.detail}" for check in checks]


def _format_readiness(readiness: ReleaseReadiness) -> str:
    lines = [f"Release readiness: {readiness.status}", "", "Checks:"]
    lines.extend(_format_checks(readiness.checks))

    # Both sections print even when empty: a reader deciding whether to ship
    # needs "nothing is blocking" to look different from "we did not check".
    lines.extend(["", "Blockers:"])
    lines.extend(_format_checks(readiness.blockers) or ["- none"])
    lines.extend(["", "Could not be determined:"])
    lines.extend(_format_checks(readiness.unknowns) or ["- none"])
    return "\n".join(lines)


def _run_doctor(args: argparse.Namespace, root: Path) -> int:
    readiness = check_release_readiness(root)
    if args.json:
        _print_json(
            _json_envelope(
                success=readiness.status == "ready",
                operation="release.doctor",
                data=readiness.to_dict(),
            )
        )
    else:
        print(_format_readiness(readiness))
    return _EXIT.get(readiness.status, EXIT_UNKNOWN)


def _run_build(args: argparse.Namespace, root: Path) -> int:
    decision = authorize(
        root,
        "build",
        acknowledged=args.yes,
        json_output=args.json,
        prompt_detail="Produce a release build.",
    )
    result = build_release(
        root,
        target=args.target,
        output=args.output,
        authorization=_authorization(decision),
    )
    if result is None:
        detail = "No engine adapter recognises this project; nothing was built."
        if args.json:
            _print_json(
                _json_envelope(
                    success=False,
                    operation="release.build",
                    data={"status": "unknown", "detail": detail},
                )
            )
        else:
            print(detail)
        return EXIT_UNKNOWN

    if args.json:
        _print_json(
            _json_envelope(
                success=result.status == "passed",
                operation="release.build",
                data=result.to_dict(),
            )
        )
        return _EXIT.get(result.status, EXIT_UNKNOWN)

    print(f"Status: {result.status}")
    print(result.detail)
    if result.run_id:
        print(f"\nRun: {result.run_id}")
    print(
        "\nA produced package has not been launched. Register and check it:\n"
        "studio release package <path> --source-run "
        f"{result.run_id or '<RUN-ID>'}"
    )
    return _EXIT.get(result.status, EXIT_UNKNOWN)


def _run_package(args: argparse.Namespace, root: Path) -> int:
    authorize(
        root,
        "artifact.add",
        acknowledged=args.yes,
        json_output=args.json,
        prompt_detail=f"Register {args.path} as a release package.",
    )
    packaged = package_release(
        root,
        args.path,
        source_run=args.source_run,
        description=args.description,
    )
    if args.json:
        _print_json(
            _json_envelope(
                success=packaged.exists,
                operation="release.package",
                data=packaged.to_dict(),
            )
        )
        return EXIT_OK if packaged.exists else EXIT_FAILED

    print(f"Registered {packaged.artifact_id}.")
    print(f"- Path: {packaged.path}")
    print(f"- Present: {'yes' if packaged.exists else 'no'}")
    print(f"- SHA-256: {packaged.sha256 or 'not hashed'}")
    print(f"- Revision: {packaged.revision or 'unknown'}")
    print("\nWhat this does NOT establish:")
    for item in packaged.limitations:
        print(f"- {item}")
    return EXIT_OK if packaged.exists else EXIT_FAILED


def _run_verify(args: argparse.Namespace, root: Path) -> int:
    checks = verify_package(root, args.artifact_id)
    failed = [check for check in checks if check.status == "failed"]
    if args.json:
        _print_json(
            _json_envelope(
                success=not failed,
                operation="release.verify",
                data={"checks": [check.to_dict() for check in checks]},
            )
        )
    else:
        print(f"Package: {args.artifact_id}")
        print("\n".join(_format_checks(checks)))
        print(
            "\nA package that exists and matches its hash has still not been "
            "run. Launching the packaged build is a separate, manual step."
        )
    if failed:
        return EXIT_FAILED
    return EXIT_UNKNOWN if any(c.status == "unknown" for c in checks) else EXIT_OK


_SUBCOMMANDS = {
    "doctor": _run_doctor,
    "build": _run_build,
    "package": _run_package,
    "verify": _run_verify,
}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio release` subcommand."""

    return _SUBCOMMANDS[args.release_command](args, root)
