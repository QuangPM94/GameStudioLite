# Milestone Review

## Purpose

Compare milestone success criteria with evidence and make a defensible recommendation.

## When to use

Use for `/milestone-review` when findings can support a milestone decision or at a phase boundary.

## Required inputs

Milestone, criteria, evidence, issues, decisions, and build status.

## Optional inputs

Player reviews, test/run logs, media, telemetry, and human notes.

## Files to read

All canonical state, relevant prototype/review artifacts, and `.studio/templates/milestone-review.md`.

## State changes

Use transactional criterion commands to update definitions, links, explicit evaluations, and retirement. Record verdict/recommendation without automatically advancing phase or milestone.

## Execution procedure

1. Inspect active evidence with `studio evidence list`/`show`; do not count superseded or retracted records as current support.
2. Run `studio criterion list` and `studio criterion show` for every active required criterion. Inspect completion conditions, verification methods, active evidence classifications, and evaluation freshness.
3. Evaluate every criterion independently with `studio criterion evaluate` as `verified`, `partially-supported`, `unsupported`, or `contradicted`. An evidence record alone never makes a criterion verified.
4. Identify blocking issues and material unknowns. Inspect `studio dependency list` and `studio decision list`/`show` for hard ordering, blocking, weakly supported, resolved, or revisit-required decisions.
5. Distinguish an accessible build from a verified experience.
6. Choose `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP` as a recommendation; do not automatically change project phase/current milestone.
7. Create or update a meaningful unresolved fork with `studio decision add`/`update`, present the recommendation, and use `studio decision resolve` only after the owner chooses.
8. Recommend one next workflow, identify non-critical work, update review state, and regenerate reports.
9. Run `studio path check`; recalculate after criterion, verdict, blocker, dependency, decision, or evidence changes, then use `studio path show` to state whether active blockers/decisions/verification remain and name the exact next item.

## User decision points

Ask for approval of phase changes and any accepted blocker, altered criterion, or major investment trade-off.

## Outputs

Milestone review, criterion result table, evidence/limitations, verdict, recommendation, next milestone, and Direction Summary.

## Validation

Check all evidence and issue references, criterion coverage, and verdict enum; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Every criterion has a result and evidence/unknown status sufficient for the stated verdict.

## Next recommended workflows

`/vertical-slice` when prototype criteria warrant a boundary decision; otherwise `/critical-path`, `/iterate`, or `/clarify`.

## Failure and blocker behavior

Choose `PAUSE` or keep evaluation open when evidence is insufficient. Never convert unverified inference into a pass.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
