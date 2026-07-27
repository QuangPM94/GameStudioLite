# Playtest Review

## Purpose

Evaluate the intended experience across relevant player profiles using available evidence.

## When to use

Use for `/playtest-review` with source/specification, screenshots, video, runtime, logs, telemetry, or human playtest notes.

## Required inputs

Prototype hypothesis, success criteria, and at least one review artifact.

## Optional inputs

Runtime access and evidence from all supported artifact types.

## Files to read

Project, evidence, issues, criteria, `.studio/templates/player-review.md`, and supplied artifacts.

## State changes

Set phase to `evaluate`; append evidence and issue candidates without overwriting conflicting observations.

## Execution procedure

1. Inventory evidence with `studio evidence list` and inspect relevant records with `studio evidence show`.
2. Select relevant profiles from first-time, genre fan, casual, explorer, optimization-focused, and skeptical.
3. For each, evaluate clarity, engagement, intended emotion/tension, pacing, feedback, friction, payoff, desire to continue, and stability.
4. Record separately what was directly observed, what the tester reported, what was inferred, and what remains unknown. Use `studio evidence add`/`update` and record tester count, build version, incomplete recording, and other limitations.
5. Name the strongest, weakest, confusing, and likely abandonment moments; main risk; most important improvement; and real-playtest questions. If evidence supports competing consequential directions, inspect or create a decision with `studio decision list`/`show`/`add`.
6. Include the simulated-review disclaimer when active observed runtime or observed human-playtest evidence is unavailable.
7. Inspect existing findings with `studio issue list`/`show`; record accepted findings with `studio issue add` and refine them with `studio issue update`. Link only existing evidence IDs.
8. Add the relevant issue/evidence links and recommendation with `studio decision update`; resolve only after the user chooses. Transactional writes regenerate reports.
9. Inspect each relevant criterion with `studio criterion show`. When evidence addresses its completion condition, record an explicit `studio criterion evaluate` result with evidence IDs and limitations; observation alone is not an automatic pass.
10. Run `studio path check` after material findings/evaluations; calculate if stale, summarize with `studio path show`, and name the exact next item.

## User decision points

Ask when evidence supports mutually exclusive experience directions or a recommended improvement changes the mechanic/fantasy/criteria.

## Outputs

Structured player review, prioritized findings, issue candidates, evidence gaps, and Direction Summary.

## Validation

Verify all findings have evidence labels and references/limitations; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Findings distinguish observation from inference and are sufficient to map issues or explicitly request missing evidence.

## Next recommended workflows

`/issue-map` when findings exist; `/review-build` when runtime access is the primary gap.

## Failure and blocker behavior

State the simulated-review disclaimer exactly when required. Never claim to have played inaccessible software.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
