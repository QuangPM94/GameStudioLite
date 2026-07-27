# Evidence Management

Phase B3 records claims and their epistemic basis through `EvidenceService`. Canonical evidence lives only in `.studio/state/evidence.json`; generated Markdown is never state input.

## Commands

```bash
studio evidence add \
  --title "Player stopped in corridor" \
  --claim "The player could not identify the target apartment." \
  --classification user-reported \
  --source-type human-playtest \
  --description "Tester remained in the corridor for forty seconds." \
  --issue ISS-0001 \
  --limitation "Only one tester participated." \
  --yes
studio evidence list
studio evidence show EVD-0001
studio evidence update EVD-0001 --status retracted
```

Every command accepts `--root PATH` and `--json`. Write commands accept `--dry-run`. Guided and strict projects confirm creation; non-interactive creation uses `--yes`.

## Classification

- `observed`: directly supported by accessible execution, runtime, media, telemetry, logs, or reproducible output.
- `user-reported`: reported by a person but not independently verified by PGS.
- `inferred`: reasoned from source, specifications, screenshots, or design analysis without observing the claimed player experience.
- `unknown`: currently lacks enough support.

Classification is not source type. Reports preserve this distinction and do not phrase user reports or inference as direct observation.

## Source types

Supported types are `runtime`, `human-playtest`, `screenshot`, `video`, `telemetry`, `test-output`, `build-log`, `source-review`, `spec-review`, `user-note`, `external-report`, and `other`.

Screenshot, video, telemetry, test-output, build-log, external-report, and other evidence require a source reference. Runtime, human-playtest, user-note, source-review, and spec-review may omit it when a useful description is supplied.

## Confidence

Confidence describes support strength within the chosen classification:

- `low`: material gaps or indirect support.
- `medium`: useful support with ordinary limitations.
- `high`: unusually strong, repeatable, or corroborated support.

Defaults are medium for observed and user-reported evidence, and low for inferred and unknown evidence. Observed evidence is never automatically high. Explicit classification changes do not silently change confidence.

## Lifecycle and IDs

Evidence is `active`, `superseded`, or `retracted`. Only active records count as current support; historical records remain visible with `--all` and are never deleted.

IDs use `EVD-0001`, allocated after the greatest numeric historical ID. Superseded and retracted records still advance allocation, and dry runs do not consume IDs.

Retracted evidence may be reactivated. Superseded evidence cannot be active while another record still supersedes it.

## Issue links

Adding `--issue` or `--add-issue` writes both directions in one transaction:

```text
evidence.related_issues → ISS-0001
issue.evidence_references → EVD-0001
```

Unlinking removes both directions. Linking evidence does not alter issue severity, status, ownership, or critical-path membership. Issue evidence classification is derived from the strongest active linked record.

## Supersession

```bash
studio evidence update EVD-0002 --supersedes EVD-0001
```

This keeps both records, points the replacement at the older record, and marks the older record superseded. Issue links remain historical. Supersession chains must be acyclic. In B3, an established `supersedes` target is immutable; replacing or clearing that relationship is deferred to a later graph-aware workflow.

## Dry runs and JSON

Dry runs allocate the proposed ID, apply relationship changes in memory, validate all schemas and relationships, and render all reports without writing tracked paths.

JSON output uses the B2 envelope with stable keys, changed/unchanged paths, changed fields, data, validation, reports, warnings, and structured errors. Exit codes remain `0` success, `1` transaction failure, `2` invalid input, and `3` missing requested record.

## Honest player-review language

When no active observed runtime or observed human-playtest evidence exists, player-facing report output includes exactly:

> This is a simulated player-experience review based on available artifacts.
> It is not a substitute for an observed human playtest.

An inferred source review is never described as a playtest. A human report remains user-reported unless direct observation supports a different classification.

## Schema 2.0 migration

The B3 evidence schema replaces the Phase A record shape. Empty registries need only set `schema_version` to `2.0`. Existing records require an explicit maintenance migration:

- `type` → lowercase `classification`, converting `_` to `-` (for example, `USER_REPORTED` → `user-reported`)
- `description` → retain as `description` and derive a concise `title` and `claim`
- add `source_type` based on the actual artifact; do not guess observed runtime
- `related_issue` → `related_issues` array and add the reverse issue reference
- `date` → `captured_at` ISO 8601 timestamp
- add `created_at`, `updated_at`, `status: active`, and `supersedes: null`

Migration must preserve the original source and limitations. Run `studio validate` and `studio report` afterward.

## Known limitations

B3 does not collect telemetry, inspect media, execute engines, calculate critical paths, mutate milestone decisions, or resolve conflicts between competing evidence automatically. Supersession is a small acyclic chain model, not a general evidence graph.

Decision records may reference evidence as recommendation support. The decision owns that one-way relationship; evidence state is not changed. Only active evidence counts toward the derived decision support level, and removing evidence never rewrites a recommendation automatically.
