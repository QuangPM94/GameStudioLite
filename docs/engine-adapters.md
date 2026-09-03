# Engine adapters

An adapter is how the framework talks to one engine. The adapter layer is the
framework's **required** abstraction; MCP and editor providers are an optional
capability source layered on top of it, never a replacement for it.

## Detection and probing are different questions

This split is the reason the framework can say something useful instead of
something wrong.

- `detect(root)` — *does this adapter recognise this project?* Answered from
  files on disk. A `project.godot` proves this is a Godot project.
- `probe(root)` — *what can this adapter do here, right now?* Answered by
  looking for the engine binary and asking it questions.

They differ because an adapter can recognise a Godot project on a machine with
no Godot installed. "This is a Godot project and I cannot run it" is a sentence
the framework must be able to say, and it is exactly what `studio doctor` prints
in that case.

## Capabilities are probed, never declared

```text
RUN  HEADLESS  TEST  BUILD  EXPORT  LOG_CAPTURE
SCREENSHOT  RUNTIME_INSPECT  INPUT_INJECTION  PROFILE
EDITOR_INSPECT  EDITOR_MODIFY
```

Each capability gets a `CapabilityReport` with a readiness of `ready`,
`unavailable`, or `unknown`, plus the detail explaining that answer.

**A capability nobody probed is not supported.** `ProbeResult.supports()`
returns False for anything absent from the report. Silence is never a yes.

An adapter reports capabilities it *cannot* do rather than omitting them, so a
reader can see what was considered and found missing instead of having to notice
an absence.

## Unsupported operations refuse usefully

Asking an adapter for something it cannot do returns a result, not an
`AttributeError`:

```text
godot-cli cannot perform SCREENSHOT (the Godot CLI cannot do this; an
editor/MCP provider is required); this adapter reports: BUILD, EXPORT,
HEADLESS, LOG_CAPTURE, RUN
```

The message names what was asked, why it failed, and what this adapter *can* do,
so an agent can choose a different action rather than retrying the same wall.

## Real-engine integration gate

The unit suite uses a deterministic fake executable for failure and timeout
coverage. CI also has a separate real-engine job pinned to Godot 4.7.2. That
job checksum-verifies the official Linux binary, bootstraps a disposable game,
launches it headlessly through `studio run`, performs smoke verification, and
checks that the resulting RUN and log ART records retain engine version, status,
hash, and source relationships. It then explicitly accepts the verification
proposal as evidence, evaluates an observed-runtime criterion, and recalculates
the milestone critical path; verification itself still performs none of those
state transitions.

The gate observes a real engine process and its output. It does not establish
gameplay quality, player behaviour, export-template availability, or support for
every Godot version.

## Resolution

`resolve_adapter(root)` asks every registered adapter to detect the project and
picks the most confident match. Confidence is compared rather than
first-match-wins, so adding a second engine adapter cannot silently change which
one an existing project resolves to.

**Resolving to nothing is a supported answer.** A planning-only project with no
engine gets `None`, and every execution command reports `unknown` and exits 4.
The framework stays usable.

`--adapter <id>` overrides detection and is honoured even when that adapter does
not detect the project: a developer overriding detection is making a deliberate
claim the framework should not second-guess.

## The Godot reference adapter

Godot is the reference engine because it can do the whole basic loop from a
command line, with no editor automation and no MCP. That makes it the right
engine to prove the execution layer against; it does not make the framework
Godot-specific.

**Finding the project.** `project.godot` at the root, or one directory below —
because `game/project.godot` is a normal layout and refusing to look would make
it unsupported for no reason. A nested match reports lower confidence.

**Finding the engine.** `$GODOT`, `$GODOT4`, or `$GODOT_BIN` first, then several
known binary names on `PATH`. Godot 3 and 4 ship under different names on
different platforms, so guessing one would produce false negatives.

**Test frameworks.** gdUnit4 and GUT are recognised by their addon directories.
No test framework is reported as `TEST: unavailable` with the reason attached —
**not** as a broken project. A project without tests has not been shown to be
broken.

**Export presets.** Read from `export_presets.cfg`. A named preset that is not
defined is refused by name, with the available presets listed, rather than
letting Godot fail deep inside an export.

**What it cannot do.** `SCREENSHOT`, `RUNTIME_INSPECT`, `INPUT_INJECTION`, and
`PROFILE` are reported `unavailable` with the reason "the Godot CLI cannot do
this; an editor/MCP provider is required".

## Writing an adapter

Subclass `BaseEngineAdapter` and implement `detect` and `probe`. Override only
the operations you can genuinely perform — every other one already refuses by
name through the base class.

```python
class MyEngineAdapter(BaseEngineAdapter):
    id = "my-engine"
    display_name = "My Engine"
    engine = "MyEngine"

    def detect(self, root: Path) -> DetectionResult: ...
    def probe(self, root: Path) -> ProbeResult: ...
    def run(self, root: Path, options: RunOptions) -> AdapterOperationResult: ...
```

Two rules an adapter must not break:

**Never claim a capability you have not probed.** Report `unknown` when you
could not determine something.

**Never turn a process result into a claim about the game.** Return runs and
artifacts. Whether a clean exit means anything is a judgement made explicitly,
by a person or an agent creating evidence.
