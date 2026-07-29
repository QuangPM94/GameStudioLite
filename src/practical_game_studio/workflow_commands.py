"""Parsing for the canonical `GS:<workflow>` AI-agent invocation syntax.

This module encodes, as testable Python, the same contract `AGENTS.md`
describes in prose for an AI agent reading raw chat text: recognize a
`GS:<workflow>` command as the first non-whitespace text of a message, treat
everything after that first line as workflow input, and never guess an
unknown workflow. It does not run as part of the `studio` CLI; the AI agent
is the one matching chat text against this contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CANONICAL_PREFIX = "GS:"
_TRIGGER_PATTERN = re.compile(r"^GS:(.*)$")
_WORKFLOW_ID_PATTERN = re.compile(r"^[a-z]+(-[a-z]+)*$")


class WorkflowCommandError(ValueError):
    """Base class for a rejected `GS:` invocation attempt."""


class MalformedInvocationError(WorkflowCommandError):
    """The first line starts with `GS:` but is not a well-formed command."""


class UnknownWorkflowError(WorkflowCommandError):
    """The first line is a well-formed `GS:<id>` command for an unknown id."""

    def __init__(self, workflow_id: str, valid_canonicals: tuple[str, ...]) -> None:
        self.workflow_id = workflow_id
        self.valid_canonicals = valid_canonicals
        super().__init__(
            f"Unknown workflow 'GS:{workflow_id}'. Valid commands: "
            + ", ".join(valid_canonicals)
        )


@dataclass(frozen=True)
class WorkflowCommand:
    """A recognized `GS:<workflow>` invocation."""

    workflow_id: str
    canonical: str
    input_text: str


def catalog_workflows_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map workflow id -> workflow entry, deriving the id from the alias for
    catalogs written before the canonical-invocation representation existed."""

    by_id: dict[str, dict[str, Any]] = {}
    for workflow in catalog.get("workflows", []):
        workflow_id = workflow.get("id")
        if workflow_id is None:
            workflow_id = workflow.get("alias", "").removeprefix("/")
        by_id[workflow_id] = workflow
    return by_id


def valid_canonical_commands(catalog: dict[str, Any]) -> tuple[str, ...]:
    """Every valid `GS:<workflow>` command for the given catalog, sorted."""

    return tuple(
        sorted(
            workflow.get("canonical", f"GS:{workflow_id}")
            for workflow_id, workflow in catalog_workflows_by_id(catalog).items()
        )
    )


def parse_invocation(message: str, catalog: dict[str, Any]) -> WorkflowCommand | None:
    """Parse a user message's first non-whitespace text as a `GS:<workflow>` command.

    Returns ``None`` when the message is not an attempted `GS:` invocation at
    all (ordinary chat text, or a legacy `/alias`, which AGENTS.md continues to
    interpret directly). Raises :class:`MalformedInvocationError` when the
    first line looks like an attempted invocation but is not well-formed
    (empty workflow id, an embedded `/`, uppercase letters, etc.). Raises
    :class:`UnknownWorkflowError` when the workflow id is well-formed but not
    present in the catalog.
    """

    stripped = message.lstrip()
    first_line, _, remainder = stripped.partition("\n")
    first_line = first_line.strip()

    trigger = _TRIGGER_PATTERN.match(first_line)
    if trigger is None:
        return None

    candidate_id = trigger.group(1)
    if not _WORKFLOW_ID_PATTERN.match(candidate_id):
        raise MalformedInvocationError(
            f"'{first_line}' is not a well-formed GS:<workflow> command; "
            "the workflow id must be lowercase kebab-case with no other "
            "punctuation."
        )

    by_id = catalog_workflows_by_id(catalog)
    if candidate_id not in by_id:
        raise UnknownWorkflowError(candidate_id, valid_canonical_commands(catalog))

    workflow = by_id[candidate_id]
    canonical = workflow.get("canonical", f"GS:{candidate_id}")
    return WorkflowCommand(
        workflow_id=candidate_id, canonical=canonical, input_text=remainder.strip()
    )
