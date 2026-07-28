# GameStudioLite

GameStudioLite is a lightweight, project-local control framework for AI-assisted game development. It keeps goals, blockers, evidence, decisions, milestone criteria, and the next action visible while a repository-aware AI agent helps plan, build, review, and iterate on a game.

GameStudioLite is **not tied to Codex**. Any compatible AI agent can use it when the agent can:

- Open the game repository
- Read the project-local `AGENTS.md`
- Read files under `.studio/`
- Run the installed `studio` CLI, or ask the user to run it
- Follow explicit workflow instructions
- Preserve the user's final decision authority

GameStudioLite currently manages:

- Project identity and state
- Issues
- Evidence
- Decisions
- Explicit dependencies
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

- [1. Overview](#1-overview)
- [2. Requirements](#2-requirements)
- [3. Install GameStudioLite](#3-install-gamestudiolite)
- [4. Attach GameStudioLite to a game](#4-attach-gamestudiolite-to-a-game)
- [5. Use GameStudioLite with an AI agent](#5-use-gamestudiolite-with-an-ai-agent)
- [6. Resume in a new AI-agent session](#6-resume-in-a-new-ai-agent-session)
- [7. AI-agent workflow aliases](#7-ai-agent-workflow-aliases)
- [8. Daily workflow](#8-daily-workflow)
- [9. Core CLI command reference](#9-core-cli-command-reference)
- [10. Important usage examples](#10-important-usage-examples)
- [11. Dry-run and JSON modes](#11-dry-run-and-json-modes)
- [12. Multiple projects](#12-multiple-projects)
- [13. Updating GameStudioLite](#13-updating-gamestudiolite)
- [14. Validation](#14-validation)
- [15. Troubleshooting](#15-troubleshooting)
- [16. Framework development](#16-framework-development)
- [17. Project status and roadmap](#17-project-status-and-roadmap)

## 1. Overview

GameStudioLite gives an AI agent a stable control layer instead of relying on loose chat history.

The installed `studio` CLI provides runtime and state-management commands. Each game repository owns a lightweight scaffold:

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

Every project has independent state, reports, and ID sequences. Game A and Game B may both contain `ISS-0001`; neither record affects the other.

The first-run flow is:

```text
Install GameStudioLite once
→ Open or create a game project
→ Bootstrap GameStudioLite into that project
→ Validate project state
→ Calculate the first critical path
→ Open the game repository in an AI agent
→ Ask the agent to read AGENTS.md
→ Execute /start
```

Current capabilities:

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

## 2. Requirements

- Python 3.11 or newer
- Git
- A game directory, empty or containing an existing engine project
- An AI agent that can read repository files and, ideally, run terminal commands

PowerShell is used for Windows examples. Bash may use the equivalent commands.

The AI agent does not need a native slash-command system. Inputs such as `/clarify` are workflow aliases. When the agent does not recognize them natively, use normal language:

```text
Read AGENTS.md and execute the /clarify workflow.
```

Unity, Godot, and Unreal are not GameStudioLite requirements. Install an engine only when the game uses it.

## 3. Install GameStudioLite

### Editable installation

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

Install the newest generated wheel:

```powershell
$wheel = Get-ChildItem .\dist\*.whl |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

python -m pip install $wheel.FullName
```

The wheel contains the runtime and packaged scaffold. A game project does not need the framework source checkout after installation.

See [Distribution](docs/distribution.md).

## 4. Attach GameStudioLite to a game

### Existing game project

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

Validate and calculate the initial path:

```powershell
studio validate
studio status
studio path calculate --yes
studio path show
```

Bootstrap creates only the GameStudioLite control layer. It does not replace unrelated engine or project content such as:

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

### Empty directory

```powershell
New-Item -ItemType Directory F:\Games\NewGame
Set-Location F:\Games\NewGame

studio bootstrap `
  --name "New Game" `
  --platform Windows
```

This creates and initializes the GameStudioLite scaffold. It does not create an engine project, executable, scene, or asset.

### Bootstrap and identity separately

Use one step when project identity is known:

```powershell
studio bootstrap `
  --name "My Game" `
  --engine Unity `
  --platform Mobile `
  --genre "Strategy"
```

Use two steps when identity will be supplied later:

```powershell
studio bootstrap

studio init `
  --name "My Game" `
  --engine Unity `
  --platform Mobile
```

Repeating `studio init` is a no-op unless explicitly supplied fields are changed with `--force`.

## 5. Use GameStudioLite with an AI agent

Open the **game repository**, not the GameStudioLite framework repository, as the agent's active workspace.

```text
Open:
F:\Games\MyGame

Do not use as the active game project:
F:\Tools\GameStudioLite
```

The game repository contains:

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
10. Finish with current direction, evidence, unknowns, critical path, and the recommended next workflow.

Generic first-session prompt:

```text
Read AGENTS.md and the requested workflow playbook.
Inspect current project state before acting.
Use the supported studio CLI for state changes.
Do not invent evidence or silently make final user decisions.
Execute the /start workflow and report the recommended next workflow.
```

## 6. Resume in a new AI-agent session

Opening a new chat or agent session does **not** mean restarting the project.

The project state already lives under `.studio/state/`. The agent should inspect that state and continue from the current phase, milestone, decisions, criteria, issues, evidence, dependencies, and critical path.

Use this prompt whenever a new AI-agent session begins:

```text
Read AGENTS.md and resume this project from its current state.

Run or inspect:
- studio status
- studio path check
- studio path show

Do not run studio bootstrap or studio init.
Do not reset project state, phase, milestone, issues, evidence, decisions, dependencies, criteria, or reports.
The /start workflow means inspect and route the current project, not restart it from the beginning.

Identify the current ready critical-path item.
Then execute or recommend the exact next workflow without expanding scope.
Use the supported studio CLI for all state mutations.
```

An agent with terminal access should run:

```powershell
studio status
studio path check
studio path show
```

When the path is stale:

```powershell
studio path calculate --dry-run
studio path calculate --yes
studio path show
```

An agent without terminal access should ask the user to run those commands and provide their output.

### Do not run these during a normal resume

```powershell
studio bootstrap
studio init
```

Use them only when:

- GameStudioLite has not yet been attached to the project
- Project identity must be explicitly corrected or updated
- A managed scaffold refresh has been reviewed and intentionally approved

### What `/start` means in an existing project

In an existing project, `/start` should:

1. Inspect the repository and current state.
2. Check the current phase and milestone.
3. Check critical-path freshness.
4. Identify blockers and pending decisions.
5. Select or recommend the correct next workflow.
6. Continue from the current state without clearing history.

It should not repeat intake automatically when the project has already progressed beyond intake.

## 7. AI-agent workflow aliases

These workflows are available to any compatible AI agent. They are not PowerShell commands.

| Workflow | Use it when | What the AI agent should do |
| --- | --- | --- |
| `/start` | Opening a new session or inspecting a project | Inspect repository, engine indicators, current state, build status, phase, milestone, blockers, and critical path; then route to the correct next workflow. It must not reset an existing project. |
| `/clarify` | The game idea, player experience, or core loop is ambiguous | Define intended player experience, core loop, target player, constraints, assumptions, unknowns, and a falsifiable prototype hypothesis. Record blocking decisions instead of guessing. |
| `/prototype-plan` | The idea is clear enough to define the first playable experiment | Select the smallest testable scope, explicit exclusions, implementation order, success criteria, evidence requirements, and risks. Avoid production architecture unless required by the experiment. |
| `/build-prototype` | The prototype plan has no unresolved critical design ambiguity | Implement the smallest approved playable experiment, keep changes bounded, run available checks, and record concrete blockers or evidence. Do not add unrelated features. |
| `/review-build` | Code or a build needs technical readiness review | Check compilation, launch path, core interaction, obvious runtime blockers, and testability. Record issues and determine whether the build is ready for playtest. |
| `/playtest-review` | A human or accessible test session produced observations | Separate observed behavior, user-reported feedback, inference, and unknowns. Record evidence with limitations and evaluate the experience against criteria. |
| `/issue-map` | Findings must become a prioritized problem set | Create or update issues, severity, impact, owner, recommended action, links, and decision requirements. Avoid placing every note on the critical path. |
| `/critical-path` | The project has many possible tasks and needs a short gating path | Identify the few items that actually block the milestone, account for dependencies and unsupported criteria, calculate the path, and state what should not be worked on yet. |
| `/next-step` | The user needs one concrete action now | Select one ready, high-value action from current state and critical path. Explain why it is next, what completion means, and which workflow should perform it. |
| `/iterate` | One bounded issue or hypothesis should be improved and rechecked | Make one focused change, verify it, record evidence, update affected issues or criteria, and recalculate the path when state changes make it stale. |
| `/milestone-review` | The current milestone may be complete | Review required criteria, evidence quality, unresolved blockers, and accepted risks. Give a supported readiness recommendation without silently advancing the milestone. |
| `/vertical-slice` | Prototype evidence supports a strategic product decision | Recommend `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP`, with evidence, trade-offs, risks, and a specific next milestone or action. |

Broad workflow sequence:

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

This is not a mandatory linear pipeline. Current state may legitimately send the agent back to `/clarify`, `/prototype-plan`, `/review-build`, or `/critical-path`.

Example requests:

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

## 8. Daily workflow

Read current direction:

```powershell
studio status
studio path check
studio path show
```

When the path is stale:

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

A normal loop is:

```text
Inspect current state
→ Work on the recommended path item
→ Record issues, evidence, and decisions
→ Evaluate criteria
→ Check path freshness
→ Recalculate the path
→ Review the milestone
```

Reports under `.studio/reports/` are generated views of canonical JSON. Do not edit them manually.

## 9. Core CLI command reference

Use command-specific help before a write:

```powershell
studio --help
studio issue add --help
studio criterion evaluate --help
studio path calculate --help
```

### Project

```powershell
studio bootstrap
studio init --name "Game Name"
studio validate
studio status
studio report
studio framework validate
```

- `bootstrap`: attach the GameStudioLite scaffold to a game directory
- `init`: initialize or explicitly update project identity
- `validate`: validate a bootstrapped game project
- `status`: show current direction and recommended action
- `report`: regenerate Markdown reports from canonical JSON
- `framework validate`: validate the GameStudioLite source repository; not for normal game projects

### Issues

```powershell
studio issue add --help
studio issue list
studio issue show ISS-0001
studio issue update ISS-0001 --status acknowledged
```

Issues represent bugs, blockers, risks, or actionable problems.

### Evidence

```powershell
studio evidence add --help
studio evidence list
studio evidence show EVD-0001
studio evidence update EVD-0001 --confidence high --yes
```

Evidence records observed, user-reported, inferred, or unknown support for a claim.

### Decisions

```powershell
studio decision add --help
studio decision list
studio decision show DEC-0001
studio decision update DEC-0001 --urgency blocking --yes
studio decision resolve DEC-0001 --option OPT-B --reason "The owner selected this option." --yes
```

An AI recommendation is guidance. `decision resolve` records the owner's actual choice.

### Dependencies

```powershell
studio dependency add --help
studio dependency list
studio dependency show DEP-0001
studio dependency update DEP-0001 --reason "Updated execution-order rationale." --yes
studio dependency deactivate DEP-0001 --reason "The dependency no longer applies." --yes
```

Dependencies describe explicit prerequisite relationships.

### Milestone criteria

```powershell
studio criterion add --help
studio criterion list
studio criterion show MC-001
studio criterion update MC-001 --verification-method "Review the approved project brief." --yes
studio criterion evaluate --help
studio criterion retire MC-001 --reason "The milestone requirement changed." --yes
```

Criteria define what must be demonstrated before a milestone is considered ready.

### Critical path

```powershell
studio path calculate --dry-run
studio path calculate --yes
studio path show
studio path explain CP-0001
studio path check
```

The critical path is a short list of milestone-gating work, not a complete backlog.

## 10. Important usage examples

IDs below assume a new project. Use the actual ID printed by each command.

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

This records the issue. It does not fix or launch the build.

### Add evidence

```powershell
studio evidence add `
  --title "First tester completed one gameplay loop" `
  --claim "One tester completed the gameplay loop without assistance." `
  --classification observed `
  --source-type human-playtest `
  --description "The developer directly observed the test session." `
  --confidence medium `
  --limitation "Only one tester has been observed." `
  --yes
```

Use `observed` only for directly accessible events. Unobserved human statements remain `user-reported`.

### Add and resolve a decision

```powershell
studio decision add `
  --question "Should the first prototype use one lane or three lanes?" `
  --context "Lane count affects pathfinding, balance, and prototype scope." `
  --option "OPT-A|One lane|Smallest implementation and easiest core-loop test." `
  --option "OPT-B|Three lanes|More tactical choice but greater implementation risk." `
  --recommended-option OPT-A `
  --recommendation-reason "One lane is sufficient to test the first interaction." `
  --status ready `
  --yes
```

Record the owner's final choice separately:

```powershell
studio decision resolve DEC-0001 `
  --option OPT-A `
  --reason "The owner selected one lane for the first prototype." `
  --consequence "Implement only one lane in the initial experiment." `
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

### Add a criterion

```powershell
studio criterion add `
  --description "A new player can complete one gameplay loop without assistance." `
  --required `
  --completion-condition "Two of three observed testers complete the loop unaided." `
  --verification-method "Observed human playtest using the current build." `
  --verification-policy observed-player-behavior `
  --yes
```

### Evaluate a criterion

```powershell
studio criterion evaluate MC-002 `
  --support partially-supported `
  --evidence EVD-0001 `
  --reason "One observed tester completed the loop unaided." `
  --limitation "Two additional observed testers are required." `
  --yes
```

Evidence never silently verifies a criterion. Record an explicit evaluation.

## 11. Dry-run and JSON modes

Dry run validates proposals without writing files, state, or reports:

```powershell
studio bootstrap --dry-run
studio init --dry-run
studio issue add --dry-run
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

`studio status`, `studio report`, and `studio init` currently provide human-readable output only.

## 12. Multiple projects

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

## 13. Updating GameStudioLite

For an editable installation:

```powershell
Set-Location F:\Tools\GameStudioLite
git pull origin main
python -m pip install -e ".[dev]"
```

Updating the CLI does not automatically upgrade existing project scaffolds. Upgrade and migration commands are not implemented.

Before refreshing managed files in an important project:

1. Commit or back up project state.
2. Run `studio bootstrap --dry-run`.
3. Review every conflict and proposed update.
4. Use `studio bootstrap --force --yes` only when the replacement is understood.

Do not run force blindly. There is currently no `studio upgrade` command.

## 14. Validation

Inside a normal game project:

```powershell
studio validate
```

Inside the GameStudioLite framework source repository:

```powershell
studio framework validate
```

Framework validation also checks development files, packaged resources, and scaffold synchronization. It is not intended for normal game repositories.

## 15. Troubleshooting

### `No Practical Game Studio project found`

From the intended game directory:

```powershell
studio bootstrap
```

`studio init` requires an existing scaffold.

### Bootstrap reports a managed-file conflict

Inspect conflicts first:

```powershell
studio bootstrap --dry-run
```

For an understood managed-file replacement:

```powershell
studio bootstrap --force --yes
```

Force does not overwrite protected state or reports.

### The wrong project is detected

```powershell
studio status --root F:\Games\CorrectGame
```

### The critical path is stale

```powershell
studio path check
studio path calculate --dry-run
studio path calculate --yes
```

### The engine was not detected

```powershell
studio init --force --engine Unity --yes
```

This changes metadata only. It does not install or control Unity.

### A new AI-agent session starts from the beginning

Give the agent the resume prompt from [Resume in a new AI-agent session](#6-resume-in-a-new-ai-agent-session).

Explicitly state:

```text
The /start workflow means inspect and route the existing project.
Do not reset state or repeat completed intake work.
```

### Validation fails after manual JSON edits

Prefer supported commands instead of editing canonical JSON manually. Restore a known-good revision when necessary, then run:

```powershell
studio validate
studio report
```

See [State mutation safety](docs/state-mutation-safety.md).

## 16. Framework development

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

## 17. Project status and roadmap

### Available now

- Lightweight multi-project bootstrap
- Transactional project state
- AI-agent workflow playbooks
- Issues, evidence, decisions, and dependencies
- Milestone criteria with explicit verification policies
- Dependency-aware critical path
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

No dates are promised.

## Further documentation

[Bootstrap](docs/project-bootstrap.md) ·
[Distribution](docs/distribution.md) ·
[Issues](docs/issue-management.md) ·
[Evidence](docs/evidence-management.md) ·
[Decisions](docs/decision-management.md) ·
[Dependencies](docs/dependency-management.md) ·
[Criteria](docs/milestone-criteria-management.md) ·
[Critical path](docs/critical-path-engine.md) ·
[Mutation safety](docs/state-mutation-safety.md)

## License and attribution

GameStudioLite uses the [MIT License](LICENSE). Architectural patterns were adapted from the MIT-licensed [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
