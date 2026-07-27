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

Update criterion results, supporting evidence, blocking issues, verdict, recommendation, and next milestone.

## Execution procedure

1. Inspect active evidence with `studio evidence list`/`show`; do not count superseded or retracted records as current support.
2. Evaluate every criterion independently as `verified`, `partially-supported`, `unsupported`, or `contradicted`. An evidence record alone never makes a criterion verified.
3. Identify blocking issues and material unknowns.
4. Distinguish an accessible build from a verified experience.
5. Choose `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP`.
6. Recommend one next workflow and identify non-critical work.
7. Update milestone state and regenerate reports.

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
