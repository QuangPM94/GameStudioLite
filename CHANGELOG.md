# Changelog

All notable changes follow Keep a Changelog conventions.

## [Unreleased]

### Added

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

- Issue validation now covers lifecycle requirements, self-references, duplicate path membership, and timestamp ordering.
- Open-issue and Direction reports now prioritize blockers, critical/major issues, user decisions, active path issues, and recent resolutions.
- Validation now detects stale generated reports, catalog phase mismatches, closed issues on the active path, and additional broken references.
- Phase B roadmap now marks B1 and B2 complete without marking all of Phase B complete.

## [0.1.0] - 2026-07-27

### Added

- Phase A foundation scaffold.
- Codex-native control layer with five roles and twelve playbooks.
- JSON schemas and valid initial canonical state.
- Workflow catalog, templates, generated reports, and delivery-horror example.
- `studio validate`, `studio status`, and `studio report`.
- Validation, reporting, and catalog tests.
