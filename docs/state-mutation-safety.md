# State Mutation Safety

Phase B1 introduced the shared mutation path. Phases B2 through B4 and Phases C1/C2 route issue, evidence, decision, dependency, criterion, and critical-path writes through that path, including coordinated updates across canonical state and generated reports.

Project bootstrap precedes normal state mutation. It uses a separate
multi-file safe-write protocol because the target may not contain any PGS state
yet.

## Bootstrap stages

1. Load packaged scaffold resources in deterministic path order.
2. Classify every managed file as create, preserve, update, or conflict.
3. Stop before target writes when a managed-file conflict exists.
4. Build the proposed lightweight project in a temporary sibling tree.
5. Preserve existing protected state/reports in that tree and apply optional
   identity initialization transactionally.
6. Validate the complete staged project and generated report freshness.
7. Recheck target hashes to detect concurrent changes.
8. Write changed files through flushed sibling temporary files and
   `os.replace`.
9. On replacement failure, remove new managed files, restore replaced managed
   files from captured bytes, clean temporary paths, and leave unrelated files
   untouched.

Bootstrap rollback is best-effort local filesystem recovery, not database ACID.
A process crash, storage failure, or rollback failure can still require version
control or backup recovery. Ordinary `--force` never replaces existing
`.studio/state/` or `.studio/reports/` files.

## Commit stages

1. Discover and load every canonical JSON document.
2. Hash the exact source bytes and deep-copy state into an isolated working representation.
3. Apply mutations only to the working copy.
4. Validate all seven schemas, the combined dependency graph, criterion lifecycle/evaluation truth, and other cross-state relationships.
5. Render all five reports in memory and confirm the complete report set is producible.
6. Recheck canonical hashes.
7. Serialize changed JSON deterministically as UTF-8 with sorted keys, two-space indentation, and a final newline.
8. Write byte-different state and report outputs to flushed, closed temporary files beside their targets.
9. Recheck canonical hashes immediately before replacement.
10. Replace targets one at a time with `os.replace`.

If validation, rendering, staging, or the concurrent-modification check fails, tracked state and reports are not replaced. If a replacement fails, the transaction restores outputs already replaced from their original bytes and removes temporary files. The error identifies the failed stage.

On Windows, a scanner or indexer can hold a just-written file for a few milliseconds. PGS retries only `PermissionError` replacement failures five times with a 10 ms interval before entering the normal rollback path. Other replacement errors are never retried.

## Honest boundary

Each individual replacement is atomic on a compatible local filesystem, but the complete state-plus-report update spans multiple files. PGS therefore does not advertise database-style ACID guarantees. A process crash, power loss, filesystem failure, rollback failure, or non-cooperating write inside the narrow replacement window can leave a mixed revision. Version control remains the recovery boundary.

Concurrent protection is optimistic: hashes detect canonical files changed from the revision loaded by the transaction. The transaction aborts with the affected path and asks the caller to reload and retry. It does not lock external editors.

## Dry runs

Dry runs perform input normalization, loading, copying, validation, relationship checks, report rendering, deterministic comparison, and change reporting. They do not create target-path outputs or replace canonical state and reports.

`studio bootstrap --dry-run` additionally builds and validates the proposed
project in an isolated temporary sibling tree. Optional identity values run
through initialization and report rendering there; the target directory remains
byte-identical.

For issue creation, a dry run proposes an ID from the current historical maximum but does not consume it. A subsequent real add against the same canonical revision receives the same ID. Issue updates that normalize to the existing value are successful no-ops: they do not change `updated_at` or rewrite reports.

Evidence dry runs provide the same guarantee, including proposed ID allocation and bidirectional issue links. Retraction, reactivation, linking, and supersession are validated and rendered before any target is replaced.

Decision dry runs allocate a proposed historical ID and exercise option, reference, lifecycle, resolution-history, support-quality, and supersession validation without consuming the ID or writing outputs.

Critical-path dry runs collect candidates, close dependencies, detect cycles, allocate proposed `CP-` IDs, reconcile active/history state, validate manual controls, and render every report. They do not persist controls or history and do not consume IDs. A real calculation against the same revision receives the same IDs.

Dependency dry runs allocate a proposed `DEP-` ID, validate endpoints and the combined explicit/derived graph, calculate path-freshness impact, and render without changing the registry or path. Criterion dry runs similarly allocate proposed `MC-` IDs or evaluation entries, validate evidence/lifecycle rules and history, calculate freshness impact, and preserve every canonical/report byte. The next real creation against the same revision receives the same ID.

## Schema compatibility

B1 did not change the Phase A schemas. B2 extends the issue status enum while retaining compatibility. B3 advances evidence state to schema `2.0`; legacy evidence records require the field migration documented in `docs/evidence-management.md`. B4 advances decision state to schema `2.0`; its migration is documented in `docs/decision-management.md`. C1 introduced critical-path/milestone schema `2.0`. C2 adds dependency schema `1.0` and advances critical-path/milestone state to `3.0`, documented in `docs/dependency-management.md`, `docs/milestone-criteria-management.md`, and `docs/critical-path-engine.md`. PGS retains the established reference namespaces and fixed-width historical IDs.
