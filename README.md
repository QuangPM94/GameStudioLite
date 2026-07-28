# GameStudioLite

GameStudioLite is a lightweight project-control framework for AI-assisted game development. It helps a solo developer or small team keep the current goal, evidence, blockers, decisions, and next action visible while working with a repository-aware AI agent.

GameStudioLite is **not tied to Codex**. Any AI agent can use it when the agent can:

- Open the game repository
- Read the project-local `AGENTS.md`
- Read files under `.studio/`
- Run the installed `studio` CLI
- Follow explicit workflow instructions
- Respect the user's final decision authority

GameStudioLite currently manages:

- Project state
- Issues
- Evidence
- Decisions
- Dependencies
- Milestone criteria
- Dependency-aware critical paths
- Generated reports
- AI-agent workflow playbooks

It does not currently:

- Create a Unity, Godot, or Unreal project
- Control a game editor
- Automatically build or run the game
- Automatically transition phases or milestones
- Autonomously implement an entire game
- Automatically ingest video or telemetry
- Provide production multiplayer infrastructure

## Table of contents

[Overview](#1-overview) · [Capabilities](#2-current-capabilities) ·
[Requirements](#3-requirements) · [Installation](#4-install-gamestudiolite) ·
[Existing game](#5-quick-start-attach-to-an-existing-game) ·
[Empty directory](#6-quick-start-empty-project-directory) ·
[Bootstrap and init](#7-bootstrap-and-init-separately) ·
[AI agent setup](#8-use-gamestudiolite-with-an-ai-agent) ·
[Agent workflows](#9-ai-agent-workflow-aliases) ·
[Daily workflow](#10-daily-workflow) ·
[CLI commands](#11-core-cli-command-reference) ·
[Examples](#12-important-usage-examples) ·
[Dry run and JSON](#13-dry-run-and-json-modes) ·
[Multiple projects](#14-multiple-project-usage) ·
[Updates](#15-updating-the-framework) ·
[Validation](#16-validation-commands) ·
[Troubleshooting](#17-troubleshooting) ·
[Development](#18-repository-development) ·
[Roadmap](#19-project-status-and-roadmap)

## 1. Overview

GameStudioLite gives an AI agent a stable, project-local control layer instead of relying on loose chat history.

The installed `studio` CLI provides the runtime and state-management commands. Each game repository owns a lightweight scaffold:

```text
Game project/
├── AGENTS.md
└── .studio/
    ├── config.json
    ├── framework.json
    ├── workflow-catalog.json
    ├── playbooks/
    ├── roles/
    ├── schemas/
    ├── state/
    ├── templates/
    └── reports/
```

Install the CLI once, then use it with multiple independent projects:

```text
Installed GameStudioLite CLI
        │
        ├── Game A/.studio/
        ├── Game B/.studio/
        └── Game C/.studio/
```

Every project has independent state, reports, and ID sequences. Game A and Game B can both contain `ISS-0001`; neither record affects the other.

The intended first-run flow is:

```text
Install GameStudioLite once
→ Open or create a game project
→ Bootstrap GameStudioLite into that project
→ Initialize project identity
→ Validate project state
→ Calculate the first critical path
→ Open the game repository in an AI agent
→ Ask the agent to read AGENTS.md
→ Run the /start workflow
```

## 2. Current capabilities

| Capability | Status |
| --- | --- |
| Lightweight project bootstrap | Available |
| Multi-project support | Available |
| AI-agent workflow playbooks | Available |
| Issue management | Available |
| Evidence management | Available |
| Decision management | Available |
| Explicit dependencies | Available |
| Milestone criteria | Available |
| Critical-path calculation | Available |
| Generated reports | Available |
| Automatic workflow transitions | Not available |
| Engine editor integration | Not available |
| Autonomous game implementation | Not available |

## 3. Requirements

- Python 3.11 or newer. CI currently verifies Python 3.11 and 3.12.
- Git, for installation and project version control.
- PowerShell for the Windows examples. Bash equivalents are included where useful.
- A game directory, empty or containing an existing engine project.
- An AI agent that can read repository files and, ideally, run terminal commands.

The AI agent does not need a native slash-command system. Inputs such as `/clarify` are workflow aliases. When an agent does not recognize them natively, use a normal-language request such as:

```text
Read AGENTS.md and execute the /clarify workflow.
```

Unity, Godot, and Unreal are not GameStudioLite requirements. Install an engine only when the game uses it.

## 4. Install GameStudioLite

### Development/editable installation

Windows PowerShell:

```powershell
git clone https://github.com/QuangPM94/GameStudioLite.git F:\Tools\GameStudioLite
python -m pip install -e "F:\Tools\GameStudioLite[dev]"
```

Bash:

```bash
git clone https://github.com/QuangPM94/GameStudioLite.git ~/tools/GameStudioLite
python -m pip install -e "$HOME/tools/GameStudioLite[dev]"
```

Verify the installation:

```powershell
studio --help
```

Editable installation is recommended while the framework remains under active development.

### Wheel installation

Build a wheel:

```powershell
Set-Location F:\Tools\GameStudioLite
python -m build
```

Select the generated wheel rather than assuming its filename:

```powershell
$wheel = Get-ChildItem .\dist\*.whl |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

python -m pip install $wheel.FullName
```

The wheel includes the runtime and packaged scaffold. A game project does not need the framework source checkout after installation.

See [Distribution](docs/distribution.md).

## 5. Quick start: attach to an existing game

This example attaches GameStudioLite to an existing Unity project.

Preview the operation:

```powershell
Set-Location F:\Games\MyGame

studio bootstrap `
  --name "My Game" `
  --engine Unity `
  --platform Windows `
  --dry-run
```

Run it for real:

```powershell
studio bootstrap `
  --name "My Game" `
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

Bootstrap creates only the GameStudioLite control layer. It does not replace unrelated project or engine content such as:

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

Git metadata is preserved, and bootstrap never creates a nested Git repository.

See [Project bootstrap](docs/project-bootstrap.md).

## 6. Quick start: empty project directory

Create an empty directory and attach GameStudioLite:

```powershell
New-Item -ItemType Directory F:\Games\NewGame
Set-Location F:\Games\NewGame

studio bootstrap `
  --name "New Game" `
  --platform Windows
```

This creates and initializes the GameStudioLite scaffold. It does not create an engine project, executable, scene, or asset.

The engine project may be added later in the same directory.

## 7. Bootstrap and init separately

### One-step bootstrap and identity

Use one step when project identity is already known:

```powershell
studio bootstrap `
  --name "My Game" `
  --engine Unity `
  --platform Mobile `
  --genre "Strategy"
```

This stages the scaffold, initializes identity, validates the result, and renders reports as one operation.

### Two-step bootstrap, then identity

Use two steps when identity will be supplied later:

```powershell
studio bootstrap

studio init `
  --name "My Game" `
  --engine Unity `
  --platform Mobile
```

The first command installs only the scaffold. `studio init` transactionally sets identity and renders reports.

Repeating `studio init` is a no-op unless explicitly supplied fields are changed with `--force`.

## 8. Use GameStudioLite with an AI agent

Open the **game repository**, not the GameStudioLite framework repository, as the agent's active workspace.

```text
Open:
F:\Games\MyGame

Do not use as the active game project:
F:\Tools\GameStudioLite
```

The game repository contains the relevant:

- `AGENTS.md`
- `.studio/workflow-catalog.json`
- `.studio/playbooks/`
- `.studio/roles/`
- `.studio/state/`
- `.studio/reports/`

Start with:

```text
Read AGENTS.md and execute the /start workflow.
```

An agent with native workflow-alias support may accept:

```text
/start
```

The aliases are instructions interpreted through `AGENTS.md` and the referenced playbook. They are not guaranteed to be native slash commands in every AI client.

### Agent execution contract

A compatible AI agent should:

1. Read the root `AGENTS.md`.
2. Read `.studio/workflow-catalog.json`.
3. Read the playbook for the requested alias.
4. Read relevant canonical state under `.studio/state/`.
5. Use `studio` commands for state mutations instead of manually editing canonical JSON.
6. Distinguish an agent recommendation from the user's final decision.
7. Never label a claim `observed` unless the observation is directly accessible.
8. Avoid work explicitly listed under “Do not work on yet.”
9. Validate and regenerate reports after meaningful state changes.
10. Finish with the current direction, evidence, unknowns, critical path, and recommended next workflow.

A useful generic prompt is:

```text
Read AGENTS.md and the requested workflow playbook.
Inspect current project state before acting.
Use the supported studio CLI for state changes.
Do not invent evidence or silently make final user decisions.
Execute the /start workflow and report the recommended next workflow.
```

## 9. AI-agent workflow aliases

These workflows are available to any compatible AI agent. They are not PowerShell commands.

| Workflow | Use it when | What the AI agent should do |
| --- | --- | --- |
| `/start` | Opening a new or existing project for the first time | Inspect repository, engine indicators, project state, build status, current phase, milestone, blockers, and recommend the correct entry workflow. Do not begin implementation merely because the repository exists. |
| `/clarify` | The game idea, player experience, or core loop is still ambiguous | Define the intended player experience, core loop, target player, constraints, assumptions, unknowns, and a falsifiable prototype hypothesis. Record blocking decisions instead of guessing. |
| `/prototype-plan` | The idea is clear enough to define the first playable experiment | Select the smallest testable scope, explicit exclusions, implementation order, success criteria, required evidence, and risks. Avoid production architecture unless it is required by the experiment. |
| `/build-prototype` | The prototype plan has no unresolved critical design ambiguity | Implement the smallest approved playable experiment, keep changes bounded, run available checks, and record concrete blockers or evidence. Do not add unrelated features. |
| `/review-build` | Code or a build exists and needs technical readiness review | Check compilation, launch path, core interaction, obvious runtime blockers, and testability. Record issues and determine whether the build is ready for playtest. |
| `/playtest-review` | A human or accessible test session has produced observations | Separate observed behavior, user-reported feedback, inference, and unknowns. Record evidence with limitations and evaluate the player experience against criteria. |
| `/issue-map` | Findings need to become a prioritized, actionable problem set | Create or update issues, severity, impact, owner, recommended action, links, and decision requirements. Avoid turning every note into critical-path work. |
| `/critical-path` | The project has many possible tasks and needs a short gating path | Identify the few items that actually block the milestone, account for dependencies and unsupported criteria, calculate the path, and state what should not be worked on yet. |
| `/next-step` | The user needs one concrete action now | Select one ready, high-value action from the current state and path. Explain why it is next, what completion means, and which workflow should perform it. |
| `/iterate` | One bounded issue or hypothesis should be improved and rechecked | Make one focused change, verify it, record evidence, update affected issues or criteria, and recalculate the path when state changes make it stale. |
| `/milestone-review` | The current milestone may be complete or needs a formal readiness check | Review required criteria, evidence quality, unresolved blockers, accepted risks, and give a supported readiness recommendation. Do not silently advance the milestone. |
| `/vertical-slice` | Prototype evidence is sufficient for a strategic product decision | Recommend `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP`, with evidence, trade-offs, risks, and a specific next milestone or action. |

The catalog currently maps the workflows into this broad sequence:

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
→ /vertical-slice
```

This is not a mandatory linear pipeline. The current state may legitimately send the agent back to `/clarify`, `/prototype-plan`, `/review-build`, or `/critical-path`.

### Example agent requests

```text
Read AGENTS.md and execute /clarify.
Ask only questions that materially affect the first prototype.
Do not write implementation code during clarification.
```

```text
Read AGENTS.md and execute /prototype-plan.
Create the smallest playable experiment and explicitly list out-of-scope work.
Use studio commands to record decisions, criteria, dependencies, and the critical path.
```

```text
Read AGENTS.md and execute /next-step.
Choose exactly one ready action from the current critical path.
Do not broaden the scope.
```

## 10. Daily workflow

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

Then ask the AI agent to run the recommended workflow:

```text
Read AGENTS.md.
Inspect studio status and the current critical path.
Execute the recommended workflow without expanding scope.
```

The operational loop is:

```text
Inspect current state
→ Run the recommended AI-agent workflow
→ Work on one ready path item
→ Record issues, evidence, and decisions
→ Evaluate affected criteria
→ Check path freshness
→ Recalculate the path
→ Review the milestone
```

Reports under `.studio/reports/` are generated views of canonical JSON. Do not edit reports manually.

## 11. Core CLI command reference

These commands run in PowerShell or another terminal. Use command-specific help before a write:

```powershell
studio --help
studio <command> --help
```

### Project

| Command | Purpose |
| --- | --- |
| `studio bootstrap` | Attach the lightweight scaffold to an empty or existing game repository. |
| `studio init --name "Game Name"` | Initialize or explicitly update project identity. |
| `studio validate` | Validate a bootstrapped game project, schemas, state relationships, and report freshness. |
| `studio status` | Show current phase, milestone, issues, evidence, decisions, criteria, path freshness, and recommended workflow. |
| `studio report` | Regenerate Markdown reports from canonical JSON state. |
| `studio framework validate` | Validate the GameStudioLite framework source repository. Do not use it for a normal game project. |

### Issues

| Command | Purpose |
| --- | --- |
| `studio issue add` | Create a structured issue. |
| `studio issue list` | List or filter issues. |
| `studio issue show ISS-0001` | Show one issue. |
| `studio issue update ISS-0001` | Update status, impact, ownership, links, or resolution. |

### Evidence

| Command | Purpose |
| --- | --- |
| `studio evidence add` | Record observed, user-reported, inferred, or unknown evidence. |
| `studio evidence list` | List or filter evidence. |
| `studio evidence show EVD-0001` | Show one evidence record. |
| `studio evidence update EVD-0001` | Update confidence, limitations, links, lifecycle, or supersession. |

### Decisions

| Command | Purpose |
| --- | --- |
| `studio decision add` | Create a decision with options, trade-offs, and an agent recommendation. |
| `studio decision list` | List or filter decisions. |
| `studio decision show DEC-0001` | Show one decision. |
| `studio decision update DEC-0001` | Update decision metadata, links, options, or recommendation. |
| `studio decision resolve DEC-0001` | Record the user's selected option or custom decision. |

An AI agent's recommended option is guidance. It is not the user's final choice until the decision is explicitly resolved.

### Dependencies

| Command | Purpose |
| --- | --- |
| `studio dependency add` | Create or reactivate an explicit prerequisite relationship. |
| `studio dependency list` | List or filter dependencies. |
| `studio dependency show DEP-0001` | Show one dependency. |
| `studio dependency update DEP-0001` | Update endpoints, reason, scope, or status. |
| `studio dependency deactivate DEP-0001` | Disable a dependency without deleting its history. |

### Milestone criteria

| Command | Purpose |
| --- | --- |
| `studio criterion add` | Add a required or optional milestone criterion. |
| `studio criterion list` | List or filter criteria. |
| `studio criterion show MC-001` | Show one criterion. |
| `studio criterion update MC-001` | Update definition, verification policy, and relationships. |
| `studio criterion evaluate MC-001` | Record explicit support, evidence, reasoning, and limitations. |
| `studio criterion retire MC-001` | Retire a criterion without deleting history. |

Verification policies currently include:

```text
observed-player-behavior
observed-runtime
automated-test
document-review
source-review
manual-approval
mixed
```

Evidence never silently verifies a criterion. The criterion must be explicitly evaluated.

### Critical path

| Command | Purpose |
| --- | --- |
| `studio path calculate` | Calculate the dependency-aware milestone path. |
| `studio path show` | Show current ready, blocked, and excluded path items. |
| `studio path explain CP-0001` | Explain why one item gates the milestone. |
| `studio path check` | Check whether the saved path is stale. |

## 12. Important usage examples

IDs below assume a new sample project. Use the actual ID printed by each add command.

### Add an issue

```powershell
studio issue add `
  --title "Prototype fails to launch" `
  --severity blocker `
  --description "The current build exits before the main scene loads." `
  --milestone-impact "External prototype testing cannot begin." `
  --recommended-action "Reproduce the failure and capture the build log." `
  --yes
```

This records the issue. It does not fix or launch the build.

### Add evidence

```powershell
studio evidence add `
  --title "First tester completed the core loop" `
  --claim "One tester completed the core loop without assistance." `
  --classification observed `
  --source-type human-playtest `
  --description "The developer directly observed the tester in the current build." `
  --confidence medium `
  --limitation "Only one tester has been observed." `
  --yes
```

Use `observed` only for directly accessible events. Unobserved human statements remain `user-reported`.

### Add and resolve a decision

Create two options and an agent recommendation:

```powershell
studio decision add `
  --question "Should the prototype use one lane or three lanes?" `
  --context "Lane count affects pathfinding complexity and tactical counterplay." `
  --option "OPT-A|One lane|Simpler and faster to test." `
  --option "OPT-B|Three lanes|More strategic options but higher complexity." `
  --recommended-option OPT-A `
  --recommendation-reason "One lane isolates the core interaction first." `
  --trade-off "The first prototype will not test lane switching." `
  --status ready `
  --yes
```

The user records the final decision separately:

```powershell
studio decision resolve DEC-0001 `
  --option OPT-A `
  --reason "The owner selected one lane for the first prototype." `
  --consequence "Build and test the one-lane interaction before adding more lanes." `
  --follow-up "Revisit lane count after the first playtest." `
  --yes
```

### Add a dependency

This means `ISS-0003` requires `DEC-0001`:

```powershell
studio dependency add `
  --prerequisite DEC-0001 `
  --dependent ISS-0003 `
  --reason "Implementation depends on the selected lane structure." `
  --yes
```

Terminal does not always mean satisfied. For example, resolved decisions satisfy dependency edges, while rejected, deferred, or superseded decisions do not.

### Add a milestone criterion

```powershell
studio criterion add `
  --description "A new player can complete the core interaction without assistance." `
  --required `
  --completion-condition "Two of three observed testers complete it unaided." `
  --verification-method "Observed human playtest using the current build." `
  --verification-policy observed-player-behavior `
  --yes
```

### Evaluate a criterion

Assuming the criterion is `MC-002` and evidence is `EVD-0001`:

```powershell
studio criterion evaluate MC-002 `
  --support partially-supported `
  --evidence EVD-0001 `
  --reason "One observed tester completed the interaction unaided." `
  --limitation "Two additional observed testers are required." `
  --yes
```

## 13. Dry-run and JSON modes

Dry run validates proposals without writing target files, state, or reports:

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

JSON output is intended for scripts, CI, and integrations. Supported write commands also expose JSON envelopes; inspect their help.

`studio status` currently provides human-readable output only:

```powershell
studio status
```

`studio report` and `studio init` are also human-readable only.

## 14. Multiple-project usage

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

## 15. Updating the framework

For an editable installation:

```powershell
Set-Location F:\Tools\GameStudioLite
git pull
python -m pip install -e ".[dev]"
```

Updating the installed CLI does not automatically upgrade existing project scaffolds. Upgrade and migration commands are not implemented.

Before refreshing managed files in an important game project:

1. Commit or back up project state.
2. Run `studio bootstrap --dry-run`.
3. Review every conflict and proposed update.
4. Use `studio bootstrap --force --yes` only when the managed-file replacement is understood.

Do not run force blindly. There is currently no `studio upgrade` command.

## 16. Validation commands

### In a game project

```powershell
studio validate
```

This validates scaffold, schemas, relationships, and report freshness. It does not require framework source, tests, documentation, package metadata, or CI files.

### In the GameStudioLite framework source repository

```powershell
studio framework validate
```

This additionally validates development files, packaged resources, and scaffold synchronization. It is not intended for normal game repositories.

## 17. Troubleshooting

### `No Practical Game Studio project found`

From the intended game directory:

```powershell
studio bootstrap
```

`studio init` requires an existing scaffold.

### Bootstrap reports a managed-file conflict

Inspect the proposal first:

```powershell
studio bootstrap --dry-run
```

For an understood managed-file replacement:

```powershell
studio bootstrap --force --yes
```

Force does not overwrite protected state or reports.

### The AI agent does not recognize `/start`

Use normal language:

```text
Read AGENTS.md and execute the /start workflow.
```

The alias is a workflow request, not necessarily a native command in the AI client.

### The AI agent does not update `.studio/state`

Tell it explicitly:

```text
Use the supported studio CLI for canonical state mutations.
Do not manually edit .studio/state JSON unless performing documented recovery.
```

### The wrong project is detected

Select the root explicitly:

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

Explicitly update metadata:

```powershell
studio init --force --engine Unity --yes
```

This changes project metadata only. It does not install or control Unity.

### Validation fails after manual JSON edits

Prefer supported commands. After restoring a known-good revision, run:

```powershell
studio validate
studio report
```

See [State mutation safety](docs/state-mutation-safety.md).

## 18. Repository development

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

## 19. Project status and roadmap

### Available now

- Lightweight multi-project bootstrap
- Transactional project state
- AI-agent workflow playbooks
- Issues, evidence, decisions, and dependencies
- Milestone criteria with explicit verification policies
- Dependency-aware critical paths
- Generated reports
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
