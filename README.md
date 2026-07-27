# Practical Game Studio (PGS)

Practical Game Studio is a lightweight, Codex-native framework for taking a game idea through a playable prototype and an evidence-backed vertical-slice decision.

```text
Clarify → Prototype plan → Build → Evaluate → Map issues
        → Critical path → Next action → Iterate → Vertical-slice decision
```

At every step PGS keeps the current goal, evidence, blockers, and recommended next action visible. It favors a runnable experiment over production architecture and a short critical path over a large backlog.

PGS is an independent open-source project. It is not affiliated with Donchitos/Claude-Code-Game-Studios, Anthropic, OpenAI, Unity, Godot, or Epic Games.

## Quick start

PGS requires Python 3.11 or later.

```bash
python -m pip install -e ".[dev]"
studio validate
studio status
studio report
ruff format --check src tests
ruff check src tests
pytest
```

Open the repository with Codex and ask for `/start`. Aliases such as `/clarify` and `/prototype-plan` are prompt conventions interpreted through `AGENTS.md`, not guaranteed native slash commands.

## Core structure

- `AGENTS.md` is the Codex control layer.
- `.studio/workflow-catalog.json` describes phases and workflow references.
- `.studio/playbooks/` contains executable workflow guidance.
- `.studio/roles/` defines exactly five practical roles.
- `.studio/state/*.json` is canonical machine-readable state.
- `.studio/reports/*.md` is generated human-readable state.
- `studio validate`, `studio status`, and `studio report` form the Phase A CLI.

## Evidence

Every finding uses one of four labels:

- `OBSERVED`: direct build, runtime, media, telemetry, or test evidence.
- `USER_REPORTED`: a human report.
- `INFERRED`: analysis of source or specifications.
- `UNKNOWN`: unsupported.

A source-only review is never represented as an actual playtest.

## Review modes

- `fast`: maximum autonomy; strategic or irreversible questions only.
- `guided`: default; decisions are batched at phase boundaries.
- `strict`: additional design and technical review.

No mode requires approval for each file.

## Prototype and vertical slice

A prototype is the smallest playable artifact that can falsify the current hypothesis. A vertical slice is a representative quality target created only after the core experience earns a `PROCEED` verdict. `PROCEED` creates a vertical-slice plan, not a production architecture.

## Roadmap

### Phase A — Foundation scaffold

Codex instructions, roles, playbooks, catalog, schemas, initial state, templates, reporting, validation, and tests.

### Phase B — State mutation and issue management

Add `studio init`, `studio issue add`, `studio issue update`, `studio decision add`, `studio decision resolve`, `studio evidence add`, and `studio next`.

### Phase C — Critical-path engine

Add dependency-aware ordering, milestone blocking analysis, and three-to-seven-item path generation.

### Phase D — Guided workflow execution

Add robust workflow transitions and automatic Direction Report updates.

### Phase E — Player Advocate evaluation

Add structured ingestion for screenshots, videos, logs, telemetry, and human notes.

### Phase F — Engine adapters

Add optional Unity, Godot, and Unreal adapters without coupling the core to one engine.

### Phase G — Dogfood and hardening

Use the framework against a small delivery-horror prototype and revise from observed usage.

Phase A intentionally excludes state mutation commands, a graph-based critical-path engine, engine/editor control, telemetry/video ingestion, multi-agent spawning, remote APIs, deployment, and full vertical-slice generation.

## License and attribution

PGS is MIT licensed. Architectural patterns were adapted from the MIT-licensed [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios). See `THIRD_PARTY_NOTICES.md`.
