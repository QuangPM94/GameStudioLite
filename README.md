# GameStudioLite

GameStudioLite is a lightweight project-control framework for AI-assisted game development. It helps a solo developer or small team keep the current goal, evidence, blockers, and next action visible while working with Codex or another coding agent.

GameStudioLite currently manages:

- Project state
- Issues
- Evidence
- Decisions
- Dependencies
- Milestone criteria
- Critical path
- Generated reports
- Codex playbooks

It does not currently:

- Create a Unity, Godot, or Unreal project
- Control a game editor
- Automatically build or run the game
- Automatically transition phases or milestones
- Autonomously implement the game
- Ingest video or telemetry automatically

## Table of contents

[Overview](#1-overview) · [Capabilities](#2-current-capabilities) ·
[Requirements](#3-requirements) · [Installation](#4-install-gamestudiolite) ·
[Existing game](#5-quick-start-attach-to-an-existing-game) ·
[Empty directory](#6-quick-start-empty-project-directory) ·
[Bootstrap and init](#7-bootstrap-and-init-separately) ·
[Codex](#8-start-a-codex-session) · [Daily workflow](#9-daily-workflow) ·
[Commands](#10-core-command-reference) · [Examples](#11-important-usage-examples) ·
[Dry run and JSON](#12-dry-run-and-json-modes) ·
[Multiple projects](#13-multiple-project-usage) · [Updates](#14-updating-the-framework) ·
[Validation](#15-validation-commands) · [Troubleshooting](#16-troubleshooting) ·
[Development](#17-repository-development) · [Roadmap](#18-project-status-and-roadmap)

## 1. Overview

GameStudioLite is for developers who want practical project control while an AI agent helps plan, implement, and review a game prototype. It replaces loose chat history with project-local, schema-validated state and a short, dependency-aware critical path.

- The installed `studio` CLI provides the Python runtime and commands.
- Each game repository owns a lightweight `AGENTS.md` and `.studio/` scaffold.

Install the CLI once, then attach it to any number of independent projects:

```text
Installed GameStudioLite CLI
        │
        ├── Game A/.studio/
        ├── Game B/.studio/
        └── Game C/.studio/
```

Every project has independent state, reports, and ID sequences. Game A and Game B can both have an `ISS-0001`; neither record affects the other. No project state is stored globally.

The intended first-run flow is:

```text
Install GameStudioLite once
→ Open or create a game project
→ Bootstrap GameStudioLite into that project
→ Initialize project identity
→ Validate project state
→ Calculate the first critical path
→ Open the game project in Codex
→ Run /start
```

## 2. Current capabilities

| Capability                     | Status        |
| ------------------------------ | ------------- |
| Lightweight project bootstrap  | Available     |
| Multi-project support          | Available     |
| Issue management               | Available     |
| Evidence management            | Available     |
| Decision management            | Available     |
| Explicit dependencies          | Available     |
| Milestone criteria             | Available     |
| Critical-path calculation      | Available     |
| Generated reports              | Available     |
| Automatic workflow transitions | Not available |
| Engine editor integration      | Not available |
| Autonomous game implementation | Not available |

## 3. Requirements

- Python 3.11 or newer. CI currently verifies Python 3.11 and 3.12.
- Git, for installing from the repository and tracking project state.
- PowerShell for the Windows examples. Bash equivalents are included where useful.
- Codex, or another agent that can read and follow the project-local
  `AGENTS.md`.
- A game directory, empty or containing a Unity, Godot, Unreal, or custom project.

Unity, Godot, and Unreal are not framework requirements. Install an engine only when the game uses it.

## 4. Install GameStudioLite

### Development/editable installation

On Windows PowerShell:

```powershell
git clone https://github.com/QuangPM94/GameStudioLite.git F:\Tools\GameStudioLite
python -m pip install -e "F:\Tools\GameStudioLite[dev]"
```

On Bash:

```bash
git clone https://github.com/QuangPM94/GameStudioLite.git ~/tools/GameStudioLite
python -m pip install -e "$HOME/tools/GameStudioLite[dev]"
```

Verify the installation:

```powershell
studio --help
```

Editable installation is recommended while the framework is under active development. Reinstall after dependency or packaging changes.

### Wheel installation

Build a wheel:

```powershell
Set-Location F:\Tools\GameStudioLite
python -m build
```

Select the generated wheel instead of assuming its filename:

```powershell
$wheel = Get-ChildItem .\dist\*.whl |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

python -m pip install $wheel.FullName
```

The wheel includes the runtime and packaged scaffold. Game projects do not need the source checkout after installation.

See [Distribution](docs/distribution.md).

## 5. Quick start: attach to an existing game

This example attaches GameStudioLite to an existing Unity project named Midnight Carrier. Preview the operation first:

```powershell
Set-Location F:\Games\MidnightCarrier
studio bootstrap `
  --name "Midnight Carrier" `
  --engine Unity `
  --platform Windows `
  --dry-run
```

Dry run validates the proposal without writing files. If it is correct, run:

```powershell
studio bootstrap `
  --name "Midnight Carrier" `
  --engine Unity `
  --platform Windows
```

Validate the project and calculate its first path:

```powershell
studio validate
studio status
studio path calculate --yes
studio path show
```

Bootstrap creates:

```text
AGENTS.md
.studio/
├── config.json
├── framework.json
├── workflow-catalog.json
├── roles/
├── playbooks/
├── schemas/
├── state/
├── templates/
└── reports/
```

It does not modify unrelated project or engine content:

```text
Assets/
Packages/
ProjectSettings/
Content/
Source/
project.godot
*.uproject
.git/
README.md
.gitignore
```

Git metadata is preserved and bootstrap never creates a nested repository. See [Project bootstrap](docs/project-bootstrap.md).

## 6. Quick start: empty project directory

Create an empty directory and attach GameStudioLite:

```powershell
New-Item -ItemType Directory F:\Games\NewGame
Set-Location F:\Games\NewGame

studio bootstrap `
  --name "New Game" `
  --platform Windows
```

This creates and initializes the scaffold. It does not create an engine project, executable, scene, or assets. Engine files may be added later in the same directory.

## 7. Bootstrap and init separately

### One-step bootstrap and identity

Use one step when identity is already known:

```powershell
studio bootstrap `
  --name "Midnight Carrier" `
  --engine Unity `
  --platform Windows
```

This stages the scaffold, initializes identity, validates it, and renders reports as one operation.

### Two-step bootstrap, then identity

Use two steps to inspect the uninitialized scaffold or provide identity later:

```powershell
studio bootstrap

studio init `
  --name "Midnight Carrier" `
  --engine Unity `
  --platform Windows
```

The first command installs only the scaffold. `studio init` transactionally sets identity and renders reports. Repeating init is a no-op unless explicitly supplied fields are changed with `--force`.

## 8. Start a Codex session

Open the game repository as the active Codex workspace:

```text
Open:
F:\Games\MidnightCarrier

Do not open as the active game project:
F:\Tools\GameStudioLite
```

It contains the relevant `AGENTS.md`, playbooks, state, and reports. Then request:

```text
/start
```

The guided playbook sequence is:

```text
/start
→ /clarify
→ /prototype-plan
→ /build-prototype
→ /review-build
→ /playtest-review
→ /issue-map
→ /critical-path
→ /next-step
→ /iterate
→ /milestone-review
```

These aliases are workflow requests interpreted through `AGENTS.md`, not guaranteed native slash commands in every client. Playbooks guide the process; phase and milestone transitions are not fully automated.

## 9. Daily workflow

Read the current direction:

```powershell
studio status
studio path check
studio path show
```

If the path is stale:

```powershell
studio path calculate --dry-run
studio path calculate --yes
```

Continue with the Codex workflow recommended by status or the direction report:

```text
Inspect current state
→ Work on recommended path item
→ Record issues/evidence/decisions
→ Evaluate criteria
→ Check path freshness
→ Recalculate path
→ Review milestone
```

Reports under `.studio/reports/` are generated views of canonical JSON; do not edit them manually.

## 10. Core command reference

These are the main command families. Use command-specific help before a write.

### Project

```powershell
studio bootstrap
studio init --name "Game Name"
studio validate
studio status
studio report
```

### Issues

```powershell
studio issue add --help
studio issue list
studio issue show ISS-0001
studio issue update ISS-0001 --status acknowledged
```

### Evidence

```powershell
studio evidence add --help
studio evidence list
studio evidence show EVD-0001
studio evidence update EVD-0001 --confidence high --yes
```

### Decisions

```powershell
studio decision add --help
studio decision list
studio decision show DEC-0001
studio decision update DEC-0001 --urgency blocking --yes
studio decision resolve DEC-0001 --option OPT-B --reason "The owner selected this option." --yes
```

### Dependencies

```powershell
studio dependency add --help
studio dependency list
studio dependency show DEP-0001
studio dependency update DEP-0001 --reason "Updated execution-order rationale." --yes
studio dependency deactivate DEP-0001 --reason "The ordering requirement no longer applies." --yes
```

### Milestone criteria

```powershell
studio criterion add --help
studio criterion list
studio criterion show MC-001
studio criterion update MC-001 --verification-method "Review the approved project brief." --yes
studio criterion evaluate --help
studio criterion retire MC-001 --reason "The milestone requirement changed." --yes
```

### Critical path

```powershell
studio path calculate --dry-run
studio path show
studio path explain CP-0001
studio path check
```

For complete options, append `--help` to the real command path:

```powershell
studio issue add --help
studio criterion evaluate --help
studio path calculate --help
```

## 11. Important usage examples

IDs below assume a new sample project. Use the actual ID printed by each add command.

### Add an issue

```powershell
studio issue add `
  --title "Prototype fails to launch" `
  --severity blocker `
  --description "The current Windows build exits before the main scene loads." `
  --milestone-impact "External prototype testing cannot begin." `
  --recommended-action "Reproduce the failure and capture the build log." `
  --yes
```

This records the issue; it does not fix or launch the build.

### Add evidence

Record one directly observed human playtest with a limitation:

```powershell
studio evidence add `
  --title "First tester completed one delivery loop" `
  --claim "One tester completed the delivery loop without assistance." `
  --classification observed `
  --source-type human-playtest `
  --description "The developer observed the tester complete the loop in the current Windows build." `
  --confidence medium `
  --limitation "Only one tester has been observed." `
  --yes
```

Use `observed` only for directly accessible events. Unobserved human statements remain `user-reported`.

### Add and resolve a decision

Create two options and a framework recommendation:

```powershell
studio decision add `
  --question "How should the player locate the delivery room?" `
  --context "The corridor currently provides insufficient guidance." `
  --option "OPT-A|Explicit waypoint|Show a marker over the target door." `
  --option "OPT-B|Environmental guidance|Use signs, lighting, and stronger room numbering." `
  --recommended-option OPT-B `
  --recommendation-reason "Environmental guidance improves clarity while preserving immersion." `
  --trade-off "The recommended option is less explicit and must be verified with players." `
  --status ready `
  --yes
```

The recommendation is guidance, not the user's choice. Record the owner's final choice separately:

```powershell
studio decision resolve DEC-0001 `
  --option OPT-B `
  --reason "The owner selected environmental guidance to preserve immersion." `
  --consequence "Revise room numbers, signs, and corridor lighting." `
  --follow-up "Run another observed navigation playtest." `
  --yes
```

### Add a dependency

Both endpoints must exist. This means “ISS-0003 requires DEC-0001”:

```powershell
studio dependency add `
  --prerequisite DEC-0001 `
  --dependent ISS-0003 `
  --reason "Implementation depends on the selected guidance approach." `
  --yes
```

Terminal does not always mean satisfied. Resolved decisions satisfy edges; rejected, deferred, or superseded decisions do not. Update or deactivate such edges.

### Add a criterion

```powershell
studio criterion add `
  --description "A new player can complete one delivery loop without assistance." `
  --required `
  --completion-condition "Two of three observed testers complete the loop unaided." `
  --verification-method "Observed human playtest using the current build." `
  --verification-policy observed-player-behavior `
  --yes
```

Verification policy is explicit and language-independent; evidence requirements are not inferred from English keywords.

### Evaluate a criterion

Assuming the criterion is `MC-002` and evidence is `EVD-0001`, record partial support:

```powershell
studio criterion evaluate MC-002 `
  --support partially-supported `
  --evidence EVD-0001 `
  --reason "One observed tester completed the delivery loop unaided." `
  --limitation "Two additional observed testers are required by the completion condition." `
  --yes
```

Evidence never silently verifies a criterion. Reevaluate after relevant changes.

## 12. Dry-run and JSON modes

Dry run validates proposals without writing files, state, or reports:

```powershell
studio bootstrap --dry-run
studio path calculate --dry-run
```

JSON mode is available on bootstrap, validation, framework validation, and supported state/path commands:

```powershell
studio validate --json
studio issue list --json
studio evidence list --json
studio decision list --json
studio dependency list --json
studio criterion list --json
studio path show --json
studio path check --json
```

JSON output is for scripts, CI, and integrations. Supported writes also expose JSON envelopes; inspect their help.

`studio status` currently provides human-readable output only. Use:

```powershell
studio status
```

for a concise summary. `studio report` and `studio init` are also human-readable only.

## 13. Multiple-project usage

One installed CLI serves multiple projects:

```powershell
Set-Location F:\Games\GameA
studio bootstrap --name "Game A"

Set-Location F:\Games\GameB
studio bootstrap --name "Game B"
```

- Both projects use the same installed `studio` executable.
- Both may independently allocate `ISS-0001`.
- State never lives globally.
- Each project stores canonical state under `.studio/state/`.
- Each project stores generated reports under `.studio/reports/`.
- Game A cannot mutate Game B unless Game B is explicitly selected with `--root`.

Commit state and reports according to each project's version-control policy.

## 14. Updating the framework

For an editable installation:

```powershell
Set-Location F:\Tools\GameStudioLite
git pull
python -m pip install -e ".[dev]"
```

Updating the CLI does not upgrade existing scaffolds. Upgrade and migration commands are not implemented.

Before refreshing managed files in an important game project:

1. Commit or back up the project state.
2. Run `studio bootstrap --dry-run`.
3. Review every conflict and proposed update.
4. Use `studio bootstrap --force --yes` only when the managed-file replacement
   is understood.

Do not run force blindly. It protects state and reports, but future schema changes may still need migration. There is no `studio upgrade`.

## 15. Validation commands

### In a game project

```powershell
studio validate
```

This validates scaffold, schemas, relationships, and report freshness. It does not require framework source, tests, docs, package metadata, or CI.

### In the GameStudioLite framework source repository

```powershell
studio framework validate
```

This also validates development files, packaged resources, and scaffold synchronization. It is not for normal game repositories.

## 16. Troubleshooting

### `No Practical Game Studio project found`

From the intended game directory:

```powershell
studio bootstrap
```

`studio init` needs an existing scaffold.

### Bootstrap reports a managed-file conflict

Bootstrap reports conflicts before writing. Inspect them first:

```powershell
studio bootstrap --dry-run
```

For an understood managed-file replacement:

```powershell
studio bootstrap --force --yes
```

Force does not overwrite protected state or reports.

### The wrong project is detected

Select the root explicitly when upward discovery finds the wrong project:

```powershell
studio status --root F:\Games\CorrectGame
```

### The critical path is stale

Inspect, preview, and confirm:

```powershell
studio path check
studio path calculate --dry-run
studio path calculate --yes
```

### The engine was not detected

Engine detection is conservative. Explicitly update the engine field when needed:

```powershell
studio init --force --engine Unity --yes
```

This changes metadata only; it does not install or control Unity.

### Validation fails after manual JSON edits

Canonical state is relationship-sensitive. Prefer supported commands. After manual recovery, restore a known-good revision and run:

```powershell
studio validate
studio report
```

See [State mutation safety](docs/state-mutation-safety.md).

## 17. Repository development

Prepare a contributor checkout:

```powershell
git clone https://github.com/QuangPM94/GameStudioLite.git
Set-Location GameStudioLite
python -m pip install -e ".[dev]"

ruff format --check src tests
ruff check src tests
python -m pytest
python -m compileall -q src tests
python -m build
studio framework validate
studio validate
studio report
```

Continuous integration covers:

- Ubuntu with Python 3.11
- Ubuntu with Python 3.12
- Windows with Python 3.11
- Formatting, lint, tests, and compilation
- Framework and game-project validation
- Source and wheel builds
- Wheel installation
- Lightweight project bootstrap
- Multi-project state isolation

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting framework changes.

## 18. Project status and roadmap

### Available now

- Lightweight multi-project bootstrap
- Transactional project state
- Issues, evidence, decisions, and dependencies
- Milestone criteria with explicit verification policies
- Dependency-aware critical path
- Generated reports and Codex playbooks
- Wheel distribution
- Cross-platform CI

### Planned, not yet available

- Scaffold upgrade and migration
- Structured workflow readiness
- Stable milestone IDs
- Controlled phase and milestone transitions
- Engine adapters
- Media and telemetry ingestion
- Autonomous implementation

No dates are promised. This README does not implement C3 or later work.

## Further documentation

[Bootstrap](docs/project-bootstrap.md) · [Distribution](docs/distribution.md) ·
[Issues](docs/issue-management.md) · [Evidence](docs/evidence-management.md) ·
[Decisions](docs/decision-management.md) · [Dependencies](docs/dependency-management.md) ·
[Criteria](docs/milestone-criteria-management.md) · [Critical path](docs/critical-path-engine.md) ·
[Mutation safety](docs/state-mutation-safety.md)

## License and attribution

GameStudioLite uses the [MIT License](LICENSE). Architectural patterns were adapted from the MIT-licensed [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
