# Decision

## Purpose

Create, update, and resolve meaningful project decisions without substituting an agent recommendation for the user's final choice.

## When to use

Use for `/decision` when a question needs explicit options and trade-offs, when an existing decision needs refinement, or when the user has made a final choice that must be recorded.

## Required inputs

For a new decision: the question and its context. For a resolution: the user's explicit selected option or explicit custom decision.

## Optional inputs

Recommended option and reason, urgency, owner, required-by date, related issues and evidence, and trade-offs per option.

## Files to read

`AGENTS.md`, `.studio/state/decisions.json` (via `studio decision list`/`show`), and related issues/evidence.

## State changes

Create or update a decision with `studio decision add` or `studio decision update`. Resolve a decision only with `studio decision resolve`. Never edit `.studio/state/decisions.json` directly.

## Execution procedure

1. Read `AGENTS.md` and the current decision, issue, and evidence state.
2. Search `studio decision list` for an existing record covering the same question before creating a new one.
3. For a new decision, define the question and context, create two to six clear options, and identify the trade-off of each.
4. Optionally recommend one option with a stated reason; state plainly that this is a recommendation, not the user's decision.
5. Create or refine the record with `studio decision add` or `studio decision update`, linking relevant issues and evidence.
6. Resolve the decision with `studio decision resolve` only when the user explicitly selects an option or gives an explicit custom decision; never resolve on the agent's own recommendation.
7. Add a dependency with `studio dependency add` only when another record genuinely cannot proceed without this decision; do not create a speculative edge for a merely related record.
8. Capture the resulting `DEC-` identifier and its current status.
9. Run `studio validate`.
10. Run `studio path check`; recalculate only when the resolution materially changes what is unblocked and the user asks for it.
11. Return the Direction Summary.

## User decision points

Always: the final option (or custom decision) is the user's choice, never the agent's. Ask before resolving, and before adding a dependency that blocks other work on this decision.

## Outputs

The `DEC-` identifier, its current status (`open`, `ready`, `blocked`, `resolved`, `deferred`, `rejected`, or `superseded` as supported by the schema), and any newly linked issues, evidence, or dependencies.

## Validation

Run `studio validate` and `studio path check` after every write.

## Completion criteria

The decision record reflects the actual question, options, and trade-offs, and is resolved only when the user has explicitly chosen.

## Next recommended workflows

`/critical-path` when the resolution unblocks gated work; otherwise `/next-step`.

## Failure and blocker behavior

Never resolve a decision from an agent recommendation alone. If the user has not yet chosen, leave the decision open or ready and say so explicitly.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
