"""Detecting a Godot MCP provider, and being honest about what that buys.

GameStudioLite is a command-line tool. It does not itself speak MCP: the MCP
connection belongs to the AI agent or editor the developer is using. So this
provider does exactly what a CLI honestly can, and nothing more:

1. Detect that a Godot MCP server is configured, and where.
2. Report what capabilities that configuration claims, and how far each can be
   trusted.
3. State the provenance rules that results obtained through it must carry.

It never claims to have taken a screenshot. When an agent captures one over its
own MCP connection, that image enters the framework the same way any other file
does — `studio artifact add --type screenshot` — and the provenance rules below
govern what may be claimed from it.

Pretending otherwise would be the worst possible failure for this framework: an
unverifiable claim wearing the costume of an observation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import BaseProvider, ProviderCapability, ProviderHealth

#: Configuration files checked, in order. The first two are the framework's own
#: opt-in; the rest are where MCP clients conventionally keep server config.
CONFIGURATION_PATHS = (
    ".studio/providers.json",
    ".mcp.json",
    ".vscode/mcp.json",
    ".cursor/mcp.json",
)

#: Server names that indicate a Godot MCP server.
GODOT_SERVER_HINTS = ("godot", "godot-mcp", "godot_mcp")

#: What a Godot MCP server typically offers. Reported as `unknown` stability
#: unless the project's own `.studio/providers.json` states otherwise, because
#: the framework cannot verify a third-party server's behaviour by inspecting a
#: config file.
DECLARED_CAPABILITIES = (
    "EDITOR_INSPECT",
    "SCENE_INSPECT",
    "SCENE_MODIFY",
    "LAUNCH",
    "SCREENSHOT",
    "RUNTIME_INSPECT",
)

#: Rules that travel with anything captured through this provider. They exist
#: because a screenshot is evidence *about rendering*, and the gap between that
#: and evidence about a player is exactly where projects deceive themselves.
EVIDENCE_POLICY = (
    (
        "A screenshot or scene dump obtained through MCP is `observed` evidence "
        "about what the engine rendered or reported. It is not evidence about a "
        "player."
    ),
    (
        "Injected input is not player behaviour. A sequence the framework or an "
        "agent drove may be recorded as `observed` runtime evidence, never as "
        "`observed-player-behavior`."
    ),
    (
        "The framework did not perform these captures and cannot attest to "
        "them. Record who or what captured each artifact in its description."
    ),
)


class GodotMcpProvider(BaseProvider):
    """Detect and describe a configured Godot MCP server."""

    id = "godot-mcp"
    display_name = "Godot MCP server"
    engine = "Godot"
    evidence_policy = EVIDENCE_POLICY

    def _configuration(self, root: Path) -> tuple[Path, dict[str, Any]] | None:
        """Find the first configuration file that names a Godot MCP server."""

        for relative in CONFIGURATION_PATHS:
            path = root / relative
            if not path.is_file():
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # An unreadable config is reported by `health`, not treated as
                # absence: "broken" and "not set up" need different fixes.
                return (path, {})
            if not isinstance(document, dict):
                return (path, {})
            if self._names_godot_server(document):
                return (path, document)
        return None

    @staticmethod
    def _names_godot_server(document: dict[str, Any]) -> bool:
        servers = document.get("mcpServers") or document.get("servers") or {}
        if isinstance(servers, dict) and any(
            hint in str(name).casefold()
            for name in servers
            for hint in GODOT_SERVER_HINTS
        ):
            return True
        providers = document.get("providers")
        return isinstance(providers, dict) and "godot-mcp" in providers

    def detect(self, root: Path) -> bool:
        return self._configuration(root) is not None

    def health(self, root: Path) -> ProviderHealth:
        found = self._configuration(root)
        if found is None:
            return ProviderHealth(
                status="not-configured",
                detail=(
                    "no Godot MCP server was found in " + ", ".join(CONFIGURATION_PATHS)
                ),
            )
        path, document = found
        relative = path.name if path.parent == root else str(path)
        if not document:
            return ProviderHealth(
                status="unknown",
                detail=f"{relative} could not be parsed as MCP configuration",
                configuration=relative,
            )
        # A config file proves configuration, not reachability. The framework
        # has no MCP connection of its own, so it cannot promote this to
        # `healthy` without asserting something it has not checked.
        return ProviderHealth(
            status="unknown",
            detail=(
                f"a Godot MCP server is configured in {relative}, but this CLI "
                "holds no MCP connection and cannot confirm it is running"
            ),
            configuration=relative,
        )

    def capabilities(self, root: Path) -> tuple[ProviderCapability, ...]:
        configured = self.detect(root)
        return tuple(
            ProviderCapability(
                capability=name,
                # Never `ready`: the framework cannot call the server, so it
                # cannot honestly say the capability is available to it.
                readiness="unknown" if configured else "not-configured",
                stability="unknown",
                detail=(
                    "declared by the configured MCP server; the agent holding "
                    "the MCP connection performs it, not this CLI"
                    if configured
                    else "no Godot MCP server is configured"
                ),
                limitations=EVIDENCE_POLICY if configured else (),
            )
            for name in DECLARED_CAPABILITIES
        )


PROVIDER = GodotMcpProvider()
