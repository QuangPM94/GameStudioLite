# Dependency-Aware Milestone Critical Path

Phase C1 calculates the smallest useful ordered set of work currently gating the active milestone. It is a dependency-aware priority path, not classical Critical Path Method: PGS has no reliable duration estimates and therefore does not claim an exact date, guaranteed shortest schedule, or mathematically proven schedule criticality.

## Commands

```bash
studio path calculate --dry-run
studio path calculate --include ISS-0004 --exclude ISS-0008 \
  --exclude-reason "External dependency is unavailable." --yes
studio path show
studio path show --all
studio path explain CP-0001
studio path check
```

All commands accept `--root PATH` and `--json`. `calculate` also accepts `--milestone TEXT`, repeated `--include` and `--exclude`, `--exclude-reason`, `--max-items 3..10`, `--dry-run`, and `--yes`. Guided and strict non-interactive writes require `--yes`; fast mode writes without that additional confirmation.

`show`, `explain`, and `check` are read-only. `check` reports a missing path successfully and recommends `studio path calculate`.

## Candidate types

- `issue`: active blocker, critical issue, milestone-impacting major issue, blocking prerequisite, or explicitly included issue.
- `decision`: blocking decision, or a high-urgency current-milestone decision.
- `verification`: a concrete claim/evidence action required by a criterion, explicitly evidence-blocked decision, or explicitly reproduction-dependent user-reported critical issue.
- `milestone-criterion`: a required criterion contradicted by current evidence and requiring a concrete corrective action.
- `manual-action`: explicitly authored path work with a title, reason, and completion condition. Manual work is preserved rather than silently deleted.

Resolved, accepted, wont-fix, and deferred issues are inactive path candidates,
but only resolved and accepted issues satisfy prerequisites. Resolved,
rejected, superseded, and deferred decisions are not active candidates, but
only resolved decisions satisfy prerequisites. Optional unsupported criteria
do not enter the path by default unless an explicit dependency requires them.

Verification candidates name the claim, satisfying evidence, and requiring source. The engine does not generate filler such as “test more” or “investigate.”

## Priority tiers

1. Hard milestone blockers: unavailable build/artifact, blocker issue, blocking decision, contradicted required criterion.
2. Critical experience failures: core-loop, comprehension, hypothesis, safety, or data-loss failures.
3. Required decisions and prerequisites: high-urgency choices and ancestors needed by Tier 1/2 work.
4. Verdict verification: unsupported required criteria and explicit reproduction/evidence gates.
5. Major milestone-impacting work: direct but non-blocking milestone work.

Minor, later, cosmetic, optional content, save systems, analytics, broad refactors, and production architecture stay off-path unless explicitly required by the milestone or included manually.

## Dependency ordering and selection

Phase C2 makes active records in `.studio/state/dependencies.json` authoritative hard ordering edges. Every edge means **dependent requires prerequisite** and records its `DEP-` origin in path state, explanations, and reports. Project-scoped edges always apply; current-milestone edges apply only in their authored milestone context. Deactivated edges do not order work.

Legacy issue dependency arrays and the deterministic issue/decision blocking rule remain compatibility-derived edges. Explicit and derived edges are merged without duplication; representing the same edge inconsistently is invalid. Criterion issue/decision links are semantic references and no longer imply order. Create a dependency when a relationship actually affects execution sequence. Verification-to-source edges remain deterministic generated rules. PGS never infers a reverse edge.

The service calculates dependency closure and then uses stable topological
ordering. Prerequisites appear before dependents even when the prerequisite has
a lower priority tier. Shared prerequisites appear once. Canonically satisfied
prerequisites leave the active path and unlock dependents. Active unsatisfied
prerequisites enter the closure when eligible. Terminal-unsatisfied
prerequisites never unlock dependents: calculation names the `DEP-` edge and
source status, then recommends updating or deactivating the relationship.
Missing references fail calculation and are never interpreted as completed.
Cycles fail with the exact source-key cycle and write nothing.

The normal maximum is seven and the minimum accepted configuration is three. Fewer than three legitimate candidates is valid and never padded. Independent lower-priority work is reduced when the maximum is reached. A single mandatory dependency closure, or explicit pinned work, may exceed the configured maximum; the state and output then carry an explicit warning rather than dropping prerequisites.

## Stable IDs and reconciliation

Path IDs use `CP-0001`. Allocation scans active and historical items, advances after the greatest ID, and never reuses an ID for a different `source_key`.

Canonical keys are independent of titles:

```text
issue:ISS-0001
decision:DEC-0002
milestone:MC-001
verification:DEC-0002:observed-support
manual:prototype-launch-check
```

