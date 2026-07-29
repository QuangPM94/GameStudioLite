# Resume

## Purpose

Continue an existing project from its current recorded state at the start of a new AI-agent session.

## When to use

Use for `GS:resume` whenever an AI-agent session opens on a project that already has `.studio/state/`. This is the normal entrypoint for a new session on an existing, already-initialized project; it is distinct from `GS:start`, which is for new, unknown, uninitialized, or intake-stage projects. Legacy alias: `/resume`.

## Required inputs

Repository access and existing canonical state under `.studio/state/`.

## Optional inputs

A stated user goal for this session.

## Files to read

`AGENTS.md`, `.studio/workflow-catalog.json`, and all canonical state (`project.json`, `issues.json`, `decisions.json`, `dependencies.json`, `evidence.json`, `milestone.json`, `critical-path.json`).

## State changes

None. `GS:resume` is read-only. It never runs `studio bootstrap` or `studio init`, and it never resets phase, milestone, issues, decisions, evidence, dependencies, criteria, reports, or history.

## Execution procedure

1. Read `AGENTS.md` to reload the workflow and evidence contract.
2. Run or inspect `studio status`, `studio path check`, and `studio path show`.
3. Read the current phase, milestone, build status, open issues, pending decisions, and unresolved criteria directly from state; do not infer them from chat history.
4. Do not run `studio bootstrap` or `studio init`. Do not restart intake automatically, even if the conversation looks like a first session.
5. If `studio path check` reports the path is fresh, identify the exact ready `CP-` item from `studio path show`.
6. If the path is stale or absent, say so explicitly and recommend `GS:critical-path` to recalculate; do not calculate it from inside `GS:resume`.
7. Route to the exact next workflow implied by current state (the recommended workflow in `project.json`, the ready path item, or an open decision), without expanding scope.
8. Return the Direction Summary.

## User decision points

Ask only when the user's stated goal for this session conflicts with the recommended next workflow, or when routing depends on a choice only the user can make.

## Outputs

A current-state summary, the exact next workflow alias, and the ready critical-path item (or the reason none is ready).

## Validation

Run `studio status`, `studio path check`, and `studio path show`. `GS:resume` performs no writes, so `studio validate` is only needed if state looked inconsistent.

## Completion criteria

The user has an accurate picture of current phase, milestone, blockers, and one exact next workflow, without any project state having been reset.

## Next recommended workflows

Exactly the routed alias: `GS:project-status`, `GS:critical-path`, `GS:next-step`, or the specific phase workflow that continues the current milestone.

## Failure and blocker behavior

If `.studio/state/` does not exist, report that GameStudioLite has not been attached to this project and recommend `studio bootstrap`; do not run it automatically. If state exists but looks corrupted, report the exact validation problem instead of guessing at intent.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
