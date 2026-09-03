# Work packets

A work packet is a contract written **before** an agent starts. It states what to
change, which files may be touched, which may not, what must be true at the end,
and which commands prove it. The agent works inside that boundary, and the
framework checks the boundary held.

This is bounded autonomous work — not unrestricted project modification.

## The lifecycle

```bash
studio work add --goal "Add a score counter" \
  --reason "The prototype hypothesis needs a visible score." \
  --allow "src/*.py" --forbid ".studio/**" \
  --criterion "The score increments on delivery." \
  --verify-with "python -m pytest tests/test_score.py"

studio work ready                 # packets whose dependencies are complete
studio work start WORK-0001       # pins the revision scope is measured from
# ... the agent does the work ...
studio work verify WORK-0001      # runs the checks and confirms the scope held
studio work complete WORK-0001    # refused unless verification passed
```

There is no path that skips a step. A packet must be started before it can be
verified, and verified before it can be completed.

## Four rules, each enforced

**An agent cannot widen its own scope.** `allowed_files` and `forbidden_files`
are set when the packet is created. A change outside them fails verification, and
the packet cannot edit its own contract to make itself pass.

**An agent cannot complete without verification.** Completion requires a
verification run that actually happened and actually passed. There is no flag for
"trust me".

**A failing check keeps the packet incomplete.** Failed verification moves the
packet to `failed`, never to `complete`, and the failure stays in
`verification_history`.

**Out-of-scope changes fail even when the tests pass.** Green tests do not excuse
touching what the packet promised not to:

```text
WORK-0001: failed
out-of-scope change(s): sneaky.md (not in allowed_files)

Commands:
- python -m pytest: passed (completed, exit 0)
```

## The scope check reads git, not the agent

`studio work verify` determines what changed by asking git — `git diff` against
the revision pinned at `work start`, plus untracked files. It does not ask the
agent what it changed, because that would make the check circular: the thing
under examination would be supplying the evidence.

Two consequences follow:

**A scope that could not be determined never counts as held.** No git, no
answer — and `ScopeReport.ok` is False. The framework does not conclude a
boundary held on a check it could not perform.

**The framework's own bookkeeping is excluded.** `work start` and `work verify`
necessarily write `.studio/state/work.json` and re-render reports. Counting those
as the agent's changes would make every packet fail on the framework's own
writes. Every other path under `.studio` is still checked, so a packet can still
forbid an agent from hand-editing canonical state.

## Two things a packet cannot be created without

**At least one acceptance criterion.** A packet with none can never be
completed, so creating one would be creating a trap.

**At least one `allowed_files` pattern.** An empty scope permits no change at
all, which is the safe default for an author who forgot to say — so the framework
asks rather than assuming.

A packet with no `verification_commands` is allowed but warned about at creation:
it can never be completed either, and saying so early is more useful than
letting it be discovered at the end.

## Human approval

`--requires-approval` marks a packet whose author decided a person must agree
before it starts. `studio work start` routes that through the same execution
safety layer as any risky command: a non-interactive terminal denies it unless
`--yes` was passed.

## What is deliberately not here

No multi-agent orchestration. The backlog rules out a permanent multi-agent
hierarchy, and a work packet is exactly the structured hand-off that a future
one would use — building the orchestration before anyone needs it would fix a
design nobody has tested.
