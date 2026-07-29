# Next Step

## Purpose

Recommend exactly one immediately useful action from current state.

## When to use

Use for `GS:next-step`, at session boundaries, or when direction is unclear. Legacy alias: `/next-step`.

## Required inputs

Current canonical state and critical path.

## Optional inputs

Available time, tools, and user constraints.

## Files to read

All canonical state and the relevant first-item playbook.

## State changes

None. `GS:next-step` is normally read-only: it selects and explains, it does not calculate the path or mutate records itself.

## Execution procedure

1. Run `studio path check`. If the path is absent or stale, report that plainly and recommend `GS:critical-path` to recalculate; do not run `studio path calculate` from inside `GS:next-step`.
2. Use `studio path show` to confirm goal, evidence gaps, blockers, manual controls, and the recommended-next item.
3. Use `studio issue list`/`show`, `studio evidence list`/`show`, `studio decision list`/`show`, `studio dependency list`/`show`, and `studio criterion list`/`show` instead of reading generated Markdown as state. Treat only active evidence as current support and only explicit evaluation as criterion truth.
4. Select exactly one ready, unblocked, high-value action — never an item whose prerequisites are not yet satisfied. Use `studio path explain CP-ID` when its rationale is questioned.
5. State why it is next, what completing it means, and which existing workflow should execute it.
6. Name the specific work that should not be started yet, and why (blocked, lower priority, or not milestone-gating).
7. If a decision blocks the only ready item, name the exact decision and recommend `GS:decision` instead of resolving it here.
8. Return the Direction Summary.

## User decision points

None normally. If no action is possible without a strategic user choice, name the exact blocking decision and recommend `GS:decision`; do not create or resolve it from inside `GS:next-step`.

## Outputs

Exactly one recommended action, the exact workflow alias that executes it, its rationale, what completion means, and the specific work that should not start yet.

## Validation

Run `studio path check` and `studio status`. `GS:next-step` performs no writes, so `studio validate` and `studio report` are not expected to be needed.

## Completion criteria

The user has one executable next workflow tied directly to the milestone.

## Next recommended workflows

Exactly the selected alias.

## Failure and blocker behavior

Do not list parallel priorities as a substitute for choosing. If blocked, make blocker resolution the next action.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
