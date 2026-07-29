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
2. Implement the smallest working increment with placeholders where adequate.
3. Record changed files, completed tasks, assumptions, shortcuts, defects, and run instructions.
4. Run focused tests, framework validation, and the most direct available launch/smoke check.
5. Register observed command/runtime evidence and name unverified behavior.
6. Regenerate reports and recommend build review.

## User decision points

Ask only for required scope/criteria/fantasy/platform changes or expensive-to-reverse technical choices.

## Outputs

Playable artifact or concrete blocker; changed-file and shortcut records; verification evidence; run instructions; Direction Summary.

## Validation

Run relevant build/tests, `studio validate`, `studio report`, and `studio status`.

## Completion criteria

The prototype launches and can be tested, or a specific blocker with recommended resolution is canonical.

## Next recommended workflows

`GS:review-build` after delivery; `GS:critical-path` when blocked.

## Failure and blocker behavior

Preserve failures verbatim where useful, add an issue with evidence, mark blocked dependencies, and never call compilation alone a playable build.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
