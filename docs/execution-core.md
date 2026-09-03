# Execution core: doctor, run, test, build, verify

The framework does not just describe a project's intentions. It can run the
game, and it can say what running it did and did not establish.

That second half is the point. `studio verify` is built so that "the build is
green" can never quietly become "the game works".

## `studio doctor`

Answers one question honestly: what can this machine actually do?

```bash
studio doctor
studio doctor --json
studio doctor --adapter godot-cli
```

It probes; it never infers. Every line corresponds to something it looked for.
It performs no configuration — a doctor that fixed things would make its own
report untrustworthy, because a reader could no longer tell what was already
true from what the doctor just did.

Readiness has four values, and `UNKNOWN` is not a polite `UNAVAILABLE`:

| Value | Means |
| --- | --- |
| `READY` | Probed and available |
| `UNAVAILABLE` | Probed and not there |
| `UNKNOWN` | Could not be determined |
| `NOT CONFIGURED` | Nothing has been set up (providers) |

"We looked and it is not there" and "we could not tell" lead to different next
actions, so they are never merged.

## `studio run`, `studio test`, `studio build`

Each resolves an engine adapter, asks it for one operation, and reports the
resulting RUN and ART records.

```bash
studio run --headless --timeout 30
studio test --suite unit
studio build --profile release --target "Windows Desktop"
```

Exit codes distinguish three outcomes, because an agent choosing what to do next
needs them separated:

| Code | Meaning |
| --- | --- |
| `0` | The operation ran and reported success |
| `1` | The operation ran and reported failure |
| `4` | The operation could not be attempted, or its result is unknown |

None of these commands creates evidence. Each closes by saying so, and by
printing the `studio evidence add --run ...` you would run to make a claim.

## `studio verify`

```bash
studio verify --level smoke
studio verify --levels          # what each level does and does not establish
studio verify --level release --json
```

| Level | Establishes | Does **not** establish |
| --- | --- | --- |
| `static` | Project state is coherent | Anything about the engine |
| `smoke` | The engine starts and stays up | Anything about gameplay |
| `runtime` | The project's tests pass | That the game is enjoyable |
| `gameplay` | **Nothing automatically** | Requires human or provider observation |
| `release` | A package was produced | That the package runs |

Levels are cumulative: `runtime` also runs `static` and `smoke`. A report's
status is the **worst** of its checks, so one `unknown` keeps the whole report
out of the green.

Three rules hold at every level:

**A check that could not run reports `unknown`.** Never `passed`, never `failed`.
A missing test framework has not shown the project to be broken, and it has not
shown it to be sound either.

**`gameplay` can never pass on its own.** No process result observes a player.
A framework that let `gameplay` go green from an exit code would be lying about
the only thing that finally matters.

**Output always states what was not established.** The "What this did NOT
establish" section prints even when empty, because silence there reads as "there
are no caveats" — the most dangerous thing this output could imply.

### A headless launch that gets killed is a *pass*

A game with a main loop is supposed to keep running. `smoke` treats "still alive
when the timeout fired" as success, with the limitation attached: the engine
started and stayed up, and nothing about gameplay was observed.

## Evidence proposals

`studio verify` offers the strongest **honest** claim its observations would
support, with limitations attached, and the exact command to accept it:

```text
Evidence proposals:
- [observed] The current build launches the engine without an immediate runtime crash.
    limitation: No player input, gameplay loop, or player experience was verified.

These are proposals, not evidence. Accept one explicitly:
studio evidence add \
  --title "<your title>" \
  --claim "The current build launches the engine without an immediate runtime crash." \
  --classification observed --source-type runtime \
  --run RUN-0001 --artifact ART-0001 \
  --limitation "No player input, gameplay loop, or player experience was verified."
```

The framework may propose. It never invents a gameplay claim, and it never
proposes a claim about fun, clarity, or difficulty, because no process result can
support one.

## The process runner

Everything the framework executes goes through
`practical_game_studio.execution`, so four guarantees hold everywhere:

- **Nothing runs forever.** Every execution carries a timeout; a process that
  ignores a polite signal is killed after a grace period.
- **Nothing waits for input.** stdin is closed. An agent cannot leave a program
  blocked on a prompt.
- **Output survives bad bytes.** Captured output is decoded as UTF-8 with
  replacement, so one stray byte from an engine does not cost the whole log.
- **A killed process is not a failed one.** A timeout maps to `unknown`.

Two safety behaviours are worth knowing about:

**Credential-shaped environment variables are not passed to child processes.**
The framework runs engines and build tools on a developer's machine, and leaking
credentials into something that logs its own environment is a real way to lose
them. An adapter that genuinely needs one opts in by name.

**Secret-looking arguments are redacted before being stored.** `runs.json` is
committed to the project's repository, so `--api-token=abc123` is recorded as
`--api-token=***`.

Full captured output is written to `.studio/logs/<run-id>.log` and registered as
an artifact. Canonical state keeps only a truncated summary, so `runs.json`
stays reviewable in a diff while nothing captured is lost.
