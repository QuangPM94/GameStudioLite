# State Mutation Safety

Phase B1 introduced the shared mutation path. Phases B2 and B3 route issue and evidence writes through that path, including coordinated updates across issue, evidence, critical-path, and generated-report files.

## Commit stages

1. Discover and load every canonical JSON document.
2. Hash the exact source bytes and deep-copy state into an isolated working representation.
3. Apply mutations only to the working copy.
4. Validate all six schemas and cross-state relationships.
5. Render all five reports in memory and confirm the complete report set is producible.
6. Recheck canonical hashes.
7. Serialize changed JSON deterministically as UTF-8 with sorted keys, two-space indentation, and a final newline.
8. Write byte-different state and report outputs to flushed, closed temporary files beside their targets.
9. Recheck canonical hashes immediately before replacement.
10. Replace targets one at a time with `os.replace`.

If validation, rendering, staging, or the concurrent-modification check fails, tracked state and reports are not replaced. If a replacement fails, the transaction restores outputs already replaced from their original bytes and removes temporary files. The error identifies the failed stage.

## Honest boundary

Each individual replacement is atomic on a compatible local filesystem, but the complete state-plus-report update spans multiple files. PGS therefore does not advertise database-style ACID guarantees. A process crash, power loss, filesystem failure, rollback failure, or non-cooperating write inside the narrow replacement window can leave a mixed revision. Version control remains the recovery boundary.

Concurrent protection is optimistic: hashes detect canonical files changed from the revision loaded by the transaction. The transaction aborts with the affected path and asks the caller to reload and retry. It does not lock external editors.

## Dry runs

Dry runs perform input normalization, loading, copying, validation, relationship checks, report rendering, deterministic comparison, and change reporting. They do not create target-path outputs or replace canonical state and reports.

For issue creation, a dry run proposes an ID from the current historical maximum but does not consume it. A subsequent real add against the same canonical revision receives the same ID. Issue updates that normalize to the existing value are successful no-ops: they do not change `updated_at` or rewrite reports.

Evidence dry runs provide the same guarantee, including proposed ID allocation and bidirectional issue links. Retraction, reactivation, linking, and supersession are validated and rendered before any target is replaced.

## Schema compatibility

B1 did not change the Phase A schemas. B2 extends the issue status enum while retaining compatibility. B3 advances evidence state to schema `2.0`; legacy evidence records require the field migration documented in `docs/evidence-management.md`. PGS retains the Phase A-compatible `ISS-` and `EVD-` reference namespaces and allocates fixed-width IDs.
