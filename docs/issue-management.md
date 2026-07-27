# Issue Management

Phase B2 records and changes issues through a domain service, with CLI presentation kept separate. Canonical issue state lives only in `.studio/state/issues.json`; Markdown reports are derived output.

## Commands

```bash
studio issue add --title "Prototype does not launch" --severity blocker \
  --milestone-impact "No runnable build exists." --yes
studio issue list
studio issue show ISS-0001
studio issue update ISS-0001 --status in-progress --owner developer
studio issue update ISS-0001 --status resolved --resolution "Fixed startup scene."
```

All commands accept `--root PATH`. Every issue command accepts `--json`; write commands also accept `--dry-run`.

## Creation and defaults

Creation requires a non-empty title, a severity, and at least one non-empty description, player impact, or milestone impact. Optional values default conservatively: `other` category, `open` status, `UNKNOWN` evidence, `unknown` effort, and `unassigned` owner. The discovery phase comes from project state. A missing recommended action becomes a bounded investigation action.

In an interactive terminal, missing essential values are prompted. After the proposal is shown, guided and strict modes ask for confirmation. In non-interactive guided or strict use, pass `--yes`; fast mode commits without this confirmation.

## Severity

- `blocker`: prevents a runnable build or all milestone progress.
- `critical`: invalidates the prototype hypothesis or intended experience.
- `major`: strong player or milestone impact but progress remains possible.
- `minor`: bounded quality or friction issue that does not threaten the milestone.
- `later`: deliberately outside the current milestone.

## Lifecycle

- `open`: discovered and actionable.
- `acknowledged`: triaged and accepted into consideration.
- `in-progress`: actively being addressed.
- `blocked`: cannot progress until a dependency or decision changes.
- `resolved`: addressed; a resolution explanation is required.
- `accepted`: risk deliberately accepted; a resolution explanation is required.
- `wont-fix`: deliberately not addressed; a resolution explanation is required.
- `deferred`: inactive legacy/planned-later state retained for schema compatibility.

Allowed transitions are:

- `open` or `acknowledged` to another active state, a terminal state, or `deferred`.
- `in-progress` to `open`, `blocked`, a terminal state, or `deferred`.
- `blocked` to `open`, `in-progress`, a terminal state, or `deferred`.
- `resolved`, `accepted`, `wont-fix`, or `deferred` to `open`.

A reopened issue keeps its historical resolution text. There is no generic validity bypass.

## Stable IDs and history

PGS retains the Phase A `ISS-` namespace so existing schemas and cross-state references stay compatible. New IDs use four digits (`ISS-0001`) and are allocated from the greatest numeric ID in all current historical records, including terminal issues. IDs never change when titles change.

Deletion is unsupported. Issues remain historical records, so IDs are not reused. If deletion is introduced in a later phase, allocation history will need a separate canonical counter or archive.

## Listing and showing

`studio issue list` shows active issues by default. `resolved`, `accepted`, `wont-fix`, and `deferred` are hidden unless `--all` is used. Filters include status, severity, category, owner, critical-path membership, and user-decision requirement.

Ordering is severity, critical-path membership, blocked status, creation time, then stable ID. `studio issue show` omits empty optional fields in human output while JSON output contains the full canonical record.

## Critical path

`.studio/state/critical-path.json` is the authoritative ordered path; issue `on_critical_path` is validation-enforced against active issue-backed items. Phase C1 calculates full membership and order with `studio path calculate`.

The legacy `--on-critical-path` flag remains an explicit compatibility inclusion: it creates/pins one issue item and marks the calculated path stale. `--off-critical-path` removes that item to compact history. Resolving, accepting, rejecting, or deferring an active source archives it transactionally and marks the path stale; the next calculation reconciles the complete path and can reuse the ID after reopening. Prefer `studio path calculate --include/--exclude` for direction work.

## Evidence references

`--add-evidence EVD-ID` attaches an existing evidence record bidirectionally; it never creates one. Missing evidence fails the transaction. Duplicate additions and removal of an absent reference are successful no-ops with warnings. The issue evidence classification reflects the strongest active linked canonical evidence type and becomes `UNKNOWN` when none remain active.

Evidence creation is outside B2 scope.

Phase A allowed free-form strings in the issue evidence-reference array. B2 runtime validation treats every entry as a canonical evidence ID. Projects that used free-form artifact paths there must first create canonical evidence records in a maintenance migration and replace those strings with their `EVD-` IDs.

## Dry runs and JSON

Dry runs allocate a proposed ID, validate schemas and relationships, render all reports, and report affected files without writing. The ID is not consumed.

JSON output uses a stable envelope:

```json
{
  "changed_files": [],
  "changed_fields": {},
  "data": {},
  "dry_run": false,
  "operation": "issue.list",
  "reports": {},
  "success": true,
  "validation": {},
  "unchanged_files": [],
  "warnings": []
}
```

Errors use the same envelope with an `error` object and no decorative output.

## Exit codes

- `0`: success, including empty lists and no-op updates.
- `1`: transaction, validation, rendering, staging, replacement, or concurrency failure.
- `2`: invalid or missing user input.
- `3`: requested issue not found.

## Related decisions

Decision state owns its `affected_issues` references. `studio report` derives related decision IDs and statuses under issues without adding a redundant decision list to `issues.json`. Resolving a decision never resolves an issue automatically.
