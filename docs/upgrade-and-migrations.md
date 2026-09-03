# Upgrade and migrations

A project records the scaffold version it was written for. The installed
`practical-game-studio` package declares the version it can produce. When those
differ, `studio upgrade` carries the project forward — refreshing
framework-managed files and migrating canonical state as one operation.

Force-replacing a project's files is not an upgrade. Those files hold the
project's own issues, decisions, evidence, and history, and that data is the
reason the framework exists.

## Commands

```bash
studio upgrade check           # is an upgrade available?
studio upgrade plan            # what exactly would change?
studio upgrade apply --dry-run # stage and validate, write nothing
studio upgrade apply --yes     # run it
```

All three accept `--root` and `--json`.

`apply` is a structural write: in `guided` or `strict` review mode it asks for
confirmation, and in a non-interactive terminal it requires `--yes`. `fast`
review mode proceeds without asking.

## What `plan` tells you

`studio upgrade plan` prints seven things, and prints a section even when it is
empty — "this upgrade destroys nothing" and "the plan forgot to mention
destruction" must not look the same.

| Section | Meaning |
| --- | --- |
| Source version | The scaffold version the project currently records |
| Target version | The version the installed package produces |
| Migrations | Each version step, in order, with what it does |
| Affected files | Every managed file and state document that would change |
| Destructive changes | Steps that drop information that cannot be reconstructed |
| Manual actions | Work a person must do; the engine never does these |
| Expected compatibility impact | What downstream consumers should expect |

## How an upgrade runs

The order exists so that a bad migration fails while the project is still
untouched:

1. Read the project's scaffold version and resolve the migration chain.
2. Load canonical state and run each migration **in memory**.
3. Stage the packaged framework files into a temporary directory and validate
   the migrated state against those **new** schemas.
4. Stop here if `--dry-run`. Nothing has been written.
5. Snapshot the managed files that will change, then replace them.
6. Write migrated state through `StateTransaction`, which validates again,
   re-renders every report, and replaces files atomically.
7. If anything after step 5 fails, restore the snapshot.

A dry run therefore proves the upgrade would validate — not merely that it would
run.

## Version resolution rules

- A version the installed package does not know is an error, not a no-op.
- A project newer than the installed package is an error: the fix is to upgrade
  `practical-game-studio`, never to downgrade the project.
- A project already at the target reports success and changes nothing, so
  `studio upgrade apply` is safe to run repeatedly.

## Writing a migration

Registering a migration is the only supported way to change the shape of
canonical state. A release that changes state without one leaves existing
projects unupgradeable.

1. Add `src/practical_game_studio/migrations/migration_NNN.py` exporting a
   `MIGRATION` constant.
2. Give it `from_version` / `to_version` that continue the chain with no gap.
3. Write `migrate(state) -> state` as a **pure** function of canonical state. It
   must not touch the filesystem — the engine owns staging, validation, and
   rollback, and a migration that wrote to disk could not be dry-run.
4. Make it idempotent: re-running it on already-migrated state returns that
   state unchanged.
5. Register it in `migrations/registry.py`, bump `SCAFFOLD_VERSION` in
   `scaffold.py`, and update the packaged schemas and seed state to match.
6. Describe `manual_actions`, `destructive`, and `compatibility_impact`
   honestly. These are what a person reads before agreeing to the upgrade.

## Registered migrations

| Step | Versions | What it does |
| --- | --- | --- |
| `001` | 1.0 → 1.1 | Stores the recommended next workflow as a workflow id (`start`) rather than a slash alias (`/start`) |
| `002` | 1.1 → 1.2 | Adds `MS-####` milestone ids and a milestone registry so references survive a title rename |
