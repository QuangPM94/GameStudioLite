"""Whether a workflow can actually run, computed rather than guessed.

Before this, "can I run `GS:build-prototype` yet?" was answered by prose in a
playbook and an agent's reading of it. Prose cannot be checked, so a workflow
could be started against a project that did not meet its own stated
prerequisites, and nothing would notice.

A workflow now declares machine-readable requirements in the catalog, and this
module evaluates them against canonical state and probed capabilities. Two rules
shape the result:

A requirement that could not be evaluated is `unknown`, never satisfied. The
framework must not let a workflow start on the strength of a check it failed to
perform.

`unknown` does not block. A project with no engine installed can still run
planning workflows, and refusing to proceed because an engine capability could
not be probed would make the framework unusable for exactly the projects it is
supposed to help most.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state import CanonicalState, StateRepository, load_json
from .workflow_commands import canonical_command, catalog_workflows_by_id

#: A requirement is satisfied, unmet, or could not be determined.
OUTCOMES = ("satisfied", "unmet", "unknown")

#: Requirement kinds a catalog may declare. Anything else is reported as
#: `unknown` with the reason, rather than silently ignored: a requirement the
#: framework does not understand must not read as one that passed.
REQUIREMENT_KINDS = (
    "project_initialized",
    "prototype_hypothesis",
    "critical_path_ready",
    "engine_run_capability",
    "engine_test_capability",
    "engine_build_capability",
    "has_open_issues",
    "has_active_evidence",
    "has_active_criteria",
    "build_status",
    "current_phase",
    "no_blocking_decisions",
)


@dataclass(frozen=True, slots=True)
class Requirement:
    """One evaluated prerequisite."""

    name: str
    expected: Any
    outcome: str
    detail: str

    @property
    def blocks(self) -> bool:
        """Whether this requirement should stop the workflow.

        Only `unmet` blocks. An `unknown` requirement is surfaced as a caveat so
        a person can decide, because refusing to proceed on an unperformed check
        would strand planning-only projects.
        """

        return self.outcome == "unmet"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.name,
            "expected": self.expected,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class WorkflowReadiness:
    """Whether one workflow can run, and exactly why or why not."""

    workflow_id: str
    canonical: str
    phase: str | None
    requirements: tuple[Requirement, ...]

    @property
    def blockers(self) -> tuple[Requirement, ...]:
        return tuple(item for item in self.requirements if item.blocks)

    @property
    def caveats(self) -> tuple[Requirement, ...]:
        return tuple(item for item in self.requirements if item.outcome == "unknown")

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def status(self) -> str:
        """`ready`, `blocked`, or `ready-with-unknowns`.

        The third value exists so a caller can tell "everything checked out"
        from "nothing blocks, but some checks could not be performed" — which
        are different amounts of confidence.
        """

        if self.blockers:
            return "blocked"
        return "ready-with-unknowns" if self.caveats else "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "canonical": self.canonical,
            "phase": self.phase,
            "status": self.status,
            "ready": self.ready,
            "requirements": [item.to_dict() for item in self.requirements],
            "blockers": [item.to_dict() for item in self.blockers],
            "caveats": [item.to_dict() for item in self.caveats],
        }


class WorkflowReadinessError(ValueError):
    """A workflow readiness question could not be answered as asked."""


def load_catalog(root: Path) -> dict[str, Any]:
    """Load the workflow catalog for a project."""

    catalog = load_json(root / ".studio" / "workflow-catalog.json")
    if not isinstance(catalog, dict):
        raise WorkflowReadinessError("workflow catalog is not a JSON object")
    return catalog


def _capabilities(root: Path) -> tuple[str, ...] | None:
    """Probed engine capabilities, or None when nothing could be probed.

    None and `()` mean different things: no adapter recognised the project
    versus an adapter that reports nothing is ready. Only the first is
    `unknown`.
    """

    from .adapters import resolve_adapter

    adapter = resolve_adapter(root)
    if adapter is None:
        return None
    return adapter.probe(root).available_capabilities


def _capability_requirement(
    name: str, capability: str, capabilities: tuple[str, ...] | None
) -> Requirement:
    if capabilities is None:
        return Requirement(
            name=name,
            expected=capability,
            outcome="unknown",
            detail=(
                "No engine adapter recognises this project, so engine "
                "capabilities could not be probed."
            ),
        )
    if capability in capabilities:
        return Requirement(
            name=name,
            expected=capability,
            outcome="satisfied",
            detail=f"the resolved adapter reports {capability} as ready",
        )
    return Requirement(
        name=name,
        expected=capability,
        outcome="unmet",
        detail=(
            f"the resolved adapter does not report {capability}; run "
            "`studio doctor` for the reason"
        ),
    )


def _evaluate_requirement(
    name: str,
    expected: Any,
    state: CanonicalState,
    capabilities: tuple[str, ...] | None,
) -> Requirement:
    """Evaluate one declared requirement against state and probed capabilities."""

    project = state["project"]

    if name == "project_initialized":
        # A placeholder name means bootstrap ran but nobody said what the game
        # is, which most workflows genuinely cannot proceed from.
        initialized = project["project_name"] != "Untitled Game"
        return Requirement(
            name,
            expected,
            "satisfied" if initialized == expected else "unmet",
            "project identity is recorded"
            if initialized
            else "project identity is still the bootstrap placeholder",
        )

    if name == "prototype_hypothesis":
        present = bool(project.get("prototype_hypothesis"))
        return Requirement(
            name,
            expected,
            "satisfied" if present == expected else "unmet",
            "a prototype hypothesis is recorded"
            if present
            else "no falsifiable prototype hypothesis is recorded",
        )

    if name == "critical_path_ready":
        path = state["critical_path"]
        fresh = path.get("freshness", {}).get("status") == "current"
        has_items = bool(path.get("items"))
        ready = fresh and has_items
        return Requirement(
            name,
            expected,
            "satisfied" if ready == expected else "unmet",
            f"critical path has {len(path.get('items', []))} item(s) and is "
            f"{path.get('freshness', {}).get('status', 'unknown')}",
        )

    if name == "engine_run_capability":
        return _capability_requirement(name, "RUN", capabilities)
    if name == "engine_test_capability":
        return _capability_requirement(name, "TEST", capabilities)
    if name == "engine_build_capability":
        return _capability_requirement(name, "BUILD", capabilities)

    if name == "has_open_issues":
        open_issues = [
            issue
            for issue in state["issues"]["issues"]
            if issue["status"] in {"open", "acknowledged", "in-progress", "blocked"}
        ]
        present = bool(open_issues)
        return Requirement(
            name,
            expected,
            "satisfied" if present == expected else "unmet",
            f"{len(open_issues)} open issue(s)",
        )

    if name == "has_active_evidence":
        active = [
            item for item in state["evidence"]["evidence"] if item["status"] == "active"
        ]
        present = bool(active)
        return Requirement(
            name,
            expected,
            "satisfied" if present == expected else "unmet",
            f"{len(active)} active evidence record(s)",
        )

    if name == "has_active_criteria":
        active = [
            item
            for item in state["milestone"]["criteria_results"]
            if item["lifecycle_status"] == "active"
        ]
        present = bool(active)
        return Requirement(
            name,
            expected,
            "satisfied" if present == expected else "unmet",
            f"{len(active)} active milestone criterion/criteria",
        )

    if name == "build_status":
        actual = project["current_build_status"]
        accepted = expected if isinstance(expected, list) else [expected]
        return Requirement(
            name,
            expected,
            "satisfied" if actual in accepted else "unmet",
            f"build status is {actual}",
        )

    if name == "current_phase":
        actual = project["current_phase"]
        accepted = expected if isinstance(expected, list) else [expected]
        return Requirement(
            name,
            expected,
            "satisfied" if actual in accepted else "unmet",
            f"current phase is {actual}",
        )

    if name == "no_blocking_decisions":
        blocking = [
            decision
            for decision in state["decisions"]["decisions"]
            if decision["urgency"] == "blocking"
            and decision["status"] in {"open", "ready", "blocked", "deferred"}
        ]
        clear = not blocking
        return Requirement(
            name,
            expected,
            "satisfied" if clear == expected else "unmet",
            f"{len(blocking)} unresolved blocking decision(s)",
        )

    # An unrecognised requirement must never read as satisfied.
    return Requirement(
        name,
        expected,
        "unknown",
        f"this version of the framework does not know the requirement {name!r}",
    )


def evaluate_workflow_readiness(
    root: Path, workflow_id: str, *, catalog: dict[str, Any] | None = None
) -> WorkflowReadiness:
    """Evaluate one workflow's declared requirements."""

    catalog = catalog if catalog is not None else load_catalog(root)
    workflows = catalog_workflows_by_id(catalog)
    if workflow_id not in workflows:
        raise WorkflowReadinessError(
            f"unknown workflow {workflow_id!r}; the catalog defines: "
            + ", ".join(sorted(workflows))
        )
    workflow = workflows[workflow_id]
    state = StateRepository(root).load_all()
    declared = workflow.get("requires") or {}
    capabilities = (
        _capabilities(root)
        if any(name.startswith("engine_") for name in declared)
        else ()
    )
    return WorkflowReadiness(
        workflow_id=workflow_id,
        canonical=workflow.get("canonical", canonical_command(workflow_id)),
        phase=workflow.get("phase"),
        requirements=tuple(
            _evaluate_requirement(name, expected, state, capabilities)
            for name, expected in sorted(declared.items())
        ),
    )


