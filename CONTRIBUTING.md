# Contributing

PGS welcomes focused changes that improve prototype delivery or evidence-backed decisions.

1. Open an issue describing the consumer and validation purpose of a proposed document or feature.
2. Keep canonical state in `.studio/state/*.json`; do not hand-edit generated reports. New mutation commands must use `StateTransaction`. Use `studio issue` commands for normal issue work; edit issue JSON directly only for framework maintenance or recovery.
3. Preserve the evidence labels and do not claim inaccessible runtime behavior was observed.
4. Add or update tests for CLI, schema, state, catalog, or report behavior.
5. Run `ruff format --check src tests`, `ruff check src tests`, `studio validate`, `studio report`, `studio status`, and `python -m pytest`.
6. Add failure-injection tests for schema, relationship, rendering, replacement, and concurrency risks introduced by a mutation.
7. Keep commits intentional and avoid bundling unrelated production-scale features.

Use `studio init --dry-run` and `studio issue add|update --dry-run` when checking mutation behavior against a real project. Fixture and manual CLI tests must not mutate the framework repository's canonical state.

PGS stays engine-neutral and dependency-light. New dependencies require a clear maintenance and user benefit.
