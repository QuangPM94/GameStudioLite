"""Bounding what an AI agent is allowed to execute without asking.

An agent that can run arbitrary commands on a developer's machine needs limits
that are stated rather than assumed. Every operation is classified by risk, and
each risk class says who must agree before it runs.

Three principles shape the rules below.

**Refusing is safer than guessing.** In a non-interactive terminal there is
nobody to ask, so anything above low risk is denied unless `--yes` was passed.
An agent cannot manufacture consent by finding itself unsupervised.

**Denial explains itself.** A refusal names the operation, its risk, why it was
refused, and the exact flag that would authorise it — so an agent can ask the
human for that specific thing instead of retrying blindly.

**Every authorisation is recorded.** The run record stores the risk level and
how the operation was authorised, so "who agreed to this build?" is answerable
after the fact rather than a matter of recollection.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state import StateRepository

#: Ordered from least to most dangerous.
RISK_LEVELS = ("safe", "low", "medium", "high")
_RISK_ORDER = {level: index for index, level in enumerate(RISK_LEVELS)}

#: How each operation is classified. An operation absent from this table is
#: treated as `high`, because the cautious default is the only safe one for
#: something the framework does not recognise.
OPERATION_RISK: dict[str, str] = {
    # Reading state changes nothing and never needs approval.
    "doctor": "safe",
    "validate": "safe",
    "status": "safe",
    "report": "safe",
    "execution.list": "safe",
    "execution.show": "safe",
    "artifact.list": "safe",
    "artifact.show": "safe",
    "artifact.verify": "safe",
    "criterion.support": "safe",
    "workflow.list": "safe",
    "workflow.ready": "safe",
    "workflow.check": "safe",
    "workflow.explain": "safe",
    "upgrade.check": "safe",
    "upgrade.plan": "safe",
    # Running the game reads the project and writes only logs the framework owns.
    "run": "low",
    "test": "low",
    "verify": "low",
    "capture": "low",
    # These write files outside `.studio`, or change how the project builds.
    "build": "medium",
    "export": "medium",
    "artifact.add": "medium",
    "upgrade.apply": "medium",
    "scene.modify": "medium",
    "dependency.install": "medium",
    # Nothing here is implemented yet. They are listed so that adding one later
    # inherits the right class instead of quietly landing as unclassified.
    "install.global": "high",
    "engine.upgrade": "high",
    "files.delete": "high",
    "build.configure": "high",
    "project.format": "high",
    "network.configure": "high",
    "credentials.modify": "high",
}

#: The lowest risk that needs agreement, per review mode. `fast` still gates
#: high risk: a review preference is not a licence to delete things unasked.
APPROVAL_THRESHOLD = {
    "fast": "high",
    "guided": "medium",
    "strict": "low",
}

#: Above this, `--yes` alone is not enough in a non-interactive terminal.
#: Nothing currently reaches it; the rule exists before the operations do.
ALWAYS_INTERACTIVE_RISK = "high"


class ExecutionDeniedError(PermissionError):
    """An operation was refused because nobody authorised it.

    Deliberately not a `ValueError`: this is not malformed input. The request
    was well-formed and understood, and was declined.
    """

    def __init__(self, decision: SafetyDecision) -> None:
        self.decision = decision
        super().__init__(decision.message)


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    """Whether an operation may run, and the reasoning either way."""

    operation: str
    risk: str
    review_mode: str
    allowed: bool
    #: How the operation was authorised: `risk-below-threshold`, `flag`,
    #: `interactive`, or `denied`.
    authorization: str
    message: str
    interactive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "risk": self.risk,
            "review_mode": self.review_mode,
            "allowed": self.allowed,
            "authorization": self.authorization,
            "message": self.message,
            "interactive": self.interactive,
        }


def classify(operation: str) -> str:
    """Return an operation's risk class, defaulting to `high` when unknown."""

    return OPERATION_RISK.get(operation, "high")


def requires_approval(operation: str, review_mode: str) -> bool:
    """Whether this operation needs agreement under the project's review mode."""

    threshold = APPROVAL_THRESHOLD.get(review_mode, "medium")
    return _RISK_ORDER[classify(operation)] >= _RISK_ORDER[threshold]


