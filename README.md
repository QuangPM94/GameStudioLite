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
studio issue add --title "Prototype does not launch" --severity blocker \
  --milestone-impact "The prototype cannot be evaluated." --yes
studio issue list
studio evidence add --title "Prototype launches" \
  --claim "The launch command completed successfully." \
  --classification observed --source-type test-output \
  --source "pytest output" --yes
studio evidence list
studio decision add --question "How should the player find the room?" \
  --context "The corridor lacks sufficient guidance." \
  --option 'OPT-A|Waypoint|Show an explicit marker.' \
  --option 'OPT-B|Signs|Improve environmental guidance.' \
  --recommended-option OPT-B \
  --recommendation-reason "Signs preserve immersion." --yes
studio decision list
studio dependency add --prerequisite DEC-0001 --dependent ISS-0001 \
  --reason "Implementation requires the selected option." --yes
studio criterion list
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
- `studio issue add|list|show|update` provides transactional B2 issue management.
- `studio evidence add|list|show|update` provides transactional B3 evidence management.
- `studio decision add|list|show|update|resolve` provides transactional B4 decision management.
- `studio path calculate|show|explain|check` provides the C1 milestone priority path.
- `studio dependency add|list|show|update|deactivate` provides transactional C2 dependency authoring.
- `studio criterion add|list|show|update|evaluate|retire` provides transactional C2 milestone-criterion management.
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

## Issue management

Record an issue with a title, severity, and at least one useful context field:

```bash
studio issue add \
  --title "Player cannot identify the delivery room" \
  --severity critical \
  --player-impact "The player stops progressing in the corridor." \
  --recommended-action "Improve apartment-number visibility." \
  --yes
```

Guided and strict projects confirm issue creation; use `--yes` for non-interactive writes. Fast mode commits without that extra confirmation. `--dry-run` validates and renders the proposed revision without writing, and `--json` returns a stable automation envelope.

```bash
studio issue list
studio issue show ISS-0001
studio issue update ISS-0001 --status in-progress --owner developer
studio issue update ISS-0001 --status resolved \
  --resolution "Increased contrast and added directional signage."
```

Issues are historical records and cannot be deleted. See `docs/issue-management.md` for lifecycle transitions, filters, critical-path behavior, evidence references, and exit codes.

## Evidence management

Evidence separates classification (`observed`, `user-reported`, `inferred`, or `unknown`) from source type. Records may link to multiple issues, remain auditable after retraction or supersession, and update both relationship directions transactionally.

```bash
studio evidence list --classification observed
studio evidence show EVD-0001
studio evidence update EVD-0001 --status retracted
```

Only active evidence counts as current support. See `docs/evidence-management.md` for confidence defaults, source requirements, lifecycle rules, supersession, migration, dry runs, and JSON output.

## Decision management

Decisions represent meaningful forks with two-to-six stable options, a recommendation, its reason and trade-offs, evidence support, affected issues, owner, and urgency. They remain historical after resolution, rejection, or supersession.

```bash
studio decision list
studio decision show DEC-0001
studio decision update DEC-0001 --urgency blocking
studio decision resolve DEC-0001 --option OPT-B \
  --reason "It improves clarity without adding HUD guidance." --yes
```

Issue and evidence references are owned by decision state and derived into reports. See `docs/decision-management.md` for option syntax, lifecycle transitions, resolution history, evidence-support levels, migration, dry runs, JSON output, and exit codes.

## Milestone critical path

Phase C1 calculates a deterministic, dependency-aware milestone priority path:

```bash
studio path calculate --dry-run
studio path calculate --yes
studio path show
studio path explain CP-0001
studio path check
```

The active path normally contains three to seven items, but fewer legitimate blockers are valid and never padded. Stable `CP-` IDs survive recalculation, completed work remains in compact history, and persistent include/exclude controls are visible. This is not duration-based Critical Path Method and does not promise an exact schedule. See `docs/critical-path-engine.md`.

## Dependencies and milestone criteria

Phase C2 records hard execution order as `dependent requires prerequisite`:

```bash
studio dependency add --prerequisite DEC-0001 --dependent ISS-0003 \
  --reason "The implementation approach requires the selected option." --dry-run
studio dependency list
studio dependency show DEP-0001
```

Criteria have a lifecycle separate from explicit evidence support:

```bash
studio criterion add --description "One delivery loop is playable." \
  --required --completion-condition "Two of three observed testers finish unaided." \
  --verification-method "Observed human playtest." --dry-run
studio criterion evaluate MC-002 --support partially-supported \
  --evidence EVD-0004 --reason "One observed tester finished unaided." \
  --limitation "Two additional observations are required." --yes
```

Evidence never silently verifies a criterion. Dependency and criterion writes mark path freshness precisely and recommend a check or recalculation; they do not change the project phase or milestone. See `docs/dependency-management.md` and `docs/milestone-criteria-management.md`.

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
- **B2 complete:** transactional `studio issue add`, `issue list`, `issue show`, and `issue update`, including dry runs and JSON output.
- **B3 complete:** transactional evidence creation, queries, updates, issue linking, retraction, and supersession.
- **B4 complete:** transactional decision creation, queries, updates, resolution history, recommendation support, and supersession.
- **Phase B complete.**

### Phase C — Critical-path engine

- **C1 complete:** dependency-aware candidate selection, deterministic ordering, three-to-seven guidance, stable path IDs/history, manual controls, freshness checks, reports, and `studio path calculate|show|explain|check`.
- **C2 complete:** explicit dependency registry, cycle-safe authoring, transactional criterion lifecycle/evaluation/history, evidence-lifecycle freshness, and C1 ordering/report integration.
- **Later Phase C work:** bounded manual workflow readiness and milestone review guidance built on explicit structure.

### Phase D — Guided workflow execution

Add robust workflow transitions and automatic Direction Report updates.

### Phase E — Player Advocate evaluation

Add structured ingestion for screenshots, videos, logs, telemetry, and human notes.

### Phase F — Engine adapters

Add optional Unity, Godot, and Unreal adapters without coupling the core to one engine.

### Phase G — Dogfood and hardening

Use the framework against a small delivery-horror prototype and revise from observed usage.

PGS still excludes automatic phase transitions, workflow execution, engine/editor control, telemetry/video ingestion, autonomous game implementation, multi-agent orchestration, remote APIs, deployment, and full vertical-slice generation.

## License and attribution

PGS is MIT licensed. Architectural patterns were adapted from the MIT-licensed [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios). See `THIRD_PARTY_NOTICES.md`.
