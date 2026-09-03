# Release

A release is where every honesty rule in this framework gets tested at once,
because "we shipped it" is the claim people most want to make on the least
evidence.

The four steps are deliberately separate, and **none of them concludes the
next**:

```bash
studio release doctor              # can this project be released at all?
studio release build --yes         # produce a package
studio release package <path>      # record it, hashed and traceable
studio release verify ART-0007     # check the package that was recorded
```

Producing a package does not verify it. Verifying that a file exists does not
mean it runs. Each step prints what it did not establish alongside what it did.

## `studio release doctor`

Six checks, each reported individually:

| Check | Fails when |
| --- | --- |
| `project_identity` | The project is still named "Untitled Game" |
| `version_metadata` | No engine version is recorded (`unknown`) |
| `licence` | `LICENSE` is missing |
| `third_party_notices` | `THIRD_PARTY_NOTICES.md` is missing |
| `engine_export` | The adapter cannot export |
| `revision` | The revision is unknown or the tree is dirty (`unknown`) |

**Absence is reported, never fixed.** Generating a licence file for someone would
be worse than saying it is missing.

**A dirty working tree is `unknown`, not `failed`.** Releasing from uncommitted
changes is a choice. It just cannot be reproduced from the recorded revision, and
a reader of that package needs to know.

The report prints "Blockers" and "Could not be determined" even when empty. A
reader deciding whether to ship needs "nothing is blocking" to look different
from "we did not check".

## `studio release package`

Registers the produced file as a build artifact with its SHA-256, size, the
revision it came from, and whether the tree was dirty.

**A build that produced nothing is recorded as missing**, not refused. "The build
reported success and produced nothing" is precisely the situation worth having on
record.

Every packaging carries the limitation that the package has not been launched.

## `studio release verify`

| Check | Establishes |
| --- | --- |
| `package_present` | A file exists at the recorded path |
| `package_hash` | It still matches the hash recorded at packaging |
| `package_runs` | **Nothing** — always `unknown` |

`package_runs` is permanently `unknown` because the framework cannot smoke-test
an arbitrary distributable target: a Windows executable, an Android APK, and a
web build have nothing in common it could invoke. Launching the packaged build is
a separate, manual step, and pretending otherwise would put a green tick on the
one thing nobody checked.

`studio release verify` therefore exits `4` (unknown) on a perfectly good
package. That is the honest answer.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Ready / passed |
| `1` | Blocked / failed |
| `4` | Could not be determined |
| `5` | Refused: not authorised |

## What is deliberately not here

No Steam publishing, no console submission, no store metadata, no marketing
automation. The backlog rules those out until the vertical-slice loop works, and
they are the kind of integration that is easy to add and very hard to remove once
a project depends on it.
