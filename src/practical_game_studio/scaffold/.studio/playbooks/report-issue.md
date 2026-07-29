# Report Issue

## Purpose

Record one concrete issue from a user report, inspection, build review, runtime failure, or playtest finding.

## When to use

Use for `GS:report-issue` whenever a specific, actionable problem is identified. Use one invocation per distinct underlying cause, not per symptom. Legacy alias: `/report-issue`.

## Required inputs

A concrete description of the problem: what happened, and where or when it was observed.

## Optional inputs

Severity, category, player impact, milestone impact, recommended action, effort, owner, and related evidence or issues.

## Files to read

`AGENTS.md`, `.studio/state/issues.json` (via `studio issue list`/`show`), and `.studio/state/evidence.json` when the report references existing evidence.

## State changes

Create or update exactly one issue record with `studio issue add` or `studio issue update`. Never edit `.studio/state/issues.json` directly.

## Execution procedure

1. Read `AGENTS.md` and the current project state.
2. Search existing issues with `studio issue list` and inspect close matches with `studio issue show` to avoid creating a duplicate.
3. Ask the user only for information that materially changes severity, category, or the recommended action; do not ask for details that do not change the record.
4. Propose severity, category, player impact, milestone impact, recommended action, and owner, and clearly label them as a proposed recommendation rather than a confirmed fact until the user confirms or the source (for example a runtime error) makes them a fact.
5. If a matching issue exists, refine it with `studio issue update` instead of creating a duplicate; otherwise create it with `studio issue add`.
6. Capture the resulting `ISS-` identifier.
7. Run `studio validate`.
8. Run `studio path check`; report its freshness but do not recalculate the path unless the user explicitly asks or the workflow contract requires it.
9. Do not mark the issue `--on-critical-path` or otherwise place it on the critical path automatically; that determination belongs to `GS:critical-path`.
10. Return the Direction Summary.

## User decision points

Ask before recording a proposed severity as confirmed, before closing or resolving the issue, and before adding the issue to the critical path.

## Outputs

The created or updated `ISS-` identifier, its proposed vs. confirmed severity, and path freshness.

## Validation

Run `studio validate` and `studio path check` after every write.

## Completion criteria

Exactly one issue record accurately reflects the reported problem, with no duplicate created and no automatic critical-path placement.

## Next recommended workflows

`GS:record-evidence` when the report includes supporting evidence; `GS:critical-path` only when the user asks whether the issue affects the milestone path; otherwise `GS:next-step`.

## Failure and blocker behavior

If the report is too vague to record a concrete issue, ask the minimum clarifying question instead of inventing details. Never fabricate severity, impact, or evidence.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
