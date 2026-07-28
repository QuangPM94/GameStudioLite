# Critical Path

## Purpose

Calculate the smallest ordered set of work whose delay most directly delays the current milestone.

## When to use

Use for `/critical-path` after planning, issue mapping, a blocker, or a material issue, evidence, decision, dependency, or milestone change.

## Required inputs

Current project/milestone state, success criteria, issues, evidence, decisions, explicit dependencies, and manual path controls.

## Optional inputs

A milestone override, explicit include/exclude sources, an exclusion reason, and a custom maximum from three to ten.

## Files to read

`AGENTS.md`, `.studio/state/project.json`, `.studio/state/milestone.json`, `.studio/state/issues.json`, `.studio/state/evidence.json`, `.studio/state/decisions.json`, `.studio/state/dependencies.json`, and `.studio/state/critical-path.json`.

## State changes

Use `studio path calculate` to transactionally replace active path membership/order, reconcile stable IDs and history, persist manual controls, update freshness snapshots, synchronize issue path flags, and regenerate reports. Never edit `critical-path.json` or generated reports directly.

## Execution procedure

1. Run `studio dependency list` and `studio criterion list`; confirm any claimed hard order is explicit and every current required criterion has a concrete completion condition.
2. Run `studio path check`.
3. If the path is absent or stale, preview `studio path calculate --dry-run`; review combined-graph cycles, missing references, dependency origins, exclusion conflicts, and oversize warnings.
4. Use repeated `--include SOURCE-ID` or `--exclude SOURCE-ID --exclude-reason TEXT` only for explicit user direction. Do not use them to hide inconvenient blockers.
5. Commit with `studio path calculate` (and `--yes` in guided/strict non-interactive use).
6. Run `studio path show` and identify its exact recommended-next `CP-` item.
7. Use `studio path explain CP-ID` when the item’s rationale, criterion/evidence state, dependency origins, downstream work, or manual context needs review.
8. Treat the result as a dependency-aware milestone priority path, not a mathematically exact schedule.
9. Run validation and return the Direction Summary with exactly one next workflow.

## User decision points

Ask when a manual inclusion/exclusion, milestone override, or prioritization change alters milestone success criteria, core direction, or an expensive scope/schedule/quality trade-off. Present the recommendation and accepted trade-off.

## Outputs

Calculated active path, stable history, one recommended-next item, manual controls, non-critical work, freshness state, generated reports, and Direction Summary.

## Validation

Run `studio path check`, `studio validate`, `studio report`, and `studio status`. Confirm dependency order, source references, three-to-seven guidance, recommended-next actionability, and exact warnings.

## Completion criteria

The path is current, every active item has a direct milestone-delay explanation and completion condition, and one unblocked next item is named (or a concrete blocker explains why none is actionable).

## Next recommended workflows

`/next-step`, `/iterate`, `/build-prototype`, or the workflow that executes the exact recommended item.

## Failure and blocker behavior

Do not write a cyclic or missing-reference path. Report the exact dependency cycle or excluded prerequisite conflict. Use a smaller valid path when fewer than three items exist; never add filler.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