def _denial_message(operation: str, risk: str, review_mode: str, reason: str) -> str:
    """Explain a refusal well enough that an agent can ask for the right thing."""

    return (
        f"Refused to run {operation} ({risk} risk, review mode {review_mode}): "
        f"{reason}\n"
        f"To authorise this, re-run with --yes, or ask the developer to run it.\n"
        "Nothing was executed and no state was changed."
    )


def evaluate(
    root: Path,
    operation: str,
    *,
    acknowledged: bool = False,
    interactive: bool | None = None,
    json_output: bool = False,
    review_mode: str | None = None,
) -> SafetyDecision:
    """Decide whether an operation may run, without running or prompting.

    Kept separate from :func:`authorize` so a caller can show what *would*
    happen — a dry run, a plan — without triggering a prompt.
    """

    risk = classify(operation)
    mode = review_mode or StateRepository(root).load_project()["review_mode"]
    # JSON output means a machine is reading; prompting into a pipe would hang
    # a caller that has no way to answer.
    can_prompt = (
        sys.stdin.isatty() if interactive is None else interactive
    ) and not json_output

    if not requires_approval(operation, mode):
        return SafetyDecision(
            operation=operation,
            risk=risk,
            review_mode=mode,
            allowed=True,
            authorization="risk-below-threshold",
            message=f"{operation} is {risk} risk; {mode} review mode permits it.",
            interactive=can_prompt,
        )

    if acknowledged:
        if risk == ALWAYS_INTERACTIVE_RISK and not can_prompt:
            return SafetyDecision(
                operation=operation,
                risk=risk,
                review_mode=mode,
                allowed=False,
                authorization="denied",
                message=_denial_message(
                    operation,
                    risk,
                    mode,
                    "high-risk operations need a person present; --yes alone is "
                    "not sufficient in a non-interactive terminal",
                ),
                interactive=can_prompt,
            )
        return SafetyDecision(
            operation=operation,
            risk=risk,
            review_mode=mode,
            allowed=True,
            authorization="flag",
            message=f"{operation} was authorised with --yes.",
            interactive=can_prompt,
        )

    if not can_prompt:
        return SafetyDecision(
            operation=operation,
            risk=risk,
            review_mode=mode,
            allowed=False,
            authorization="denied",
            message=_denial_message(
                operation,
                risk,
                mode,
                "there is nobody to ask in a non-interactive terminal",
            ),
            interactive=False,
        )

    return SafetyDecision(
        operation=operation,
        risk=risk,
        review_mode=mode,
        allowed=False,
        authorization="prompt-required",
        message=f"{operation} is {risk} risk and needs confirmation.",
        interactive=True,
    )


def authorize(
    root: Path,
    operation: str,
    *,
    acknowledged: bool = False,
    json_output: bool = False,
    prompt_detail: str = "",
    interactive: bool | None = None,
) -> SafetyDecision:
    """Authorise an operation, prompting when a person is present.

    Raises :class:`ExecutionDeniedError` when the operation may not run. The
    caller must not proceed on a decision it did not check.
    """

    decision = evaluate(
        root,
        operation,
        acknowledged=acknowledged,
        interactive=interactive,
        json_output=json_output,
    )
    if decision.allowed:
        return decision
    if decision.authorization != "prompt-required":
        raise ExecutionDeniedError(decision)

    detail = f"\n{prompt_detail}" if prompt_detail else ""
    answer = (
        input(f"{operation} is {decision.risk} risk.{detail}\nProceed? [y/N]: ")
        .strip()
        .casefold()
    )
    if answer in {"y", "yes"}:
        return SafetyDecision(
            operation=decision.operation,
            risk=decision.risk,
            review_mode=decision.review_mode,
            allowed=True,
            authorization="interactive",
            message=f"{operation} was authorised interactively.",
            interactive=True,
        )
    raise ExecutionDeniedError(
        SafetyDecision(
            operation=decision.operation,
            risk=decision.risk,
            review_mode=decision.review_mode,
            allowed=False,
            authorization="denied",
            message=_denial_message(
                operation, decision.risk, decision.review_mode, "declined at the prompt"
            ),
            interactive=True,
        )
    )
