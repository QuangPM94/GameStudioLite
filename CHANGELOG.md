# Changelog

All notable changes follow Keep a Changelog conventions.

## [Unreleased]

### Added

- Phase B1 state repository and copy-on-write transaction abstractions.
- Deterministic, flushed temporary output staging with per-file atomic replacement and rollback behavior.
- Canonical state hash checks for concurrent modification protection.
- Structured mutation results shared by core services and CLI presentation.
- `studio init` with root discovery, engine indicator detection, forced identity updates, and dry-run support.
- Behavioral regression coverage for initialization, validation, transactions, rollback, concurrency, dry runs, and CLI errors.

### Changed

- Validation now detects stale generated reports, catalog phase mismatches, closed issues on the active path, and additional broken references.
- Phase B roadmap now marks B1 complete while leaving B2 mutation commands pending.

## [0.1.0] - 2026-07-27

### Added

- Phase A foundation scaffold.
- Codex-native control layer with five roles and twelve playbooks.
- JSON schemas and valid initial canonical state.
- Workflow catalog, templates, generated reports, and delivery-horror example.
- `studio validate`, `studio status`, and `studio report`.
- Validation, reporting, and catalog tests.
