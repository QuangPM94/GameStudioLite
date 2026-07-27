# Start

## Purpose

Inspect the repository and route the user to the smallest appropriate entry workflow.

## When to use

Use for a new session, an unknown project, `/start`, or uncertain workflow intent. If `project_name` is still `Untitled Game`, initialize identity first with `studio init`.

## Required inputs

Repository access, `.studio/config.json`, and initialized project identity.

## Optional inputs

User idea, engine/platform preference, existing build, run instructions, and prior artifacts.

## Files to read

`AGENTS.md`, `.studio/config.json`, `.studio/workflow-catalog.json`, all canonical state, and engine/project manifests found during inspection.

## State changes

Update the project profile, detected phase, build status, assumptions, and recommended entry workflow. Do not overwrite known values with guesses.

## Execution procedure

1. Read `.studio/state/project.json`. If it still contains the Phase A placeholder, collect the project name and run `studio init`; use `--dry-run` first when proposed detection needs review.
2. Determine whether the game repository is empty or existing.
3. Detect engine, engine version, platform, game artifacts, tests, build outputs, and run instructions. Treat CLI engine detection as a suggestion, not runtime proof.
4. Classify the current stage as idea, prototype, vertical slice, or production project; label uncertain classification `INFERRED`.
5. Check whether a build is accessible and distinguish its existence from verified launchability.
6. Produce the project profile, detected phase, and recommended entry workflow.
7. Run `studio path check`; calculate when absent/stale, then use `studio path show` to identify the exact recommended item.
8. Apply state changes through the validated transaction layer, then run `studio validate` and present the Direction Summary.

## User decision points

Ask only when engine/platform intent conflicts with detected files, the stage cannot be safely inferred, or routing depends on different core goals. Recommend the least-assumptive route.

## Outputs

Project profile, detected phase, recommended entry workflow, updated project state, and generated reports.

## Validation

Run `studio validate` and `studio status`. Transactional mutations regenerate reports.

## Completion criteria

The repository stage and build accessibility are recorded without unsupported claims, and one entry workflow is recommended.

## Next recommended workflows

`/clarify` for an unclear hypothesis; `/prototype-plan` for a clear hypothesis; `/review-build` for an existing accessible build.

## Failure and blocker behavior

Record inaccessible tools/builds as concrete blockers or unknowns. Do not infer launch success from project files.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
