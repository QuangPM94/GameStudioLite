# Execution safety

Once an AI agent can start processes on a developer's machine, the limits on
what it may do without asking have to be stated rather than assumed.

Every operation is classified by risk, each risk class says who must agree, and
every authorisation is recorded in the run.

## Risk classes

| Class | Operations | Why |
| --- | --- | --- |
| `safe` | `doctor`, `validate`, `status`, `report`, every `list`/`show`, `criterion support`, `workflow *`, `upgrade check/plan` | Reads state; changes nothing |
| `low` | `run`, `test`, `verify`, `capture` | Runs the game; writes only logs the framework owns |
| `medium` | `build`, `export`, `artifact add`, `upgrade apply` | Writes files outside `.studio`, or changes how the project builds |
| `high` | global install, engine upgrade, file deletion, build/network/credential configuration | Not implemented; classified in advance so adding one later cannot land unclassified |

**An operation the framework does not recognise is treated as `high`.** The
cautious default is the only safe one for something it has never heard of.

## Who must agree

The threshold depends on the project's `review_mode`:

| Review mode | Lowest risk that needs agreement |
| --- | --- |
| `fast` | `high` |
| `guided` (default) | `medium` |
| `strict` | `low` |

`fast` still gates high risk. A review preference is not a licence to delete
things unasked.

## Non-interactive safety

In a non-interactive terminal there is nobody to ask, so anything above the
threshold is **denied** unless `--yes` was passed. An agent cannot manufacture
consent by finding itself unsupervised.

`--json` output counts as non-interactive even on a TTY: prompting into a pipe
would hang a caller that has no way to answer.

High-risk operations are refused even with `--yes` when no person is present.
`--yes` records that someone typed it; it does not put anyone in the room.

## Denials explain themselves

```text
studio: Refused to run build (medium risk, review mode guided): there is nobody
to ask in a non-interactive terminal
To authorise this, re-run with --yes, or ask the developer to run it.
Nothing was executed and no state was changed.
```

A refusal names the operation, its risk, the review mode, why it was refused, and
the exact flag that would authorise it — so an agent can ask the human for that
specific thing instead of retrying blindly.

**Exit code 5** is reserved for a denial. It is neither a crash nor a usage
error: the request was well-formed, understood, and declined.

| Exit code | Meaning |
| --- | --- |
| `0` | Succeeded |
| `1` | Ran and failed |
| `2` | Usage error |
| `3` | Referenced record not found |
| `4` | Could not be attempted, or result unknown |
| `5` | Refused: not authorised |

## Audit trail

Every run records the risk class it was assigned and how it was authorised:

```text
RUN-0001 build | medium | flag
RUN-0002 run   | low    | risk-below-threshold
```

| `authorization` | Meaning |
| --- | --- |
| `risk-below-threshold` | The review mode permitted it without asking |
| `flag` | Authorised with `--yes` |
| `interactive` | Someone confirmed at a prompt |
| `unrecorded` | The run predates the audit trail (migration `004`) |

"Who agreed to this build?" is answerable from the record rather than from
anyone's recollection.

Runs written before migration `004` are marked `unrecorded` rather than
backfilled. Inventing an approval nobody gave would defeat the entire point of
keeping the record.

## What is never passed to a child process

Credential-shaped environment variables (`AWS_*`, `GITHUB_TOKEN`, `NPM_TOKEN`,
API keys, and similar) are withheld from every process the framework starts. The
framework runs engines and build tools on a developer's machine, and leaking
credentials into something that logs its own environment is a real way to lose
them. An adapter that genuinely needs one opts in by name.

Secret-looking command arguments are redacted before being written to
`runs.json`, which lives in the project's repository: `--api-token=abc123`
is recorded as `--api-token=***`.
