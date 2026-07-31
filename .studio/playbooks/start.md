# Start

## Purpose

Inspect the repository and route the user to the smallest appropriate entry workflow.

## When to use

Use `GS:start` for a new, unknown, uninitialized, or intake-stage project, or when workflow intent is otherwise uncertain. If `project_name` is still `Untitled Game`, initialize identity first with `studio init`. Use `GS:resume` instead when the project is already initialized and this is simply a new AI-agent session continuing existing state. Legacy alias: `/start`.

## Required inputs

Repository access, `.studio/config.json`, and initialized project identity.

## Optional inputs

User idea, engine/platform preference, preferred AI client, existing engine MCP or editor-control tooling, existing game brief, existing build, run instructions, and prior artifacts.

## Files to read

`AGENTS.md`, `.studio/config.json`, `.studio/workflow-catalog.json`, all canonical state, engine/project manifests found during inspection, and accessible AI-client MCP/tool configuration.

## State changes

Update the project profile, detected phase, build status, assumptions/blockers about engine MCP readiness, and recommended entry workflow. Do not overwrite known values with guesses.

## Execution procedure

1. Read `.studio/state/project.json`. If it still contains the Phase A placeholder, collect the project name and run `studio init`; use `--dry-run` first when proposed detection needs review.
2. Determine whether the game repository is empty or existing.
3. Detect engine, engine version, platform, starter game brief, game artifacts, tests, build outputs, and run instructions. Treat CLI engine detection as a suggestion, not runtime proof.
4. Determine engine MCP readiness before recommending build work:
   - Identify whether a known MCP or equivalent editor-control integration exists for the detected or intended engine.
   - Inspect accessible AI-client MCP/tool configuration to determine whether that integration is already installed and enabled. If configuration is inaccessible, label the readiness `UNKNOWN` and state the exact file, command, or UI the human should check.
   - If a stable MCP exists but is not installed, recommend installing it before `GS:prototype-plan` or `GS:build-prototype`; install it only when the environment permits the change and the human approves any network, global-config, credential, or editor-side modification.
   - If the only available MCP is experimental, ask the human whether to use it. Present the trade-off between better editor interaction and instability/security/maintenance risk, recommend the conservative default, and do not install or rely on it until the human explicitly chooses.
   - If no MCP exists for the chosen engine, record that editor interaction will use CLI/files/manual editor steps instead. This is a workflow constraint, not evidence that the engine cannot be used.
5. Classify the current stage as idea, prototype, vertical slice, or production project; label uncertain classification `INFERRED`.
6. Check whether a build is accessible and distinguish its existence from verified launchability.
7. Produce the project profile, detected phase, MCP readiness, and recommended entry workflow. If a concise game brief is missing or lacks what the game is, how to play, the core idea, or the prototype hypothesis, recommend `GS:clarify` before any build workflow.
8. Inspect `studio criterion list` and `studio dependency list`; use their supported commands for structural corrections rather than editing milestone/dependency JSON.
9. Run `studio path check`; calculate when absent/stale, then use `studio path show` to identify the exact recommended item.
10. Apply state changes through the validated transaction layer without automatically changing phase/milestone, then run `studio validate` and present the Direction Summary.

## User decision points

Ask only when engine/platform intent conflicts with detected files, the stage cannot be safely inferred, routing depends on different core goals, or using an experimental engine MCP would change security, stability, or maintenance risk. Recommend the least-assumptive route.

## Outputs

Project profile, detected phase, MCP readiness, recommended entry workflow, updated project state, and generated reports.

## Validation

Run `studio validate` and `studio status`. Transactional mutations regenerate reports.

## Completion criteria

The repository stage, MCP readiness, and build accessibility are recorded without unsupported claims, and one entry workflow is recommended.

## Next recommended workflows

`GS:clarify` for an unclear hypothesis; `GS:prototype-plan` for a clear hypothesis; `GS:review-build` for an existing accessible build.

## Failure and blocker behavior

Record inaccessible MCP tooling, editor tools, and builds as concrete blockers or unknowns. Do not infer MCP availability, editor control, or launch success from project files.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
