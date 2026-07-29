# Review Build

## Purpose

Verify build accessibility, scope compliance, technical stability, and readiness for player-experience review.

## When to use

Use for `GS:review-build` after a build increment or when adopting an existing build. Legacy alias: `/review-build`.

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
6. Record reproducible commands, test output, build logs, runtime observations, and limitations with `studio evidence add`; use `studio evidence list`/`show` before updating or superseding an existing record.
7. Use `studio issue add` for a new build finding or `studio issue update` for an existing one, linking the canonical evidence ID rather than a file path.
8. Transactional issue/evidence writes regenerate all reports.

## User decision points

Ask when accepting a known blocker or changing criteria/scope is required to proceed.

## Outputs

Build-readiness finding, technical issues, evidence references, unverified areas, and Direction Summary.

## Validation

Run applicable project checks plus `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Launchability and review readiness are evidenced or a concrete blocking issue is recorded.

## Next recommended workflows

`GS:playtest-review` when evidence is sufficient; `GS:critical-path` when blocked.

## Failure and blocker behavior

Record exact failing command/context, severity, player/milestone impact, and recommended action. Keep inaccessible runtime behavior `UNKNOWN`.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
