# Milestone Criteria

## Purpose

Create, update, evaluate, and retire the current milestone's success criteria, and never let evidence silently verify one.

## When to use

Use for `GS:milestone-criteria` when a milestone needs explicit success criteria defined, an existing criterion needs correction, new evidence should be checked against a criterion, or a criterion no longer applies. Legacy alias: `/milestone-criteria`.

## Required inputs

For a new criterion: a clear description, whether it is required or optional, a completion condition, a verification method, and an explicit verification policy. For an evaluation: the criterion ID and the evidence to inspect.

## Optional inputs

Related issues, related decisions, and supporting evidence links.

## Files to read

`AGENTS.md`, `.studio/state/milestone.json` (via `studio criterion list`/`show`), and `.studio/state/evidence.json`.

## State changes

Create or update a criterion with `studio criterion add` or `studio criterion update`. Record an explicit evaluation with `studio criterion evaluate`. Retire with `studio criterion retire`. Never edit `.studio/state/milestone.json` directly.

## Execution procedure

1. Read `AGENTS.md` and the current milestone, criteria, and evidence state.
2. Search `studio criterion list` for an existing criterion covering the same requirement.
3. For a new criterion, require: a clear description; `--required` or `--optional`; a concrete completion condition; a verification method; and exactly one `--verification-policy` from `observed-player-behavior`, `observed-runtime`, `automated-test`, `document-review`, `source-review`, `manual-approval`, or `mixed`. Never infer the policy from wording in the description.
4. Create or refine the record with `studio criterion add` or `studio criterion update`, linking related issues, decisions, and evidence.
5. For an evaluation, inspect the linked evidence with `studio evidence show` and only count active, relevant evidence.
6. Record an explicit `studio criterion evaluate` result with one of `unsupported`, `partially-supported`, `verified`, or `contradicted`, plus a reason and any limitations. The mere existence of linked evidence, a closed issue, a resolved decision, or a completed playbook never counts as verification by itself.
7. Retire a criterion that no longer applies with `studio criterion retire --reason`, preserving its history.
8. Capture the resulting `MC-` identifier(s) and support status.
9. Run `studio validate`.
10. Run `studio path check`; recalculate only when the change materially affects milestone readiness and the user asks.
11. Return the Direction Summary.

## User decision points

Ask when the required verification policy is unclear, when a required criterion should become optional (or vice versa), or when retiring a criterion changes what the milestone requires.

## Outputs

The `MC-` identifier(s), their lifecycle and support status, and any newly linked issues, decisions, or evidence.

## Validation

Run `studio validate` and `studio path check` after every write.

## Completion criteria

Every touched criterion has a concrete completion condition, an explicit verification policy, and, when evaluated, an explicit support status backed by a stated reason.

## Next recommended workflows

`GS:milestone-review` when enough criteria are evaluated to support a milestone recommendation; `GS:critical-path` when an unresolved criterion gates the path; otherwise `GS:next-step`.

## Failure and blocker behavior

Never mark a criterion `verified` because supporting evidence merely exists. If evidence is insufficient, record `unsupported` or `partially-supported` with the specific gap.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