Recalculation preserves the ID and `created_at` for a matching key. Reordering and title changes do not allocate new IDs. Resolved sources move to compact completed history; rejected, superseded, deferred, or no-longer-selected work moves to removed history. Reopened sources reuse their historical ID when selected again. No-op calculations preserve timestamps and bytes.

## Manual controls

`--include SOURCE-ID` persists the resolved canonical key in `pinned_sources`. `--exclude SOURCE-ID` persists it in `excluded_sources`; every exclusion requires `--exclude-reason`. A source cannot be both pinned and excluded.

An excluded prerequisite causes a clear calculation failure. The engine never silently overrides it. Missing or completed controls are removed during recalculation with warnings. `path show`, `path explain`, and the critical-path report expose active controls.

Legacy issue `--on-critical-path` and `--off-critical-path` operations remain compatibility controls: they pin/remove one issue item and mark the calculated path stale. `studio path calculate` remains the authority for ordering and full membership.

## Freshness

Calculation stores deterministic candidate, active dependency graph, criterion definition, criterion evaluation, criterion-evidence lifecycle, evidence, and manual-control fingerprints. `studio path check` compares them with current canonical state and reports:

- source issue or decision status changes;
- material evidence-support changes;
- milestone or criterion changes;
- active dependency additions, edits, deactivations, or reactivations;
- criterion definition, required/optional, verification-policy, support, retirement, or completion/verification changes;
- retracted or superseded evidence used by an explicit criterion evaluation;
- deleted, inactive, or superseded sources;
- new hard blockers;
- invalid manual controls.

`check` never writes. Material issue/decision lifecycle changes also archive invalid active items immediately so canonical relationships remain valid, then mark the path stale. Recalculate after material issue, decision, evidence, dependency, or milestone changes; trivial wording changes that do not affect gating need not trigger a workflow interruption.

## Recommended next action

The recommended item must have no active unmet dependency and must be `ready` or `in-progress`. Selection prefers the highest priority tier, then in-progress work, then stable path order. A blocked item is never recommended over its prerequisite. CLI output distinguishes user decisions, implementation, and verification through the item type and source.

## Dry runs and JSON

`studio path calculate --dry-run` performs candidate collection, dependency closure, cycle checks, proposed ID allocation, reconciliation, full schema/relationship validation, and isolated report rendering. It writes nothing: state, reports, manual controls, history, and ID allocation remain byte-identical. The next real calculation receives the same IDs.

JSON mode uses the shared stable envelope. JSON is the only stdout content, keys are sorted, output has a final newline, errors are structured, and identical read commands produce byte-identical output.

## Schema 3.0 migration

Critical-path state originally advanced from schema `1.0` to `2.0` in C1. Phase C2 advances it to `3.0`. Preserve all C1 identity/history fields, then:

- expand `CP-001` to `CP-0001` without changing identity;
- map issue/decision source fields to `source_id` and canonical `source_key`;
- map legacy types to `issue`, `decision`, `verification`, `milestone-criterion`, or `manual-action`;
- map `why_critical` to `reason`/`milestone_impact` and `exit_condition` to `completion_condition`;
- add priority, status, owner, evidence, manual/pinned, source-status, and timestamps;
- add `history`, controls, recommended-next, configured maximum, calculation snapshot, freshness, warnings, and milestone override metadata.
- add `dependency_origins` to every active and historical path item;
- replace the single criterion fingerprint with dependency-graph, criterion-definition, criterion-evaluation, and criterion-evidence-lifecycle fingerprints;
- remove the duplicated `milestone_success_criteria` copy and render criteria from milestone state.

Milestone state advanced to `3.0` in C2 and to `3.1` in C2.1.
Version 3.1 adds the required explicit `verification_policy` definition field;
the C1 criterion fingerprint includes it, so policy edits report “Milestone
criterion definitions changed.” `MC-001` keeps its identity/history and uses
`document-review`. Preserve existing `MC-` IDs and map `pass`, `partial`,
`fail`, and `unknown` to `verified`, `partially-supported`, `contradicted`, and
`unsupported`. Do not manufacture evaluation history for legacy projections.
Run `studio validate` and `studio report`; the path remains stale until
`studio path calculate`.

## Known limitations

Phase C2.1 still does not estimate durations, calculate dates, support soft
dependency types, use evidence as a dependency endpoint, infer arbitrary
semantic dependencies, merge multiple issues into one action, automatically
transition milestones/project phases, execute workflows, control an engine,
ingest media/telemetry, implement game code, or orchestrate agents.
Verification rules depend on explicit policies and canonical relationships,
never language-specific keyword detection.
