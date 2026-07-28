# Changelog

All notable changes follow Keep a Changelog conventions.

## [Unreleased]

### Added

- Cross-platform GitHub Actions validation for Ubuntu/Python 3.11 and 3.12 plus Windows/Python 3.11, including copied-repository CLI smoke coverage.
- C2.1 canonical typed dependency-satisfaction verdicts shared by dependency display, validation, and critical-path closure, including actionable terminal-unsatisfied diagnostics.
- Explicit criterion verification policies with multilingual player-behavior tests and policy-specific evidence source/classification rules.
- Phase C2 typed dependency and milestone-criterion services with stable historical IDs, explicit lifecycle, deterministic graph validation, explicit evidence evaluation, and append-only evaluation history.
- `studio dependency add|list|show|update|deactivate` and `studio criterion add|list|show|update|evaluate|retire`, including transactional dry runs, confirmations, and stable JSON envelopes.
- Dedicated dependency state/schema plus dependency- and criterion-management guides, C1 dependency origins, four-part structural freshness fingerprints, and criterion-centered reports/status.
- Phase C1 dependency-aware milestone critical-path service with typed candidates, deterministic priority tiers, topological ordering, cycle reporting, three-to-seven guidance, stable IDs, history reconciliation, manual controls, and freshness snapshots.
- `studio path calculate`, `studio path show`, `studio path explain`, and `studio path check`, including transactional dry runs and stable JSON output.
- Critical-path, direction, current-state, issue, milestone-review, status, playbook, validation, and documentation integration.
- Phase B4 decision service with stable options, lifecycle transitions, resolution history, evidence-quality summaries, issue/evidence traceability, and acyclic supersession.
- `studio decision add`, `studio decision list`, `studio decision show`, `studio decision update`, and `studio decision resolve` with dry-run and stable JSON output.
- Decision-management documentation and behavioral coverage for recommendations, overrides, reopening, rollback, concurrency, and reporting.
- Phase B3 evidence service with classification/source separation, lifecycle history, controlled confidence defaults, bidirectional issue links, and acyclic supersession.
- `studio evidence add`, `studio evidence list`, `studio evidence show`, and `studio evidence update` with dry-run and stable JSON output.
- Evidence-quality summaries in status, Direction, issue, and milestone reports.
- Evidence-management documentation and behavioral coverage for integrity, reporting, rollback, and concurrency.
- Phase B2 issue service with normalized creation, queries, lifecycle transitions, stable historical ID allocation, and reference checks.
- `studio issue add`, `studio issue list`, `studio issue show`, and `studio issue update` with human-readable and JSON output.
- Transactional issue/critical-path membership updates, write-free dry runs, and an issue-management guide.
- Behavioral issue service and CLI coverage for lifecycle, filters, relationships, reports, rollback, and concurrency.
- Phase B1 state repository and copy-on-write transaction abstractions.
- Deterministic, flushed temporary output staging with per-file atomic replacement and rollback behavior.
- Canonical state hash checks for concurrent modification protection.
- Structured mutation results shared by core services and CLI presentation.
- `studio init` with root discovery, engine indicator detection, forced identity updates, and dry-run support.
- Behavioral regression coverage for initialization, validation, transactions, rollback, concurrency, dry runs, and CLI errors.

### Changed

- Milestone state/schema advances from `3.0` to `3.1`; `MC-001` preserves identity/history and migrates to `document-review`.
- Critical-path criterion fingerprints include verification policy, and rejected/superseded/deferred/retired/stale prerequisites no longer silently unlock dependents.
- Criterion verification no longer uses English keyword detection.
- Critical-path and milestone state advance to schema `3.0`; the duplicated success-criterion copies are removed and C1 criterion records migrate in place to explicit support/lifecycle/history fields.
- Phase C2 is complete. Automatic milestone progression, phase transitions, and workflow execution remain out of scope.
- Phase C1 introduced critical-path and milestone schema `2.0`; its migration remains documented in `docs/critical-path-engine.md`.
- Phase C1 is complete. Workflow automation and automatic phase transitions remain out of scope.
- Decision state advances to schema `2.0`; migration from the Phase A decision shape is documented.
- Direction, Current State, Open Issues, Milestone Review, and status output now expose prioritized decisions and evidence support without duplicating canonical relationships.
- Phase B roadmap now marks B1 through B4 complete without marking workflow automation or critical-path calculation complete.
- Evidence state advances to schema `2.0`; the migration from Phase A records is documented.
- Issue evidence attachment now updates both canonical relationship directions transactionally.
- Reports exclude superseded/retracted evidence from current support and apply simulated-review language when direct play evidence is absent.
- Issue validation now covers lifecycle requirements, self-references, duplicate path membership, and timestamp ordering.
- Open-issue and Direction reports now prioritize blockers, critical/major issues, user decisions, active path issues, and recent resolutions.
- Validation now detects stale generated reports, catalog phase mismatches, closed issues on the active path, and additional broken references.

## [0.1.0] - 2026-07-27

### Added

- Phase A foundation scaffold.
- Codex-native control layer with five roles and twelve playbooks.
- JSON schemas and valid initial canonical state.
- Workflow catalog, templates, generated reports, and delivery-horror example.
- `studio validate`, `studio status`, and `studio report`.
- Validation, reporting, and catalog tests.
