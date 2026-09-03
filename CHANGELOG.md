# Changelog

All notable changes follow Keep a Changelog conventions.

## [Unreleased]

### Added

- Execution core (`practical_game_studio.execution`): one supervised way to run
  an external process. Nothing runs forever, nothing waits for stdin, output
  survives undecodable bytes, and a process the framework killed maps to
  `unknown` rather than `failed`. Credential-shaped environment variables are
  withheld from child processes and secret-looking arguments are redacted
  before being written to `runs.json`.
- Engine adapter layer (`practical_game_studio.adapters`): capability-based
  contract where detection (does this adapter recognise the project?) and
  probing (what can it do on this machine?) are separate questions. A
  capability nobody probed is not supported, and an unsupported operation
  refuses by name listing what the adapter can do.
- Godot CLI reference adapter: project and engine detection, headless run,
  gdUnit4/GUT test support, and debug/release export, with no MCP or editor
  automation required.
- `studio doctor`: probes what the machine can actually do and reports
  `READY`/`UNAVAILABLE`/`UNKNOWN`/`NOT CONFIGURED` without ever inferring, and
  changes nothing.
- `studio run`, `studio test`, `studio build`: adapter-backed execution that
  records RUN and ART entries and creates no evidence. Exit code 4 separates
  "could not be attempted" from a failure.
- `studio verify --level static|smoke|runtime|gameplay|release`: cumulative
  checks whose report status is the worst of its checks, which always prints
  what it did NOT establish, and which offers evidence *proposals* rather than
  asserting evidence. `gameplay` can never pass on its own.
- `docs/execution-core.md` and `docs/engine-adapters.md`.
- Execution data model: `runs.json` (`RUN-####`) and `artifacts.json`
  (`ART-####`) canonical documents, with `studio execution list|show` and
  `studio artifact add|list|show|verify`. A run is recorded before its result
  exists, `unknown` stays distinguishable from `failed`, and captured output is
  truncated with an explicit marker naming what was dropped.
- Artifact verification that tells `present`, `modified`, `missing`, and
  `unverified` apart, read-only unless `--record` is passed, exiting non-zero
  when anything did not match.
- Evidence provenance: `related_runs` / `related_artifacts` with
  `studio evidence add --run/--artifact` and
  `studio evidence update --add-run/--remove-artifact`. References to runs or
  artifacts that do not exist are refused, and `studio validate` checks every
  cross-reference. Execution records never become evidence on their own.
- Migration `003` (scaffold 1.2 -> 1.3) creating both documents empty and adding
  the evidence reference lists (evidence schema 2.0 -> 2.1). The upgrade engine
  now tolerates a state document that does not exist yet and creates it inside
  the same snapshot/rollback window.
- `docs/execution-records.md` describing what runs and artifacts are, and why
  neither is evidence.
- `studio upgrade check|plan|apply`: a migration engine that carries a project
  from the scaffold version it records to the version the installed package
  produces. State is migrated in memory and validated against the new schemas
  before any file is touched; `--dry-run` proves the upgrade would validate;
  a failure after the first write restores the pre-upgrade snapshot.
- Migration `001` (scaffold 1.0 -> 1.1): canonical state stores the recommended
  next workflow as a workflow id (`recommended_next_workflow: "start"`) instead
  of a slash alias (`recommended_next_playbook: "/start"`).
- Migration `002` (scaffold 1.1 -> 1.2): `MS-####` milestone ids and a milestone
  registry in `milestone.json`, referenced by `project.json`,
  `critical-path.json`, and every criterion, so milestone references survive a
  title rename.
- `docs/upgrade-and-migrations.md` describing the upgrade contract and how to
  write a migration.

- `src/practical_game_studio/commands/` package: one module per `studio`
  command noun, each registering its own arguments and rendering its own
  human/JSON output, with `cli.py` reduced to a router. No CLI syntax, stdout
  text, exit code, or JSON envelope changed.
- `docs/baseline.md` recording the pre-execution-layer baseline: test count,
  CLI surface, package/scaffold/catalog versions, and schema versions.
- Cross-platform C2.2 distribution CI: source/wheel builds, isolated wheel
  installation, lightweight bootstrap/init/validation, and two-project state
  isolation smoke on Ubuntu and Windows Python 3.11.
- Phase C2.2 lightweight `studio bootstrap` for empty or existing game
  repositories, including staged validation, managed-file conflict detection,
  protected state/reports, deterministic dry runs, rollback, and JSON output.
- Bootstrap manifest/schema, package-safe scaffold resource loading,
  multi-project root discovery without `pyproject.toml`, and
  `studio framework validate`.
- Explicit wheel package-data for the complete hidden scaffold plus isolated
  build/install/bootstrap acceptance outside the source checkout.
- Behavioral coverage for Unity-, Godot-, and Unreal-like attachment,
  idempotency, rollback, concurrency, and independent project state/IDs.
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

- Human output now renders the recommended workflow as its canonical `GS:`
  command (`GS:start`) rather than the legacy alias (`/start`). Both spellings
  remain valid agent input.
- GitHub Actions checkout/setup-python actions move to Node 24-based stable
  majors to remove Node 20 deprecation warnings.
- `studio validate` now validates a lightweight game project; framework source,
  tests, docs, package metadata, and scaffold synchronization are checked by
  `studio framework validate`.
- Project roots use valid config, bootstrap manifest, and state markers instead
  of requiring `pyproject.toml`.
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
