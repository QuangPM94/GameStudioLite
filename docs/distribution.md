# Distribution

Practical Game Studio is installed once as a Python CLI and attached to any
number of independent game repositories. Runtime code comes from the installed
package; game repositories contain only the lightweight scaffold and their own
state.

## Editable installation

For framework development or a local tools checkout:

```powershell
python -m pip install -e "F:\Tools\GameStudioLite[dev]"

New-Item -ItemType Directory F:\Games\GameA
Set-Location F:\Games\GameA
studio bootstrap
studio init --name "Game A"
```

The same executable may then bootstrap `GameB` and `GameC`. Their project
identities, issues, evidence, decisions, dependencies, criteria, critical
paths, and reports remain independent.

## Wheel installation

Build the distribution from the GameStudioLite source repository:

```powershell
python -m build
python -m venv .tmp-pgs-wheel-test
.tmp-pgs-wheel-test\Scripts\python -m pip install `
  dist\practical_game_studio-0.1.0-py3-none-any.whl
```

Test the installed CLI outside the source checkout:

```powershell
New-Item -ItemType Directory .tmp-game
Push-Location .tmp-game
..\.tmp-pgs-wheel-test\Scripts\studio bootstrap
..\.tmp-pgs-wheel-test\Scripts\studio init --name "Wheel Test Game"
..\.tmp-pgs-wheel-test\Scripts\studio validate
Pop-Location
```

The wheel declares every scaffold resource explicitly as package data,
including the hidden `.studio/` tree. `importlib.resources` resolves those
files for editable and wheel installations without hard-coded checkout paths.

## Installed tool versus project data

The installed distribution owns:

- `practical_game_studio` Python runtime modules
- the canonical seed under
  `practical_game_studio/scaffold/`
- the `studio` console entry point

Each game project owns:

- `AGENTS.md`
- `.studio/config.json`
- `.studio/framework.json`
- catalog, roles, playbooks, schemas, templates
- canonical state and generated reports

A game project does not need framework source, tests, development docs,
examples, package metadata, or GameStudioLite CI. Bootstrap never copies
`.git/` or `.github/` and never creates a nested repository.

## Synchronization and future upgrades

The packaged scaffold is the canonical seed. `studio framework validate`
checks package-resource availability and compares root framework-managed
dogfood files by deterministic SHA-256. Live dogfood state and reports are
validated for schema, relationships, and freshness rather than forced back to
seed bytes.

`.studio/framework.json` records scaffold version, installed package version,
bootstrap timestamp, and managed paths without machine-specific installation
locations. C2.2 uses it for ownership and conflict detection. It does not
implement scaffold upgrades or state-schema migrations; those require a future
explicit migration command with version-aware preservation rules.
