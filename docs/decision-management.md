# Decision Management

Phase B4 records meaningful project forks through `DecisionService`. Canonical decisions live only in `.studio/state/decisions.json`; reports derive issue and evidence traceability without parsing or duplicating decision state.

## When to create a decision

Create a decision when user input, competing viable options, player experience, scope, milestone success, reversal cost, a blocker, or a meaningful evidence trade-off makes the choice consequential. Do not create records for naming, formatting, routine defaults, reversible implementation details, or work Codex is authorized to decide.

Before asking the user, search with `studio decision list` and update an existing record when possible. Present the recommendation, reason, evidence quality, and accepted trade-offs before requesting a choice.

## Commands

```bash
studio decision add \
  --question "How should the player locate the delivery room?" \
  --context "The corridor lacks sufficient guidance." \
  --option 'OPT-A|Explicit waypoint|Show a marker over the target door.' \
  --option 'OPT-B|Environmental guidance|Use signs and stronger room numbering.' \
  --recommended-option OPT-B \
  --recommendation-reason "It improves clarity while preserving immersion." \
  --trade-off "Less reliable than an explicit waypoint." \
  --status ready \
  --yes
studio decision list
studio decision show DEC-0001
studio decision update DEC-0001 --urgency blocking
studio decision resolve DEC-0001 --option OPT-B --reason "Preserves immersion." --yes
```

Every command accepts `--root PATH` and `--json`. Write commands accept `--dry-run`. Guided and strict projects require one confirmation for creation and resolution; non-interactive calls use `--yes`. Fast mode commits without that confirmation.

## Option format

The compact option specification is:

```text
ID|Label|Description|benefit1,benefit2|risk1,risk2|effort
```

Only ID, label, and description are required. Omit trailing optional fields or leave them empty:

```text
OPT-B|Environmental guidance|Use signs and lighting|||medium
```

PowerShell uses quotes around the complete value:

```powershell
--option "OPT-B|Environmental guidance|Use signs and lighting"
```

Bash should normally use single quotes:

```bash
--option 'OPT-B|Environmental guidance|Use signs and lighting'
```

Literal pipe characters are not escapable inside the compact B4 format; rephrase option text instead. Benefits and risks use comma separation. Option IDs remain stable when labels change.

## Lifecycle

- `open`: needs context, evidence, or refinement.
- `ready`: sufficiently prepared for the owner.
- `blocked`: cannot be resolved yet.
- `resolved`: a final choice is active.
- `deferred`: intentionally postponed but still relevant.
- `rejected`: the question is no longer worth pursuing.
- `superseded`: a replacement owns the active fork.

Supported transitions are:

```text
open → ready, blocked, deferred, rejected
ready → open, blocked, deferred, rejected
blocked → open, ready, deferred, rejected
deferred → open, ready, rejected
resolved → open
rejected → open
```

Resolution is performed only with `studio decision resolve`, not a status update. Decisions are historical records and are never deleted.

## Recommendation and evidence support

Every decision stores a recommended option and reason. Retracted and superseded evidence remains traceable but does not count as current support.

- `strong`: at least one active observed record.
- `moderate`: at least two active records without observed evidence.
- `weak`: one active user-reported, inferred, or unknown record.
- `unsupported`: no active linked evidence.
- `conflicted`: active linked evidence explicitly declares a conflict through a limitation such as `Conflicts with EVD-0001`.

This is a transparent classification rule, not numerical scoring. Evidence does not rewrite the recommendation automatically. Inferred support is never described as experimentally verified.

## Issue and evidence links

`affected_issues` and `supporting_evidence` are owned by the decision record. Issue reports derive related decisions by scanning decision state; issue and evidence state are not mutated merely for symmetry. Referenced records must exist, and duplicates are normalized.

Resolving a decision does not resolve an issue. Removing evidence does not change the recommendation. Reports warn when a recommendation has no active support.

## Resolution, overrides, and reopening

Resolution requires exactly one option or one custom decision plus a reason:

```bash
studio decision resolve DEC-0001 \
  --option OPT-B \
  --reason "It improves clarity without adding HUD guidance." \
  --consequence "Revise room-number contrast." \
  --follow-up "Run another playtest." \
  --revisit-condition "Two testers still cannot find the room." \
  --yes
```

PGS stores an option-label snapshot, reason, consequences, follow-ups, revisit condition, resolution time, and whether the recommendation was followed. Custom decisions have no fabricated option ID and are recorded as recommendation overrides.

Reopen with:

```bash
studio decision update DEC-0001 --status open
```

The active final fields are cleared while the structured resolution history remains. The decision keeps its ID and returns to pending reports.

## Supersession

```bash
studio decision update DEC-0002 --supersedes DEC-0001
```

This marks the older record superseded and keeps both histories and references. Self-supersession, cycles, missing targets, and multiple active replacements are rejected. An established supersession target is immutable in B4.

## Dry runs, JSON, and exit codes

Dry runs allocate the proposed ID, validate relationships, derive support, and render all reports without writing state or reports. The next real add receives the same ID. JSON uses the shared stable envelope.

- `0`: success, including empty lists and no-op updates
- `1`: transaction, validation, rendering, concurrency, or replacement failure
- `2`: invalid or incomplete input
- `3`: requested decision not found

## Schema 2.0 migration

Empty Phase A/B decision registries need only change `schema_version` to `2.0`. Existing 1.0 records require an explicit maintenance migration:

- map `pending` to `open` or `ready`, and `decided` to `resolved`
- map `soon` to `high` or `medium`, and `later` to `low`
- add milestone, issue/evidence references, required-by date, timestamps, supersession, follow-ups, and resolution history
- expand options with empty benefits/risks and nullable effort
- split the old final decision into `final_option_id` and a human-readable snapshot
- preserve reasons, trade-offs, consequences, and revisit conditions

Do not guess evidence links or historical resolution times. Run `studio validate` and `studio report` afterward.

## Known limitations

B4 does not score options, infer which option an evidence claim supports, automate workflow state, resolve issues, or build a general decision graph. Phase C1 can place blocking/high decisions and explicitly required verification on the milestone path, but never chooses for the owner. Explicit evidence conflict markers are required for the `conflicted` support level.
