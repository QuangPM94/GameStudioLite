"""`studio provider` — what optional capability sources are configured.

Providers are optional. "No providers" is a completely normal answer, and these
commands say so plainly rather than treating it as a problem to fix.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..providers import ProviderProbe, get_provider, probe_providers
from ._shared import _add_root_argument, _json_envelope, _print_json

HEALTH_LABEL = {
    "healthy": "HEALTHY",
    "unreachable": "UNREACHABLE",
    "not-configured": "NOT CONFIGURED",
    "unknown": "UNKNOWN",
}


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio provider` and its subcommands."""

    provider_parser = subparsers.add_parser(
        "provider", help="inspect optional capability providers"
    )
    provider_subparsers = provider_parser.add_subparsers(
        dest="provider_command", required=True
    )

    provider_list = provider_subparsers.add_parser("list", help="list providers")
    _add_root_argument(provider_list)
    provider_list.add_argument("--json", action="store_true")

    provider_doctor = provider_subparsers.add_parser(
        "doctor", help="report provider health and configuration"
    )
    _add_root_argument(provider_doctor)
    provider_doctor.add_argument("--json", action="store_true")

    provider_capabilities = provider_subparsers.add_parser(
        "capabilities", help="report what each provider claims it can do"
    )
    _add_root_argument(provider_capabilities)
    provider_capabilities.add_argument(
        "provider_id", nargs="?", help="limit to one provider"
    )
    provider_capabilities.add_argument("--json", action="store_true")


def _probes(root: Path, provider_id: str | None = None) -> tuple[ProviderProbe, ...]:
    if provider_id is None:
        return probe_providers(root)
    return (get_provider(provider_id).probe(root),)


def _run_list(args: argparse.Namespace, root: Path) -> int:
    probes = _probes(root)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="provider.list",
                data={
                    "count": len(probes),
                    "providers": [probe.to_dict() for probe in probes],
                },
            )
        )
        return 0
    print(f"Providers ({len(probes)}):")
    for probe in probes:
        print(
            f"- {probe.provider_id:<14} {HEALTH_LABEL[probe.health.status]:<16}"
            f"{probe.display_name}"
        )
    print("\nProviders are optional. The framework works fully without any of them.")
    return 0


def _run_doctor(args: argparse.Namespace, root: Path) -> int:
    probes = _probes(root)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="provider.doctor",
                data={"providers": [probe.to_dict() for probe in probes]},
            )
        )
        return 0
    for probe in probes:
        print(f"{probe.provider_id} — {probe.display_name}")
        print(f"- Health: {HEALTH_LABEL[probe.health.status]}")
        print(f"- Detail: {probe.health.detail}")
        print(f"- Configuration: {probe.health.configuration or 'none found'}")
        usable = probe.available_capabilities
        print("- Usable now: " + (", ".join(usable) if usable else "nothing"))
        if probe.evidence_policy:
            # The policy prints with the provider, not only when something is
            # captured, so a reader sees the constraint before relying on it.
            print("- Evidence policy:")
            for item in probe.evidence_policy:
                print(f"  - {item}")
        print()
    return 0


def _run_capabilities(args: argparse.Namespace, root: Path) -> int:
    probes = _probes(root, args.provider_id)
    if args.json:
        _print_json(
            _json_envelope(
                success=True,
                operation="provider.capabilities",
                data={"providers": [probe.to_dict() for probe in probes]},
            )
        )
        return 0
    for probe in probes:
        print(f"{probe.provider_id} ({HEALTH_LABEL[probe.health.status]}):")
        if not probe.capabilities:
            print("- none declared")
        for capability in probe.capabilities:
            print(
                f"- {capability.capability}: {capability.readiness} "
                f"[{capability.stability}] — {capability.detail}"
            )
        print()
    return 0


_SUBCOMMANDS = {
    "list": _run_list,
    "doctor": _run_doctor,
    "capabilities": _run_capabilities,
}


def run(args: argparse.Namespace, root: Path) -> int:
    """Dispatch to the requested `studio provider` subcommand."""

    return _SUBCOMMANDS[args.provider_command](args, root)
