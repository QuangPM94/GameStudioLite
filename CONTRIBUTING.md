# Contributing

PGS welcomes focused changes that improve prototype delivery or evidence-backed decisions.

1. Open an issue describing the consumer and validation purpose of a proposed document or feature.
2. Keep canonical state in `.studio/state/*.json`; do not hand-edit generated reports. New mutation commands must use `StateTransaction`. Use `studio issue`, `studio evidence`, `studio decision`, `studio dependency`, `studio criterion`, and `studio path` commands for normal state work; edit their JSON directly only for framework maintenance or recovery.
3. Preserve the evidence labels and do not claim inaccessible runtime behavior was observed.
4. Add or update tests for CLI, schema, state, catalog, or report behavior.
5. Run `ruff format --check src tests`, `ruff check src tests`, `python -m pytest`, `python -m compileall -q src tests`, `python -m build`, `studio framework validate`, `studio validate`, `studio report`, `studio status`, `studio path check`, and `git diff --check`.
6. Add failure-injection tests for schema, relationship, rendering, replacement, and concurrency risks introduced by a mutation.
7. Keep commits intentional and avoid bundling unrelated production-scale features.

Use `studio init --dry-run`, `studio issue add|update --dry-run`, `studio evidence add|update --dry-run`, `studio decision add|update|resolve --dry-run`, `studio dependency add|update|deactivate --dry-run`, `studio criterion add|update|evaluate|retire --dry-run`, `studio path calculate --dry-run`, and `studio upgrade apply --dry-run` when checking mutation behavior against a real project. Fixture and manual CLI tests must not mutate the framework repository's canonical state.

Changing the shape of canonical state requires a migration in
`src/practical_game_studio/migrations/`; see
[docs/upgrade-and-migrations.md](docs/upgrade-and-migrations.md). A release that
changes state without one leaves existing projects unupgradeable.

CLI code is split by command noun. `src/practical_game_studio/cli.py` is a
router: it builds the parser from `src/practical_game_studio/commands/` and
dispatches a parsed command to the module that owns it. A new command gets a
new module there with a `register` and a `run` function; helpers shared by more
than one command module belong in `commands/_shared.py`. Domain rules and state
mutation stay in the service modules, never in a command module.

PGS stays engine-neutral and dependency-light. New dependencies require a clear maintenance and user benefit.

The packaged scaffold in `src/practical_game_studio/scaffold/` is the canonical
seed for new game projects. Keep framework-managed root files synchronized and
run `studio framework validate`. Live root state and generated reports are
validated as project data rather than forced back to seed bytes.
