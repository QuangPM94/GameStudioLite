# Execution records: runs and artifacts

The framework's central claim is that it can tell what actually happened from
what someone hopes happened. Runs and artifacts are where that distinction is
stored.

- A **run** (`RUN-####`) is a fact about a process: what command ran, when,
  where, and how it ended.
- An **artifact** (`ART-####`) is a fact about a file: where it is, what it
  hashed to, and whether it is still that.
- **Evidence** (`EVD-###`) is a *claim*. It can cite runs and artifacts, and it
  never appears on its own.

## Runs are not evidence

"The engine exited 0" is a fact about a process. "The prototype is playable" is a
claim about a game. Nothing in the run or artifact code makes the leap between
them. An agent or a person makes that judgement explicitly, by creating evidence
that cites the run — and the evidence carries its own classification and
limitations.

Completing a run never creates evidence. That is enforced by test, not just by
convention.

## Run records

`.studio/state/runs.json`

| Field | Notes |
| --- | --- |
| `action` | One of `doctor`, `run`, `test`, `build`, `verify`, `export`, `capture`, `custom` |
| `status` | One of `pending`, `running`, `passed`, `failed`, `cancelled`, `unknown` |
| `command` | The argv actually executed |
| `exit_code`, `duration_ms` | Null until the run completes |
| `stdout_summary`, `stderr_summary` | Truncated; the full log belongs in an artifact |
| `revision`, `engine`, `engine_version`, `platform` | Provenance of the environment |
| `artifacts` | `ART-####` ids this run produced |
| `limitations` | What this run did *not* establish |

Two rules shape this schema:

**A run is recorded before its result exists.** `RunService.create` opens the
record in `running`, so a process that hangs, is killed, or takes the host down
still leaves a trace of what was attempted. `RunService.complete` fills in the
result, and refuses to complete a run twice.

**`unknown` is not a synonym for `failed`.** A verification that could not run —
no test framework installed, no engine binary — must stay distinguishable from
one that ran and found a problem. Only the second is grounds for an issue.

**Long output is truncated, and says so.** `summarize_output` appends an explicit
marker naming how many characters were dropped, because a fragment that looks
whole would let a reader draw a conclusion the output does not support.

```bash
studio execution list --action test --status failed
studio execution show RUN-0007
studio execution list --json
```

## Artifact records

`.studio/state/artifacts.json`

| Field | Notes |
| --- | --- |
| `type` | `log`, `build`, `screenshot`, `video`, `test-report`, `telemetry`, `profile`, `export`, `text`, `json`, `other` |
| `path` | Stored relative to the project root when it lives inside it |
| `sha256`, `size_bytes` | Captured at registration when the file exists |
| `source_run` | The `RUN-####` that produced it |
| `status` | `present`, `missing`, `modified`, `unverified` |

```bash
studio artifact add --type log --path build/out.log --source-run RUN-0007
studio artifact list --type screenshot
studio artifact show ART-0003
studio artifact verify              # read-only
studio artifact verify --record     # store the result
```

### Registering a file that is not there

`studio artifact add` records a missing file as `missing` rather than refusing.
A build that did not produce what it promised is exactly the thing worth
recording — but never silently: the CLI prints a warning saying the artifact was
recorded as missing rather than assumed present.

### Verification distinguishes three outcomes

A screenshot that silently changed is worse than a missing one, because only the
missing one is obvious. `studio artifact verify` therefore reports:

- `present` — the file is there and matches the recorded hash.
- `modified` — the file is there and does not match.
- `missing` — there is no file at that path.
- `unverified` — the file could not be read, or was registered without a hash so
  there is nothing to compare against. This is not a claim that the file is fine.

Verification is **read-only** by default: a check is an observation at a moment,
not a new fact about the record. `--record` is the explicit way to store it. The
command exits non-zero when anything did not match.

## Evidence provenance

Evidence carries `related_runs` and `related_artifacts`:

```bash
studio evidence add --title "Headless launch did not crash" \
  --claim "The prototype launches without an immediate runtime crash." \
  --classification observed --source-type runtime \
  --run RUN-0007 --artifact ART-0003

studio evidence update EVD-0012 --add-run RUN-0009 --remove-artifact ART-0003
```

Citing a run or artifact that was never recorded is refused. Evidence that points
at something missing is worse than evidence citing nothing: it reads as sourced
while its source cannot be inspected. `studio validate` checks every
run/artifact/evidence cross-reference for the same reason.

Linking is one-directional. A run does not gain a pointer back to the evidence,
because the evidence is an *interpretation* of the run while the run stays a
plain fact about a process.

The `current-state` report shows the citation alongside the claim, so a reader
deciding how much to trust a claim can see whether anything executable stands
behind it.
