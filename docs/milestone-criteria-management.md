# Milestone Criteria Management

Phase C2 makes milestone success criteria transactional and explicitly
evaluated. Criteria remain in `.studio/state/milestone.json`; use
`studio criterion` commands instead of direct editing.

## Model and lifecycle

Each stable `MC-` record owns its milestone, description, required/optional
flag, completion condition, verification method, related records, current
support, evaluation freshness, timestamps, and append-only evaluation history.
Lifecycle (`active` or `retired`) is separate from support:

- `unsupported`
- `partially-supported`
- `verified`
- `contradicted`

Retirement preserves support and evaluation history, excludes the criterion
from milestone-gating calculation, and never renumbers later criteria.
Reactivation is intentionally deferred beyond Phase C2.

## Explicit evaluation

Evidence presence never silently verifies a criterion. Before recording a
result, inspect the completion condition and active evidence, distinguish
`OBSERVED`, `USER_REPORTED`, `INFERRED`, and `UNKNOWN`, then use
`studio criterion evaluate`.

`verified` requires active evidence and normally active observed evidence.
Player-behavior claims always require observation; inferred evidence alone
cannot verify them. A criterion may document a non-runtime review method such
as document or source review. `partially-supported` requires active evidence
and at least one limitation. `contradicted` requires active conflicting
evidence. `unsupported` may have no evidence.

Every non-no-op evaluation snapshots evidence IDs, classifications and
lifecycle statuses along with issue/decision references, limitations, reason,
and time. Later retraction, supersession, or classification changes make that
evaluation and the critical path stale without rewriting history.

## Commands

PowerShell:

```powershell
studio criterion add `
  --description "A new player completes one delivery loop unaided." `
  --required `
  --completion-condition "Two of three observed testers complete the loop." `
  --verification-method "Observed human playtest." `
  --dry-run

studio criterion evaluate MC-002 `
  --support partially-supported `
  --evidence EVD-0004 `
  --reason "One observed tester completed the loop." `
  --limitation "Two additional observations are required." `
  --yes
```

Bash:

```bash
studio criterion list
studio criterion show MC-002
studio criterion update MC-002 --optional --yes
studio criterion retire MC-002 --reason "The milestone requirement changed." --yes
```

All writes support deterministic JSON envelopes and isolated dry runs.
Adding evidence through `criterion update` links it but does not evaluate the
criterion. Material definition, support, or lifecycle changes mark the path
stale and recommend `studio path check` or `studio path calculate`; they never
advance the milestone or project phase.

## Migration and limitations

Milestone schema v3 migrates C1 `criteria_results` records in place, preserving
existing `MC-` IDs. The old duplicated `success_criteria` list and path copy are
removed; each criterion description is now canonical once. Old
`pass/partial/fail/unknown` projections migrate to
`verified/partially-supported/contradicted/unsupported`.

Phase C2 does not automatically infer support, progress milestones, change
workflow phase, reactivate retired criteria, or execute verification work.