def get_workflow_blockers(
    root: Path, workflow_id: str, *, catalog: dict[str, Any] | None = None
) -> tuple[Requirement, ...]:
    """Return only the requirements that stop this workflow."""

    return evaluate_workflow_readiness(root, workflow_id, catalog=catalog).blockers


def explain_workflow_blockers(readiness: WorkflowReadiness) -> str:
    """Render a human explanation of why a workflow can or cannot run."""

    lines = [
        f"{readiness.canonical} — {readiness.status}",
        "",
        "Requirements:",
    ]
    if readiness.requirements:
        lines.extend(
            f"- {item.name}: {item.outcome} — {item.detail}"
            for item in readiness.requirements
        )
    else:
        lines.append("- none declared; this workflow has no machine-readable gate")

    # Both sections print even when empty. "Nothing blocks this" and "we did not
    # look" must not render identically.
    for title, items in (
        ("Blockers", readiness.blockers),
        ("Could not be determined", readiness.caveats),
    ):
        lines.extend(["", f"{title}:"])
        lines.extend([f"- {item.name}: {item.detail}" for item in items] or ["- none"])

    if readiness.caveats and not readiness.blockers:
        lines.extend(
            [
                "",
                (
                    "Nothing blocks this workflow, but the unknowns above were "
                    "not verified. Proceeding is your call."
                ),
            ]
        )
    return "\n".join(lines)


def list_ready_workflows(
    root: Path, *, catalog: dict[str, Any] | None = None
) -> tuple[WorkflowReadiness, ...]:
    """Evaluate every workflow, readiest first, then by id for stability."""

    catalog = catalog if catalog is not None else load_catalog(root)
    evaluated = [
        evaluate_workflow_readiness(root, workflow_id, catalog=catalog)
        for workflow_id in sorted(catalog_workflows_by_id(catalog))
    ]
    order = {"ready": 0, "ready-with-unknowns": 1, "blocked": 2}
    evaluated.sort(key=lambda item: (order[item.status], item.workflow_id))
    return tuple(evaluated)


def recommend_next_workflow(
    root: Path, *, catalog: dict[str, Any] | None = None
) -> WorkflowReadiness | None:
    """Recommend exactly one workflow, preferring the current phase's.

    Returns None rather than guessing when nothing is runnable. A recommendation
    the project cannot act on is worse than saying there isn't one.
    """

    catalog = catalog if catalog is not None else load_catalog(root)
    project = StateRepository(root).load_project()
    phase = project["current_phase"]
    candidates = [
        item for item in list_ready_workflows(root, catalog=catalog) if item.ready
    ]
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.phase == phase:
            return candidate
    return candidates[0]
