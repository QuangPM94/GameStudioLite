# Review Build

## Purpose

Verify build accessibility, scope compliance, technical stability, and readiness for player-experience review.

## When to use

Use for `/review-build` after a build increment or when adopting an existing build.

## Required inputs

Build/run instructions and current success criteria.

## Optional inputs

Runtime access, test logs, crash logs, screenshots, video, and platform tooling.

## Files to read

Project, issues, evidence, critical path, prototype scope/criteria, source, tests, and run instructions.

## State changes

Update build status, last verified date, technical issues, evidence, and readiness. Do not change design criteria silently.

## Execution procedure

1. Check run instructions and prerequisites.
2. Run the narrowest reliable build, test, and launch/smoke checks available.
3. Compare implemented interactions/states with approved scope and criteria.
4. Classify stability, defects, and verification gaps by evidence label.
5. Decide whether player review is supported and state limitations.
6. Update state and reports.

## User decision points

Ask when accepting a known blocker or changing criteria/scope is required to proceed.

## Outputs

Build-readiness finding, technical issues, evidence references, unverified areas, and Direction Summary.

## Validation

Run applicable project checks plus `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Launchability and review readiness are evidenced or a concrete blocking issue is recorded.

## Next recommended workflows

`/playtest-review` when evidence is sufficient; `/critical-path` when blocked.

## Failure and blocker behavior

Record exact failing command/context, severity, player/milestone impact, and recommended action. Keep inaccessible runtime behavior `UNKNOWN`.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
