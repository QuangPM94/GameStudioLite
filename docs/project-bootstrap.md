# Project Bootstrap

`studio bootstrap` attaches Practical Game Studio to an empty directory or an
existing game repository. The Python runtime stays in the installed
`practical-game-studio` package; the game owns only `AGENTS.md` and `.studio/`.

## Typical use

```powershell
cd F:\Games\MidnightCarrier
studio bootstrap
studio init --name "Midnight Carrier"
studio validate
```

Bootstrap and identity initialization may be combined:

```powershell
studio bootstrap `
  --name "Midnight Carrier" `
  --engine Unity `
  --platform Windows `
  --review-mode guided
```

Use `--root PATH` when the target is not the current directory. Bootstrap does
not run normal project discovery first, because it is responsible for creating
the markers discovery needs.

## Managed and protected paths

Replaceable framework files are:

- `AGENTS.md`
- `.studio/config.json`
- `.studio/framework.json`
- `.studio/workflow-catalog.json`
- `.studio/roles/`
- `.studio/playbooks/`
- `.studio/schemas/`
- `.studio/templates/`

Project-specific `.studio/state/` and `.studio/reports/` files are protected.
Existing protected files are never replaced by ordinary force bootstrap.
Missing seed files may be created only when the complete staged project
validates.

Unrelated files—including `Assets/`, `Packages/`, `ProjectSettings/`,
`project.godot`, `*.uproject`, `Source/`, `Content/`, README files,
`.gitignore`, `.git/`, and `.github/`—are not managed and are never copied from
the framework or overwritten.

## Conflicts and force

If an existing replaceable file differs from the packaged scaffold, bootstrap
reports every conflicting path and writes nothing. Review the difference first.
Use `--force --yes` to replace only framework-managed files in a
non-interactive terminal. Dry runs do not require confirmation.

```powershell
studio bootstrap --dry-run
studio bootstrap --force --yes
```

Running bootstrap again on an unchanged project is a successful no-op. It
does not rewrite timestamps, regenerate reports, consume IDs, or change state.

## Root discovery and validation

A project root has a valid `.studio/config.json`, `.studio/framework.json`, and
`.studio/state/`. `AGENTS.md` remains a required validated scaffold file but is
not the sole root marker. Commands work from nested directories and accept
`--root PATH`.

`studio validate` checks only game-project scaffold files, schemas,
relationships, and report freshness. `studio framework validate` is reserved
for the GameStudioLite source repository and additionally checks source, tests,
docs, package metadata, resource availability, and scaffold synchronization.

## Safety and current limitations

Bootstrap calculates the entire plan, stages it in a temporary sibling tree,
validates it, rechecks target hashes, and replaces managed files with rollback.
It never creates a nested Git repository. This is a practical local multi-file
safety protocol, not database ACID.

C2.2 does not implement scaffold upgrades, schema migration, phase or milestone
transitions, workflow execution, engine project creation/editor control, media
or telemetry ingestion, autonomous implementation, or multi-agent
orchestration.
