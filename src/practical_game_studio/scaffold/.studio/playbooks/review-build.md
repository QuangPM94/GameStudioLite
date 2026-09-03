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

1. Run `studio doctor` and record which capabilities are READY, UNAVAILABLE, and UNKNOWN. Do not treat UNKNOWN as either.
2. Run `studio test`, then `studio verify --level runtime`. Read the `What this did NOT establish` section as carefully as the status.
3. Inspect the produced records: `studio execution list`, `studio execution show RUN-####`, `studio artifact verify`.
4. Compare implemented interactions/states with approved scope and criteria.
5. Classify stability, defects, and verification gaps by evidence label. A `passed` RUN is `observed` evidence about a process, never about gameplay.
6. Decide whether player review is supported and state limitations.
7. Record evidence with `studio evidence add --run RUN-#### --artifact ART-####`, starting from the proposals `studio verify` printed and keeping their limitations; use `studio evidence list`/`show` before updating or superseding an existing record.
8. Use `studio issue add` for a new build finding or `studio issue update` for an existing one, linking the canonical evidence ID rather than a file path. Open an issue for a `failed` run, not for an `unknown` one: an unknown result has not shown anything to be broken.
9. Run `studio criterion support MC-###` for each current criterion to see what its evidence now supports. That command is read-only; evaluate separately and explicitly with `studio criterion evaluate`.
10. Transactional issue/evidence writes regenerate all reports.

## User decision points

Ask when accepting a known blocker or changing criteria/scope is required to proceed.

## Outputs

Build-readiness finding, technical issues, evidence references, unverified areas, and Direction Summary.

## Validation

Run `studio verify --level runtime`, `studio artifact verify`, `studio validate`, `studio report`, and `studio status`.

Where execution tooling is unavailable, run the engine manually and record the result as `user-reported` evidence naming exactly what was and was not observed. Never record a manual impression as `observed` runtime evidence.

## Completion criteria

Launchability and review readiness are evidenced or a concrete blocking issue is recorded.

## Next recommended workflows

`GS:playtest-review` when evidence is sufficient; `GS:critical-path` when blocked.

## Failure and blocker behavior

Record exact failing command/context, severity, player/milestone impact, and recommended action. Keep inaccessible runtime behavior `UNKNOWN`.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
