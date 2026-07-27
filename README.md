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
studio init --name "My Game"
studio validate
studio status
studio report
ruff format --check src tests
ruff check src tests
pytest
```

`studio init` initializes only project identity and conservatively detects Unity, Godot, or Unreal indicators. Then open the repository with Codex and ask for `/start`. Aliases such as `/clarify` and `/prototype-plan` are prompt conventions interpreted through `AGENTS.md`, not guaranteed native slash commands.

Preview initialization without writing:

```bash
studio init --name "Midnight Carrier" --engine Unity --platform Windows --dry-run
```

Run commands from the PGS root or a child directory. Use `--root PATH` to select a root explicitly. A valid root contains `AGENTS.md`, `.studio/`, and `pyproject.toml`.

## Core structure

- `AGENTS.md` is the Codex control layer.
- `.studio/workflow-catalog.json` describes phases and workflow references.
- `.studio/playbooks/` contains executable workflow guidance.
- `.studio/roles/` defines exactly five practical roles.
- `.studio/state/*.json` is canonical machine-readable state.
- `.studio/reports/*.md` is generated human-readable state.
- `studio init` uses the B1 transaction layer to initialize project identity.
- `studio validate`, `studio status`, and `studio report` inspect and render state.

## Initialization behavior

The only essential first-run value is the project name. Engine, engine version, platform, and genre may remain explicitly unknown (`null`). Review mode defaults to `guided`.

```bash
studio init \
  --name "Midnight Carrier" \
  --engine Unity \
  --engine-version "6.1" \
  --platform Windows \
  --genre Horror
```

If the project is already initialized, `studio init` is a successful no-op and recommends `studio status`. To change identity later, use `--force` with only the fields to change. Non-interactive forced writes also require `--yes`; `--force` never clears issues, evidence, decisions, milestones, or the critical path.

## Mutation safety

State mutations load and copy all canonical state, validate schemas and relationships, render every report in memory, and hash-check canonical files before staging. Changed JSON and reports are written to flushed temporary files on the same filesystem and atomically replaced one file at a time. A replacement error triggers restoration of outputs already replaced, and temporary files are cleaned.

This is not a database or a claim of full ACID behavior: a process crash, power loss, filesystem failure, or non-cooperating writer during the narrow multi-file replacement window can still leave a mixed revision. Concurrent canonical edits detected before replacement abort with the changed path and a reload-and-retry instruction. See `docs/state-mutation-safety.md`.

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

- **B1 complete:** validated transactions, atomic per-file replacement, rollback attempts, concurrent-modification detection, dry runs, and `studio init`.
- **B2 pending:** `studio issue add`, `studio issue update`, `studio decision add`, `studio decision resolve`, `studio evidence add`, and `studio next`.

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

PGS still excludes issue/decision/evidence mutation commands, a graph-based critical-path engine, engine/editor control, telemetry/video ingestion, multi-agent spawning, remote APIs, deployment, and full vertical-slice generation.

## License and attribution

PGS is MIT licensed. Architectural patterns were adapted from the MIT-licensed [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios). See `THIRD_PARTY_NOTICES.md`.
