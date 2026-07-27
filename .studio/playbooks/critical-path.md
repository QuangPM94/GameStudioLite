# Critical Path

## Purpose

Select the smallest ordered set of work whose delay would delay the milestone.

## When to use

Use for `/critical-path` after planning, issue mapping, a blocker, or changed evidence.

## Required inputs

Current milestone, success criteria, open issues, pending decisions, and dependencies.

## Optional inputs

Effort estimates, build verification, and accepted risks.

## Files to read

Project, issues, decisions, evidence, milestone, and current critical path.

## State changes

Replace active path items with an ordered set of three-to-seven valid items unless fewer exist; update blocked state, exit conditions, and non-critical work.

## Execution procedure

1. Prioritize runnable-build blockers.
2. Then prioritize critical hypothesis-invalidating issues, blocking user decisions, required dependencies, major high-player-impact issues, and milestone verification. Inspect decisions with `studio decision list`/`show`, including evidence support and required-by dates.
3. Use `studio evidence list --issue ISSUE-ID` and `studio evidence show` to distinguish active support from superseded, retracted, inferred, or unknown claims.
4. Order by dependency and explain why delaying each delays the milestone.
5. Keep only active milestone work; use fewer than three when fewer valid items exist.
6. Exclude menu polish, saves, content, localization, analytics, asset replacement, broad refactors, optional accessibility, and production architecture unless directly required.
7. Inspect records with `studio issue list --critical-path` and `studio issue show`. Use `studio issue update ID --on-critical-path` or `--off-critical-path` for explicit membership changes; B3 still does not calculate or reorder the path automatically.
8. Use `studio decision update` for decision readiness or traceability changes; do not resolve choices without the owner. Update reports and recommend the first actionable item.

## User decision points

Ask when a pending user decision is the first unresolved dependency or prioritization changes milestone criteria/trade-offs.

## Outputs

Ordered critical path, blocker state, exit condition, deferred work, and Direction Summary.

## Validation

Check length, ordering, dependencies, references, and rationale; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

Every active item has a direct milestone-delay explanation and the first unblocked action is identifiable.

## Next recommended workflows

`/next-step`, or the playbook that executes the first item.

## Failure and blocker behavior

If dependencies form a cycle or are unknown, record a verification/decision item rather than inventing an order.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
