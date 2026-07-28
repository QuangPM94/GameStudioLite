# Next Step

## Purpose

Recommend exactly one immediately useful action from current state.

## When to use

Use for `/next-step`, at session boundaries, or when direction is unclear.

## Required inputs

Current canonical state and critical path.

## Optional inputs

Available time, tools, and user constraints.

## Files to read

All canonical state and the relevant first-item playbook.

## State changes

Normally none beyond correcting stale direction. Regenerate reports when state changed.

## Execution procedure

1. Run `studio path check`; if absent or stale, preview and run `studio path calculate`.
2. Use `studio path show` to confirm goal, evidence gaps, blockers, manual controls, and the recommended-next item.
3. Use `studio issue list`/`show`, `studio evidence list`/`show`, `studio decision list`/`show`, `studio dependency list`/`show`, and `studio criterion list`/`show` instead of reading generated Markdown as state. Treat only active evidence as current support and only explicit evaluation as criterion truth.
4. Select the exact recommended `CP-` item; use `studio path explain CP-ID` when its rationale is questioned. If a decision unlocks it, update the existing record with issues/evidence and present its recommendation before asking.
5. Recommend one workflow and define its expected outcome.
6. Name important work that should not start.
7. Return the Direction Summary.

## User decision points

Ask only when no action is possible without a strategic user choice. Use `studio decision add`/`update`, present options and a recommendation, then `studio decision resolve` after the choice.

## Outputs

One recommended action, exact workflow alias, rationale, expected evidence, and deferred work.

## Validation

Run `studio validate` and `studio status`; run `studio report` if direction state was corrected.

## Completion criteria

The user has one executable next workflow tied directly to the milestone.

## Next recommended workflows

Exactly the selected alias.

## Failure and blocker behavior

Do not list parallel priorities as a substitute for choosing. If blocked, make blocker resolution the next action.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
