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

1. Confirm goal, evidence, blockers, and pending decisions.
2. Use `studio issue list`/`show` and `studio evidence list`/`show` instead of reading generated Markdown as state. Treat only active evidence as current support.
3. Select the first unblocked critical-path item; if none, choose the missing decision or verification that unlocks one.
4. Recommend one workflow and define its expected outcome.
5. Name important work that should not start.
6. Return the Direction Summary.

## User decision points

Ask only when no action is possible without a strategic user choice; present options and recommend one.

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
