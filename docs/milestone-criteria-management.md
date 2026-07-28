# Milestone Criteria Management

Phase C2 makes milestone success criteria transactional and explicitly
evaluated. Criteria remain in `.studio/state/milestone.json`; use
`studio criterion` commands instead of direct editing.

## Model and lifecycle

Each stable `MC-` record owns its milestone, description, required/optional
flag, completion condition, verification method, explicit verification policy,
related records, current support, evaluation freshness, timestamps, and
append-only evaluation history. Lifecycle (`active` or `retired`) is separate
from support:

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

Correctness never depends on English words in the description, completion
condition, or verification method. Every criterion declares one policy:

| Policy | Requirement for `verified` |
|---|---|
| `observed-player-behavior` | Active `observed` evidence from human playtest, video, or runtime |
| `observed-runtime` | Active `observed` runtime, video, telemetry, test output, build log, or screenshot |
| `automated-test` | Active `observed` test output or build log |
| `document-review` | Active spec review, user note, external report, or other document evidence, plus a reason naming the reviewed artifact |
| `source-review` | Active source-review evidence classified `observed` or `inferred` |
| `manual-approval` | Explicit reason plus active evidence or a decision reference; never automatic |
| `mixed` | Active evidence plus an explicit reason |

`mixed` does not replace `observed-player-behavior` for player outcomes.
Multilingual criteria, including Vietnamese and Japanese descriptions, behave
identically because the policy—not keyword detection—defines evidence quality.
`partially-supported` requires active evidence and at least one limitation.
`contradicted` requires active conflicting evidence. `unsupported` may have no
evidence.

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
  --verification-policy observed-player-behavior `
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
studio criterion update MC-002 --verification-policy mixed --yes
studio criterion retire MC-002 --reason "The milestone requirement changed." --yes
```

All writes support deterministic JSON envelopes and isolated dry runs.
Adding evidence through `criterion update` links it but does not evaluate the
criterion. Material definition, support, or lifecycle changes mark the path
stale and recommend `studio path check` or `studio path calculate`; they never
advance the milestone or project phase.

## Migration and limitations

Milestone schema v3.1 requires `verification_policy` while preserving existing
`MC-` IDs, timestamps, support, references, and evaluation history. `MC-001`
migrates to `document-review` because its profile/hypothesis condition is
verified by artifact review rather than player behavior. The old duplicated
`success_criteria` list and path copy remain removed; each criterion
description is canonical once. Old
`pass/partial/fail/unknown` projections migrate to
`verified/partially-supported/contradicted/unsupported`.

Changing a policy updates `updated_at`, makes an existing evaluation stale,
marks the critical path stale, preserves evaluation history, and recommends
`studio path calculate`. A no-op policy update remains byte-identical.

Phase C2 does not automatically infer support, progress milestones, change
workflow phase, reactivate retired criteria, or execute verification work.
