# Iterate

## Purpose

Implement the highest-value change and gather evidence against updated prototype criteria.

## When to use

Use for `/iterate` after issue mapping and critical-path selection.

## Required inputs

First actionable critical-path item, related evidence, and current criteria.

## Optional inputs

Approved decision, alternative actions, timebox, and playtest setup.

## Files to read

Project, issues, decisions, evidence, critical path, milestone, relevant review, source, and tests.

## State changes

Set phase to `iterate`; update issue status/resolution, evidence, assumptions, build status, and critical path. Change success criteria only after approval.

## Execution procedure

1. State the issue and evidence gap being addressed.
2. Confirm the smallest change and expected observable result. Inspect any governing choice with `studio decision list`/`show`.
3. Implement within scope and record shortcuts/assumptions.
4. Run focused tests and the most direct available experience verification.
5. Record the result with `studio evidence add`, or use `studio evidence update` when retracting or superseding an earlier claim. State limitations explicitly.
6. Use `studio issue update` for status, resolution, owner, and evidence references. Use `studio dependency add|update|deactivate` for concrete ordering changes, `studio decision update` for decision evidence/consequences, and `studio decision resolve` only after the owner chooses.
7. Compare new evidence with each relevant criterion completion condition. Record support only with `studio criterion evaluate`; include limitations for partial support and never infer verification from issue closure.
8. Run `studio path check` after material changes; if stale, preview and run `studio path calculate`, then use `studio path show`.
9. Regenerate reports through transactional updates.
10. State the exact next `CP-` item and recommend further iteration or milestone review.

## User decision points

Ask before alternative selection changes the core experience, scope, platform, or criteria; explain recommendation and trade-off.

## Outputs

Working iteration, verification result, updated issue map/path, and Direction Summary.

## Validation

Run project checks, `studio validate`, `studio report`, and `studio status`.

## Completion criteria

The target issue is resolved, deliberately accepted, or remains blocked with better evidence and a concrete next action.

## Next recommended workflows

`/playtest-review`, `/critical-path`, or `/milestone-review` depending on evidence.

## Failure and blocker behavior

Revert no user work. Record failures and keep criteria/result distinctions honest.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
