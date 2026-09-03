# Build Prototype

## Purpose

Deliver a launchable prototype increment that tests the approved hypothesis.

## When to use

Use for `GS:build-prototype` when the prototype plan has no unresolved critical design ambiguity. Legacy alias: `/build-prototype`.

## Required inputs

Prototype scope, ordered tasks, success criteria, repository, and run target.

## Optional inputs

Placeholder assets, engine tools, existing tests, and reference implementations.

## Files to read

Project, issues, critical path, decisions, prototype artifacts, assumption log, relevant source, tests, and engine manifests.

## State changes

Set phase to `prototype-build`; update build status, assumptions, issues, evidence, critical path, and last verified date from actual results.

## Execution procedure

1. Confirm the active critical-path item and preserve explicit exclusions.
2. Run `studio doctor` to establish what this machine can actually execute. Treat `UNKNOWN` as unknown, not as available.
3. Implement the smallest working increment with placeholders where adequate.
4. Record changed files, completed tasks, assumptions, shortcuts, and defects.
5. Run `studio test`, then `studio verify --level smoke`. Where a command reports `unknown` (no adapter, no test framework, engine missing), record that as unknown rather than substituting a manual impression for it.
6. Inspect the resulting records with `studio execution show RUN-####` and `studio artifact list`.
7. Create evidence explicitly with `studio evidence add --run RUN-#### --artifact ART-####`, using the proposal `studio verify` printed as a starting point and keeping its limitations. Never accept a proposal that claims more than was observed.
8. Open or update issues for observed defects, then regenerate reports and recommend build review.

## User decision points

Ask only for required scope/criteria/fantasy/platform changes or expensive-to-reverse technical choices.

## Outputs

Playable artifact or concrete blocker; changed-file and shortcut records; verification evidence; run instructions; Direction Summary.

## Validation

Run `studio test`, `studio verify --level smoke`, `studio validate`, `studio report`, and `studio status`.

Where execution tooling is unavailable, fall back to running the engine manually and record the result as `user-reported` evidence naming what was and was not observed. A manual fallback is still evidence; it is simply weaker provenance than a RUN record, and must not be recorded as `observed` runtime evidence.

## Completion criteria

The prototype launches and can be tested, or a specific blocker with recommended resolution is canonical.

## Next recommended workflows

`GS:review-build` after delivery; `GS:critical-path` when blocked.

## Failure and blocker behavior

Preserve failures verbatim where useful, add an issue with evidence, and mark blocked dependencies.

Never call compilation alone a playable build. A `passed` RUN record means a process exited zero; `studio verify --level smoke` establishes only that the engine started and did not exit early. Neither establishes that the game is playable, and neither may be recorded as gameplay evidence.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
