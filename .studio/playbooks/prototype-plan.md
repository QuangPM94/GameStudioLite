# Prototype Plan

## Purpose

Define the smallest playable loop that can answer the prototype question.

## When to use

Use for `/prototype-plan` after a falsifiable hypothesis exists.

## Required inputs

Approved prototype hypothesis and current project/engine constraints.

## Optional inputs

Timebox, reference artifacts, available assets, and developer skill constraints.

## Files to read

Project and decision state; game brief; `.studio/templates/prototype-scope.md`; `.studio/templates/prototype-success-criteria.md`; relevant source/manifests.

## State changes

Set phase to `prototype-plan`; update milestone, success criteria, assumptions, decisions, and a three-to-seven-item critical path when enough valid items exist.

## Execution procedure

1. State one prototype question.
2. Define the smallest playable loop, interactions, scenes/states, and placeholder strategy.
3. Define observable success and failure criteria and a realistic timebox.
4. List explicit exclusions, including production architecture and unrelated polish.
5. Resolve critical design ambiguity or inspect/create it through `studio decision list`, `show`, `add`, and `update`; attach relevant issues/evidence and present the recommendation before asking.
6. Order implementation tasks by runnable-build blockers, dependencies, hypothesis risk, and verification.
7. Use `studio decision resolve` after an approved choice, then generate scope and criteria artifacts, update state, and regenerate reports.

## User decision points

Ask when the plan changes core mechanics/fantasy/platform, materially exceeds the expected timebox, or requires changed success criteria.

## Outputs

Prototype question, scope, criteria, timebox, exclusions, ordered tasks, and Direction Summary.

## Validation

Confirm each task supports launch or a success criterion; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

The prototype can be implemented without unresolved critical design ambiguity.

## Next recommended workflows

`/build-prototype` when ready; `/clarify` for unresolved core design.

## Failure and blocker behavior

Record critical ambiguity as a pending decision. Do not pad the plan with non-critical work.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
