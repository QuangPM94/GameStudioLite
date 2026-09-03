"""`studio doctor` — what can this machine actually do?

The doctor's only job is to answer that honestly. It probes; it never infers.
Every line it prints corresponds to something it looked for, and a thing it
could not determine is reported as `UNKNOWN` rather than being rounded to either
`READY` or `UNAVAILABLE`.

It performs no configuration. A doctor that fixed things would make its own
report untrustworthy, because the reader could no longer tell what was already
true from what the doctor just did.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..adapters import detect_adapters, resolve_adapter
from ..execution import (
    describe_platform,
    detect_repository,
    probe_git,
    probe_python,
)
from ..providers import probe_providers, provider_capabilities
from ..state import StateRepository
from ._shared import _add_root_argument, _json_envelope, _print_json

#: How a readiness value is shown. The words are deliberately different lengths
#: of certainty rather than a red/green pair.
READINESS_LABEL = {
    "ready": "READY",
    "unavailable": "UNAVAILABLE",
    "unknown": "UNKNOWN",
    "not-configured": "NOT CONFIGURED",
}

#: Capabilities always shown, so a reader can see what was considered and found
#: missing rather than having to notice an absence.
REPORTED_CAPABILITIES = (
    "RUN",
    "HEADLESS",
    "TEST",
    "BUILD",
    "EXPORT",
    "LOG_CAPTURE",
    "SCREENSHOT",
    "RUNTIME_INSPECT",
    "INPUT_INJECTION",
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio doctor`."""

    doctor_parser = subparsers.add_parser(
        "doctor", help="report what the framework can actually execute here"
    )
    _add_root_argument(doctor_parser)
    doctor_parser.add_argument(
        "--adapter", help="probe this adapter instead of the detected one"
    )
    doctor_parser.add_argument("--json", action="store_true")


def collect(root: Path, *, adapter_id: str | None = None) -> dict[str, Any]:
    """Probe the environment and return the full doctor payload."""

    project = StateRepository(root).load_project()
    matches = detect_adapters(root)
    adapter = resolve_adapter(root, adapter_id=adapter_id)
    probe = adapter.probe(root) if adapter is not None else None

    return {
        "root": str(root),
        "project": {
            "name": project["project_name"],
            "declared_engine": project["engine"],
            "declared_platform": project["platform"],
            "build_status": project["current_build_status"],
        },
        "tools": [probe_python().to_dict(), probe_git().to_dict()],
        "repository": detect_repository(root),
        "platform": describe_platform(),
        "adapters": [match.to_dict() for match in matches],
        "resolved_adapter": adapter.id if adapter is not None else None,
        "engine": probe.to_dict() if probe is not None else None,
        # Reported explicitly, including when nothing is configured: omitting
        # the row would let a reader assume rather than read.
        "providers": _provider_rows(root),
        "capabilities": _capability_rows(probe),
    }


def _provider_rows(root: Path) -> dict[str, Any]:
    """Summarise configured providers and what is usable through them."""

    probes = probe_providers(root)
    configured = [probe for probe in probes if probe.health.status != "not-configured"]
    usable = provider_capabilities(root)
    if not configured:
        readiness, detail = (
            "not-configured",
            "no editor/MCP provider is configured",
        )
    elif usable:
        readiness, detail = "ready", f"{len(configured)} provider(s) reachable"
    else:
        # Configured but unusable from here. Saying `unknown` rather than
        # `ready` keeps the framework from implying it can call something
        # it has never reached.
        readiness, detail = (
            "unknown",
            (
                f"{len(configured)} provider(s) configured; this CLI holds no "
                "connection and cannot confirm any of them"
            ),
        )
    return {
        "readiness": readiness,
        "detail": detail,
        "available": list(usable),
        "providers": [probe.to_dict() for probe in probes],
    }


def _capability_rows(probe: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in REPORTED_CAPABILITIES:
        report = probe.capability(name) if probe is not None else None
        if report is not None:
            rows.append(report.to_dict())
            continue
        rows.append(
            {
                "capability": name,
                # No adapter resolved, or the adapter did not probe this: either
                # way the truthful answer is that we do not know, not that it is
                # missing.
                "readiness": "unknown" if probe is None else "unavailable",
                "detail": (
                    "no engine adapter recognises this project"
                    if probe is None
                    else "this adapter does not report the capability"
                ),
                "risk": "low",
            }
        )
    return rows


def _format(payload: dict[str, Any]) -> str:
    engine = payload["engine"]
    lines = [
        f"Project: {payload['project']['name']}",
        f"Declared engine: {payload['project']['declared_engine'] or 'not recorded'}",
        "",
        "Tools:",
    ]
    lines.extend(
        f"- {tool['name']}: {READINESS_LABEL[tool['readiness']]}"
        + (f" ({tool['version']})" if tool["version"] else "")
        for tool in payload["tools"]
    )

    repository = payload["repository"]
    dirty = repository["dirty"]
    lines.extend(
        [
            "",
            "Repository:",
            f"- VCS: {repository['vcs'] or 'none detected'}",
            f"- Revision: {repository['revision'] or 'unknown'}",
            "- Working tree: "
            + (
                "unknown"
                if dirty is None
                # A dirty tree means an artifact cannot be reproduced from the
                # recorded revision alone.
                else ("has uncommitted changes" if dirty else "clean")
            ),
        ]
    )

    lines.extend(["", "Engine:"])
    if engine is None:
        lines.append("- No engine adapter recognises this project.")
        lines.append(
            "- The framework remains usable for planning; execution commands "
            "will report UNKNOWN."
        )
    else:
        lines.append(f"- Adapter: {payload['resolved_adapter']}")
        lines.append(f"- Engine: {engine['engine']}")
        lines.append(f"- Version: {engine['engine_version'] or 'unknown'}")
        lines.append(f"- Executable: {engine['executable'] or 'not found'}")

    lines.extend(["", "Capabilities:"])
    lines.extend(
        f"- {row['capability']}: {READINESS_LABEL[row['readiness']]} — {row['detail']}"
        for row in payload["capabilities"]
    )

    providers = payload["providers"]
    provider_readiness = READINESS_LABEL[providers["readiness"]]
    lines.extend(["", f"Providers: {provider_readiness} — {providers['detail']}"])

    limitations = (engine or {}).get("limitations") or []
    if limitations:
        lines.extend(["", "Limitations:"])
        lines.extend(f"- {item}" for item in limitations)

    lines.extend(["", "Recommended next command:", _recommendation(payload)])
    return "\n".join(lines)


def _recommendation(payload: dict[str, Any]) -> str:
    ready = {
        row["capability"]
        for row in payload["capabilities"]
        if row["readiness"] == "ready"
    }
    if "HEADLESS" in ready:
        return "studio verify --level smoke"
    if payload["engine"] is None:
        return "studio status"
    return "studio validate"


def run(args: argparse.Namespace, root: Path) -> int:
    """Report what the framework can execute, without changing anything."""

    payload = collect(root, adapter_id=args.adapter)
    if args.json:
        _print_json(_json_envelope(success=True, operation="doctor", data=payload))
        return 0
    print(_format(payload))
    return 0
