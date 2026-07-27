# Vertical Slice Decision

## Purpose

Decide whether prototype evidence justifies a representative-quality vertical slice.

## When to use

Use for `/vertical-slice` after critical prototype issues are resolved or deliberately accepted.

## Required inputs

Milestone criteria/results, evidence, blocking issues, decisions, and current hypothesis.

## Optional inputs

Schedule, quality target, team capacity, and market constraints.

## Files to read

All canonical state, generated milestone review, game brief, prototype scope, and evaluations.

## State changes

Set phase to `vertical-slice-decision`; record exactly one verdict: `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP`. For `PROCEED`, set next milestone to vertical-slice planning without creating production architecture.

## Execution procedure

1. Compare each success criterion with supporting evidence and limitations.
2. Identify unresolved hypothesis, experience, and stability risks.
3. Inspect the phase-boundary choice with `studio decision list`/`show`; create or update one decision record with verdict options, recommendation, trade-offs, milestone, issues, and evidence.
4. For `PROCEED`, outline a bounded vertical-slice plan: representative loop, target quality, evidence goals, exclusions, and next planning step.
5. For other verdicts, identify one next experiment, decision, or pause condition.
6. After approval, resolve the decision with `studio decision resolve`, record the verdict in milestone state, and regenerate reports.
7. Run `studio path check`; recalculate for the approved milestone state and use `studio path show` before recommending investment work.

## User decision points

The user approves the phase-boundary verdict in guided/strict mode and any investment/scope commitment. Present alternatives when evidence permits more than one defensible direction.

## Outputs

One verdict, rationale, recommendation, next milestone, optional bounded vertical-slice plan, and Direction Summary.

## Validation

Ensure evidence supports each criterion result and verdict is valid; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

One evidence-backed verdict exists and the next milestone/action is explicit.

## Next recommended workflows

For `PROCEED`, a future bounded vertical-slice planning workflow; otherwise `/iterate`, `/clarify`, or `/next-step`.

## Failure and blocker behavior

Use `PAUSE` when necessary evidence or capacity is unavailable. Do not default to `PROCEED` from enthusiasm or source inference.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
