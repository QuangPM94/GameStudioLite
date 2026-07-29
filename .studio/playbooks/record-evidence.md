# Record Evidence

## Purpose

Record a claim and its source using the evidence model, with an honest classification of how it is known.

## When to use

Use for `GS:record-evidence` whenever a claim about the game, build, or player experience needs to be captured with its source and confidence, separate from recording a problem. Legacy alias: `/record-evidence`.

## Required inputs

The claim, and how it came to be known (directly observed, reported by a user, inferred, or unknown).

## Optional inputs

Confidence, limitations, related issues, source type, and captured-at time.

## Files to read

`AGENTS.md`, `.studio/state/evidence.json` (via `studio evidence list`/`show`), and `.studio/state/issues.json` when linking related issues.

## State changes

Create or update exactly one evidence record with `studio evidence add` or `studio evidence update`. Never edit `.studio/state/evidence.json` directly, and never use evidence writes to mark a milestone criterion verified.

## Execution procedure

1. Read `AGENTS.md` and the current evidence and issue state.
2. Search `studio evidence list` for a duplicate or superseded record covering the same claim; use `--supersedes` on `studio evidence update` when a new record replaces an older one.
3. Classify correctly: a statement from the user about something the agent did not directly witness is `user-reported`, not `observed`. Direct access to a runtime, build, screenshot, video, telemetry, or test output is `observed`. A conclusion drawn from source code or specifications is `inferred`. Anything without support is `unknown`.
4. Record confidence and explicit limitations (for example sample size, incomplete recording, or single-tester scope).
5. Link related issues with `--issue` when the evidence bears on an existing problem; issue/evidence links must remain bidirectional.
6. Create the record with `studio evidence add` or refine it with `studio evidence update`.
7. Capture the resulting `EVD-` identifier.
8. Run `studio validate`.
9. Run `studio path check`; do not recalculate unless required.
10. Do not treat the existence of this evidence as verifying any milestone criterion; that requires an explicit `GS:milestone-criteria` evaluation.
11. Return the Direction Summary.

## User decision points

Ask when the classification is ambiguous (for example, unclear whether a report was directly witnessed) rather than guessing `observed`.

## Outputs

The created or updated `EVD-` identifier and its classification, confidence, and limitations.

## Validation

Run `studio validate` and `studio path check` after every write.

## Completion criteria

Exactly one evidence record accurately reflects the claim, its true classification, and its limitations, with no silent criterion verification.

## Next recommended workflows

`GS:milestone-criteria` when the evidence addresses a specific criterion's completion condition; `GS:report-issue` when the evidence reveals a new problem; otherwise `GS:next-step`.

## Failure and blocker behavior

Never invent evidence. If the source of a claim is unclear, classify it `unknown` and ask rather than defaulting to a stronger classification.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
