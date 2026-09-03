# Workflow readiness

"Can I run `GS:build-prototype` yet?" used to be answered by prose in a playbook
and an agent's reading of it. Prose cannot be checked, so a workflow could start
against a project that did not meet its own stated prerequisites and nothing
would notice.

Workflows now declare machine-readable requirements in
`.studio/workflow-catalog.json`, and the framework evaluates them against
canonical state and probed engine capabilities.

## Commands

```bash
studio workflow list              # every workflow, and whether it declares a gate
studio workflow ready             # what can run now, plus one recommendation
studio workflow ready --all       # include blocked workflows
studio workflow check build-prototype
studio workflow explain build-prototype
```

All of them are read-only. Knowing a workflow is blocked never advances a phase
or changes state on its own. `studio workflow check` exits non-zero when the
workflow is blocked, so it can gate a script.

## Three statuses, not two

| Status | Meaning |
| --- | --- |
| `ready` | Every declared requirement was checked and satisfied |
| `ready-with-unknowns` | Nothing blocks, but some checks could not be performed |
| `blocked` | At least one requirement is unmet |

The middle value exists because "everything checked out" and "nothing blocks,
but we could not verify some of it" are different amounts of confidence, and
collapsing them would let the framework sound more certain than it is.

## Two rules about unknowns

**A requirement that could not be evaluated is `unknown`, never satisfied.** A
requirement kind this version of the framework does not recognise is reported as
unknown with that reason attached — it must not read as one that passed.

**`unknown` does not block.** A project with no engine installed can still run
planning workflows. Refusing to proceed because an engine capability could not be
probed would make the framework unusable for exactly the projects it is supposed
to help most. Unknowns surface as caveats and the decision stays with a person.

## Declaring requirements

```json
{
  "id": "build-prototype",
  "requires": {
    "project_initialized": true,
    "prototype_hypothesis": true,
    "critical_path_ready": true
  }
}
```

| Requirement | Checks |
| --- | --- |
| `project_initialized` | Project identity is no longer the bootstrap placeholder |
| `prototype_hypothesis` | A falsifiable hypothesis is recorded |
| `critical_path_ready` | The path has items and is fresh |
| `engine_run_capability` | The resolved adapter reports `RUN` as ready |
| `engine_test_capability` | …reports `TEST` |
| `engine_build_capability` | …reports `BUILD` |
| `has_open_issues` | There is at least one open issue |
| `has_active_evidence` | There is at least one active evidence record |
| `has_active_criteria` | There is at least one active milestone criterion |
| `build_status` | Current build status is one of the listed values |
| `current_phase` | Current phase is one of the listed values |
| `no_blocking_decisions` | No unresolved decision has `blocking` urgency |

A workflow with no `requires` block is ready. Not declaring a gate must not mean
being gated — over-gating would make the framework refuse work a developer can
legitimately do, which is worse than not gating at all.

## Recommendation

`studio workflow ready` names exactly one next workflow, preferring one whose
declared phase matches the project's current phase.

When nothing is runnable it says so rather than naming something anyway. A
recommendation the project cannot act on is worse than admitting there isn't one.
