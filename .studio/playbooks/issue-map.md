# Issue Map

## Purpose

Convert findings into a small, connected map of problems that affect the milestone.

## When to use

Use for `/issue-map` after a build or player review.

## Required inputs

Review findings, evidence, milestone, and success criteria.

## Optional inputs

Existing issue history, estimates, and dependency notes.

## Files to read

Issues, evidence, decisions, milestone, critical path, and relevant review artifacts.

## State changes

Create or update issue records, relationships, severity, milestone/player impact, and user-decision flags.

## Execution procedure

1. Deduplicate findings by underlying cause.
2. Classify severity/category and connect evidence.
3. Describe player and milestone impact separately.
4. Identify dependencies, issues blocked, alternatives, effort, owner, and whether user input is required.
5. Use `studio issue list` and `studio issue show` to inspect history, then `studio issue add` or `studio issue update` for each accepted record. Prefer `--dry-run` when relationships or path membership change.
6. Separate active milestone issues from later work. Do not delete history.
7. Transactional issue commands regenerate open-issues and direction reports.

## User decision points

Ask only where resolution changes mechanics/fantasy/scope/criteria or accepts a critical risk.

## Outputs

Open issue map, decision queue additions, explicit non-critical work, and Direction Summary.

## Validation

Ensure IDs and references resolve, severity values are valid, and open issues have recommended actions; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Every material finding is mapped, deliberately deferred, or marked unknown without producing an undifferentiated backlog.

## Next recommended workflows

`/critical-path`.

## Failure and blocker behavior

Keep insufficiently supported findings as `UNKNOWN`/investigation work; do not inflate severity to force priority.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
