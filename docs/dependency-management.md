# Dependency Management

Phase C2 stores execution-order relationships in
`.studio/state/dependencies.json`. Use the `studio dependency` commands rather
than editing that file.

## Direction and endpoints

Every edge means **dependent requires prerequisite**. For example,
`ISS-0003 requires DEC-0001` means the decision must be satisfied before the
issue is actionable. Supported endpoints are issues (`ISS-`), decisions
(`DEC-`), milestone criteria (`MC-`), and existing manual path actions
(`MANUAL:slug`). Evidence is supporting material and cannot be a dependency
endpoint.

Dependencies are for concrete ordering. A vague semantic relationship such as
“related to” belongs in the record links, not in this registry.

## Lifecycle, scope, and satisfaction

Dependencies are `active` or `inactive`; history is never deleted and `DEP-`
IDs are never reused. Re-adding an identical inactive edge reactivates its
historical record when safe. Project-scoped edges apply across milestones.
Current-milestone edges retain the milestone context in which they were
authored.

Satisfaction is derived rather than stored: a resolved/accepted issue, resolved
decision, explicitly verified active criterion, or completed manual action can
satisfy a prerequisite. Inactive edges do not affect path ordering.

The runtime validator rejects missing endpoints, duplicate active edges,
self-dependencies, inconsistent legacy duplicates, and exact cycles across
explicit and deterministic compatibility edges.

## Commands

PowerShell:

```powershell
studio dependency add `
  --prerequisite DEC-0001 `
  --dependent ISS-0003 `
  --reason "Implementation requires the selected guidance option." `
  --dry-run
studio dependency update DEP-0001 --reason "Clarified ordering reason." --yes
studio dependency deactivate DEP-0001 --reason "The implementation no longer depends on the decision." --yes
```

Bash:

```bash
studio dependency add \
  --prerequisite DEC-0001 \
  --dependent ISS-0003 \
  --reason "Implementation requires the selected guidance option." \
  --yes
studio dependency list --active
studio dependency show DEP-0001
```

All writes support `--dry-run` and `--json`. Dry runs allocate the proposed ID,
validate the combined graph, render reports in isolation, and write nothing.
Material changes mark the current path stale but do not recalculate it or
change workflow phase. Run `studio path check`, then `studio path calculate`
when required.

## Compatibility and limitations

Legacy issue dependency arrays and the deterministic “decision blocks
implementation issue” rule remain readable as derived compatibility edges.
New ordering relationships should use the dedicated registry; representing the
same active edge in both forms is invalid. Phase C2 supports only the hard
`requires` relationship, not soft/informational edges, evidence endpoints,
automatic workflow execution, or milestone progression.
