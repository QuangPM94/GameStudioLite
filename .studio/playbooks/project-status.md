# Project Status

## Purpose

Give a read-only summary of current project direction: phase, milestone, build status, blockers, decisions, criteria, and path freshness.

## When to use

Use for `GS:project-status` whenever the user wants a snapshot without changing anything, including mid-session check-ins. Legacy alias: `/project-status`.

## Required inputs

Current canonical state.

## Optional inputs

None.

## Files to read

`AGENTS.md`, `.studio/workflow-catalog.json`, and all canonical state under `.studio/state/`.

## State changes

None. `GS:project-status` never writes state, never regenerates reports, and never recalculates the critical path; it only reports what `studio path check` already says about freshness.

## Execution procedure

1. Run or inspect `studio status`, `studio path check`, and `studio path show`.
2. Summarize: current phase, current milestone, build status, open blockers (issues with `status` not resolved/accepted/wont-fix), pending decisions, unsupported or unevaluated milestone criteria, path freshness, and the current ready path item.
3. Recommend exactly one next workflow based on the summary above.
4. If the path is stale or absent, report that clearly and recommend `GS:critical-path` instead of calculating it.

## User decision points

None. If the user asks for a mutation while running `GS:project-status`, name the correct workflow (`GS:report-issue`, `GS:record-evidence`, `GS:decision`, `GS:milestone-criteria`, or `GS:critical-path`) instead of performing it here.

## Outputs

A concise read-only summary covering phase, milestone, build status, blockers, pending decisions, unsupported criteria, path freshness, ready path item, and recommended next workflow.

## Validation

Run `studio status`, `studio path check`, and `studio path show`. No write commands are used.

## Completion criteria

Every required summary field is present and traceable to inspected state, and exactly one next workflow is recommended.

## Next recommended workflows

`GS:critical-path` when the path is stale; otherwise the workflow implied by the ready path item, open decisions, or unresolved criteria (for example `GS:report-issue`, `GS:record-evidence`, `GS:decision`, `GS:milestone-criteria`, or `GS:next-step`).

## Failure and blocker behavior

If canonical state is missing or invalid, report the exact problem and recommend `studio validate` or `studio bootstrap` instead of guessing at project status.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
