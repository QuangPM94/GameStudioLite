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
- [5. Open a game project in an AI agent](#5-open-a-game-project-in-an-ai-agent)
- [6. Manage GameStudioLite through an AI agent](#6-manage-gamestudiolite-through-an-ai-agent)
- [7. AI-agent workflow commands](#7-ai-agent-workflow-commands)
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
→ Execute GS:start
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

The AI agent does not need a native slash-command system. The canonical way to request a workflow is plain text such as `GS:clarify` (see [section 6](#6-manage-gamestudiolite-through-an-ai-agent)); a legacy `/clarify` alias also remains supported. When the agent does not recognize either form natively, use normal language:

```text
Read AGENTS.md and execute the GS:clarify workflow.
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

## 5. Open a game project in an AI agent

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
GS:start
```

This is plain text, so it works whether or not the AI client has native slash-command handling. The fully spelled-out request below is equally valid and preferred over the legacy `/start` alias:

```text
Read AGENTS.md and execute the GS:start workflow.
```

See [section 6](#6-manage-gamestudiolite-through-an-ai-agent) for the full `GS:<workflow>` syntax.

### Agent execution contract

A compatible AI agent should:

1. Read the root `AGENTS.md`.
2. Read `.studio/workflow-catalog.json`.
3. Read the playbook for the requested workflow.
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
Execute the GS:start workflow and report the recommended next workflow.
```

## 6. Manage GameStudioLite through an AI agent

Most day-to-day use of GameStudioLite should go through an AI agent, not through hand-typed CLI commands. The agent turns a short workflow request into the long, exact `studio` invocation, and the CLI stays the only thing that ever validates or writes canonical state:

```text
User instruction
→ AI-agent workflow (playbook in .studio/playbooks/)
→ studio CLI (studio issue/evidence/decision/criterion/dependency/path/validate/report)
→ validated canonical state (.studio/state/*.json)
→ reports and critical path (.studio/reports/, studio path show)
```

What this means in practice:

- Users normally interact with the AI agent, in plain language or with a workflow command such as `GS:report-issue`.
- The AI agent constructs and runs the long CLI commands; the user does not need to remember flags like `--verification-policy` or `--exclude-reason`.
- The `studio` CLI remains the trusted state-mutation and validation layer. No workflow edits `.studio/state/*.json` directly, and no workflow invents its own mutation logic — it only calls the same supported commands documented in [section 9](#9-core-cli-command-reference).
- `GS:<workflow>` commands are workflow instructions interpreted through `AGENTS.md`, not native slash commands guaranteed to exist inside every AI client.

### Canonical invocation syntax: `GS:<workflow>`

`GS:<workflow>` is the canonical, official syntax for requesting a workflow — for example `GS:clarify`, `GS:report-issue`, `GS:critical-path`. It is:

- **Uppercase `GS`, one colon, lowercase kebab-case workflow name.** `GS:report-issue`, not `gs:report-issue`, `GS: report-issue`, or `GS::report-issue`.
- **Plain text**, not a slash command, an `@` mention, or any other client-reserved prefix. That is deliberate: some AI clients intercept a leading `/` as their own client-level slash command, and some reserve a leading `@` for mentions, which can prevent those characters from ever reaching the agent as normal text. `GS:` is ordinary text, so it reaches the agent unmodified and works the same across chat UIs, IDE extensions, and terminal sessions.
- **Recognized as the first non-whitespace text of a message.** Leading/trailing whitespace around the command is fine; everything after that first line is the workflow's input, for example:

  ```text
  GS:report-issue

  Defender can place two towers in the same build slot after selling a tower.
  Record this issue and tell me whether it affects the current milestone.
  ```

- **Never guessed.** If the text after `GS:` is not a recognized workflow id (or the command is malformed, such as `GS:` with nothing after it, or `GS:/clarify` with a stray slash), the agent reports that it does not recognize the command and lists the valid `GS:<workflow>` commands instead of picking one.

Existing `/<workflow>` slash aliases (`/clarify`, `/report-issue`, and so on) remain supported as **legacy aliases** for backward compatibility, and plain language always works:

```text
Read AGENTS.md and execute the GS:report-issue workflow.
```

Native slash-command registration inside a specific AI product is never required for any of this to work.

### Resume an existing project

Opening a new chat or agent session does **not** mean restarting the project. The project state already lives under `.studio/state/`; the agent should inspect it and continue from the current phase, milestone, decisions, criteria, issues, evidence, dependencies, and critical path.

```text
GS:resume
```

`GS:resume` (read-only):

1. Runs or inspects `studio status`, `studio path check`, and `studio path show`.
2. Never runs `studio bootstrap` or `studio init` as part of a normal resume.
3. Never resets phase, milestone, issues, decisions, evidence, dependencies, criteria, reports, or history.
4. Names the exact next workflow and the current ready critical-path item.
5. If the path is stale, says so plainly and recommends `GS:critical-path` instead of silently recalculating it.

Run `studio bootstrap` or `studio init` only when GameStudioLite has not yet been attached to the project, identity must be explicitly corrected, or a managed scaffold refresh has been reviewed and intentionally approved — never as part of a normal resume.

`GS:start` serves a related but distinct purpose: it must not reset an existing project either, but it is for new, unknown, uninitialized, or intake-stage projects, not for continuing one that is already initialized. Use `GS:resume` for a new AI-agent session on an existing, already-initialized project; use `GS:start` when the project is new, unknown, uninitialized, or still in intake.

### User-facing commands

| Command | Legacy alias | When to use it | Read-only or write | Records it may create/update |
| --- | --- | --- | --- | --- |
| `GS:resume` | `/resume` | Opening a new AI-agent session on an existing project | Read-only | None |
| `GS:project-status` | `/project-status` | Getting a snapshot of direction without changing anything | Read-only | None |
| `GS:report-issue` | `/report-issue` | Recording a bug, blocker, or risk from a report, review, or failure | Writes state | One issue (`ISS-####`) |
| `GS:record-evidence` | `/record-evidence` | Recording a claim and its source (observed, user-reported, inferred, or unknown) | Writes state | One evidence record (`EVD-####`) |
| `GS:decision` | `/decision` | Creating, refining, or resolving a meaningful project decision | Writes state | One decision (`DEC-####`) |
| `GS:milestone-criteria` | `/milestone-criteria` | Defining, updating, evaluating, or retiring milestone success criteria | Writes state | One or more criteria (`MC-###`) |
| `GS:critical-path` | `/critical-path` | Recalculating the short list of work that actually gates the milestone | Writes state | The active critical path and its history |
| `GS:next-step` | `/next-step` | Picking exactly one ready, high-value action right now | Read-only | None |

Example requests:

```text
GS:report-issue

Defender can place two towers in the same build slot after selling a tower.
Record this issue and tell me whether it affects the current milestone.
```

```text
GS:record-evidence

I tested the Android build. Three units reached the Core, but the third unit
paused for about one second. Record this as user-reported evidence.
```

```text
GS:decision

Create a decision for whether the first prototype should use one lane or three
lanes. Compare the options, but do not resolve it for me.
```

```text
GS:milestone-criteria

Create the required success criteria for the first offline Defender-versus-
Attacker prototype.
```

```text
GS:project-status

Summarize the current milestone, blockers, unsupported criteria, and next
critical-path item.
```

An agent recommendation is guidance, not the user's final choice. `GS:decision` only resolves a decision after the user explicitly selects an option or states an explicit custom decision; `GS:milestone-criteria` only marks a criterion verified after an explicit evaluation, never because supporting evidence merely exists. `GS:report-issue` records a problem; `GS:record-evidence` records support for a claim — they are not interchangeable.

### Direct CLI use remains available

The AI-agent layer is an orchestration convenience, not a replacement for the CLI. Use `studio` commands directly for:

- Automation and scripts
- CI pipelines
- Debugging and recovery
- Advanced or manual operation (for example custom `studio path calculate --include`/`--exclude` scopes)
- AI agents without terminal integration, where a human runs the printed commands and reports the output back

## 7. AI-agent workflow commands

These workflows are available to any compatible AI agent. They are not PowerShell commands. Each has a canonical `GS:<workflow>` form (see [section 6](#6-manage-gamestudiolite-through-an-ai-agent)) and a legacy `/<workflow>` alias kept for backward compatibility.

### Phase workflows

These follow the milestone pipeline and belong to one phase each.

| Canonical | Legacy alias | Use it when | What the AI agent should do |
| --- | --- | --- | --- |
| `GS:start` | `/start` | Opening a new session or inspecting a project | Inspect repository, engine indicators, current state, build status, phase, milestone, blockers, and critical path; then route to the correct next workflow. It must not reset an existing project. |
| `GS:clarify` | `/clarify` | The game idea, player experience, or core loop is ambiguous | Define intended player experience, core loop, target player, constraints, assumptions, unknowns, and a falsifiable prototype hypothesis. Record blocking decisions instead of guessing. |
| `GS:prototype-plan` | `/prototype-plan` | The idea is clear enough to define the first playable experiment | Select the smallest testable scope, explicit exclusions, implementation order, success criteria, evidence requirements, and risks. Avoid production architecture unless required by the experiment. |
| `GS:build-prototype` | `/build-prototype` | The prototype plan has no unresolved critical design ambiguity | Implement the smallest approved playable experiment, keep changes bounded, run available checks, and record concrete blockers or evidence. Do not add unrelated features. |
| `GS:review-build` | `/review-build` | Code or a build needs technical readiness review | Check compilation, launch path, core interaction, obvious runtime blockers, and testability. Record issues and determine whether the build is ready for playtest. |
| `GS:playtest-review` | `/playtest-review` | A human or accessible test session produced observations | Separate observed behavior, user-reported feedback, inference, and unknowns. Record evidence with limitations and evaluate the experience against criteria. |
| `GS:issue-map` | `/issue-map` | Findings must become a prioritized problem set | Create or update issues, severity, impact, owner, recommended action, links, and decision requirements. Avoid placing every note on the critical path. |
| `GS:iterate` | `/iterate` | One bounded issue or hypothesis should be improved and rechecked | Make one focused change, verify it, record evidence, update affected issues or criteria, and recalculate the path when state changes make it stale. |
| `GS:milestone-review` | `/milestone-review` | The current milestone may be complete | Review required criteria, evidence quality, unresolved blockers, and accepted risks. Give a supported readiness recommendation without silently advancing the milestone. |
| `GS:vertical-slice` | `/vertical-slice` | Prototype evidence supports a strategic product decision | Recommend `PROCEED`, `ITERATE`, `PIVOT`, `PAUSE`, or `STOP`, with evidence, trade-offs, risks, and a specific next milestone or action. |

### Cross-phase workflows

These are utility commands usable in any phase; the catalog does not force them into a single phase. See [section 6](#6-manage-gamestudiolite-through-an-ai-agent) for full read/write and record details.

| Canonical | Legacy alias | Use it when | What the AI agent should do |
| --- | --- | --- | --- |
| `GS:resume` | `/resume` | Opening a new AI-agent session on an existing project | Inspect current state and the critical path, then route to the exact next workflow. Never resets state; never runs bootstrap/init as part of a normal resume. |
| `GS:project-status` | `/project-status` | A read-only summary of direction is needed | Summarize phase, milestone, build status, blockers, pending decisions, unsupported criteria, and path freshness without changing anything. |
| `GS:report-issue` | `/report-issue` | A concrete problem was found | Search for a duplicate, record severity/category/impact/owner as a proposal or confirmed fact, and create or update exactly one issue. |
| `GS:record-evidence` | `/record-evidence` | A claim needs its source recorded | Classify the claim as observed, user-reported, inferred, or unknown, record confidence/limitations, and create or update exactly one evidence record. |
| `GS:decision` | `/decision` | A meaningful choice needs options and trade-offs | Define the question, options, and trade-offs; recommend one option without resolving it; resolve only after the user's explicit choice. |
| `GS:milestone-criteria` | `/milestone-criteria` | Milestone success criteria need defining or checking | Require a completion condition and explicit verification policy; evaluate only with an explicit support status, never from evidence existence alone. |
| `GS:critical-path` | `/critical-path` | The project has many possible tasks and needs a short gating path | Identify the few items that actually block the milestone, account for dependencies and unsupported criteria, calculate the path, and state what should not be worked on yet. |
| `GS:next-step` | `/next-step` | The user needs one concrete action now | Select one ready, high-value action from current state and critical path. Explain why it is next, what completion means, and which workflow should perform it. |

Broad phase workflow sequence:

```text
GS:start
→ GS:clarify
→ GS:prototype-plan
→ GS:build-prototype
→ GS:review-build
→ GS:playtest-review
→ GS:issue-map
→ GS:critical-path
→ GS:next-step
→ GS:iterate
→ GS:milestone-review
→ GS:vertical-slice
```

This is not a mandatory linear pipeline. Current state may legitimately send the agent back to `GS:clarify`, `GS:prototype-plan`, `GS:review-build`, or `GS:critical-path`.

Example requests:

```text
Read AGENTS.md and execute GS:clarify.
Ask only questions that materially affect the first prototype.
Do not write implementation code during clarification.
```

```text
Read AGENTS.md and execute GS:prototype-plan.
Create the smallest playable experiment and explicitly list out-of-scope work.
Use studio commands to record decisions, criteria, dependencies, and the critical path.
```

```text
Read AGENTS.md and execute GS:next-step.
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

Give the agent the `GS:resume` guidance from [Manage GameStudioLite through an AI agent](#6-manage-gamestudiolite-through-an-ai-agent).

Explicitly state:

```text
The GS:start workflow means inspect and route the existing project.
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
