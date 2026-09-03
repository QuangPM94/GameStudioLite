# Sprint 0 Baseline

Recorded before execution-layer work begins (backlog item **S0.1**). Every value here is
the reference point that later sprints must not silently break.

## How to reproduce

```bash
PYTHONPATH=src python -m pytest
PYTHONPATH=src ruff format --check src tests
PYTHONPATH=src ruff check src tests
PYTHONPATH=src python -m practical_game_studio.cli validate
PYTHONPATH=src python -m practical_game_studio.cli framework validate
```

> `PYTHONPATH=src` matters when another checkout of this project is installed in editable
> mode; without it `import practical_game_studio` can resolve to that other working tree
> and `framework validate` will report bogus packaged-scaffold differences.

## Baseline results

| Check | Result |
| --- | --- |
| `pytest` | 491 passed |
| `ruff format --check src tests` | 80 files already formatted |
| `ruff check src tests` | All checks passed |
| `studio validate` | passed |
| `studio framework validate` | passed |

## Package version

| Item | Value |
| --- | --- |
| Distribution | `practical-game-studio` |
| Version | `0.1.0` |
| Console script | `studio` → `practical_game_studio.cli:main` |
| Requires Python | `>=3.11` |
| Runtime dependency | `jsonschema>=4.21,<5` |

## Scaffold and catalog versions

| Item | Value |
| --- | --- |
| `.studio/framework.json` → `scaffold_version` | `1.0` |
| `.studio/framework.json` → `installed_from_version` | `0.1.0` |
| `.studio/workflow-catalog.json` → `catalog_version` | `1.2` |
| Workflows in catalog | 18 |

## Schema versions

| Schema | `schema_version` |
| --- | --- |
| `critical-path.schema.json` | 3.0 |
| `decisions.schema.json` | 2.0 |
| `dependencies.schema.json` | 1.0 |
| `evidence.schema.json` | 2.0 |
| `framework.schema.json` | (no pinned version) |
| `issues.schema.json` | 1.0 |
| `milestone.schema.json` | 3.1 |
| `project.schema.json` | 1.0 |

## CLI command surface

```text
studio bootstrap
studio validate
studio framework validate
studio status
studio report
studio init

studio issue      add | list | show | update
studio evidence   add | list | show | update
studio decision   add | list | show | update | resolve
studio dependency add | list | show | update | deactivate
studio criterion  add | list | show | update | evaluate | retire
studio path       calculate | show | explain | check
```

Any change to this surface must be additive, or accompanied by a migration, per the
backlog's backwards-compatibility rules.
