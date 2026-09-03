# Providers and media provenance

Two features that share one rule: **the framework may only claim what it has
actually established.**

## Providers are optional capability sources

```text
EngineAdapter  = required abstraction
Provider       = optional capability source
```

A provider is something that can do more with an engine than its command line
can — an editor plugin, an MCP server, a debug bridge. Screenshots, scene-tree
inspection, and input injection live there because no engine CLI offers them.

A provider may **add** capabilities. It may never become required for one, and
it may never remove one an adapter already has. Every operation a provider could
accelerate still has a CLI answer, even if that answer is "this cannot be
observed here" — otherwise configuring MCP would quietly become mandatory.

```bash
studio provider list
studio provider doctor
studio provider capabilities godot-mcp
```

**No providers is a normal answer.** `studio provider list` says so outright
rather than treating it as a problem to fix.

### Health has four values

| Value | Means |
| --- | --- |
| `healthy` | Reachable and usable |
| `unreachable` | Configured but not responding |
| `not-configured` | Never set up |
| `unknown` | Could not be determined |

They are distinguished because they call for different actions: fix it, start
it, configure it, or investigate.

### An unreachable provider supports nothing

`ProviderProbe.supports()` returns False for every capability when the provider
is not healthy. Its declared capabilities are still *listed*, so a reader can see
what configuring it would buy — but nothing can act on that list by mistake.

### What the Godot MCP provider actually does

GameStudioLite is a command-line tool. It does not speak MCP: that connection
belongs to the AI agent or editor the developer is using. So the Godot MCP
provider does exactly what a CLI honestly can:

1. Detect that a Godot MCP server is configured, and where
   (`.studio/providers.json`, `.mcp.json`, `.vscode/mcp.json`, `.cursor/mcp.json`).
2. Report the capabilities that configuration claims.
3. State the provenance rules results obtained through it must carry.

It never claims to have taken a screenshot. When an agent captures one over its
own MCP connection, that image enters the framework like any other file —
`studio artifact add --type screenshot` — and the rules below govern what may be
claimed from it.

A configured server is reported as `unknown`, never `healthy`. A config file
proves configuration, not reachability, and promoting it would mean asserting
something the framework has not checked.

## Media provenance

A screenshot proves a frame was rendered. A video proves a session was recorded.
Neither proves a player understood anything — and that gap is where a project
deceives itself most easily, because a folder of screenshots *feels* like proof
of a working game while establishing nothing about whether it is playable.

So media carries a provenance question: **who or what produced this, and does
that support the claim being made?**

```bash
studio artifact add --type screenshot --path shot.png \
  --capture-source human-playtest
```

| Capture source | Strongest classification | Can support player behaviour? |
| --- | --- | --- |
| `human-playtest` | `observed` | **yes** |
| `developer-session` | `observed` | no |
| `automated-run` | `observed` | no |
| `provider-capture` | `observed` | no |
| `external-report` | `user-reported` | yes |
| `unknown` | `unknown` | no |

Three of these deserve saying out loud:

**A developer session is not player behaviour.** Someone who built the thing
cannot be surprised by it.

**Injected input is not player behaviour.** A sequence the framework or an agent
drove may be recorded as `observed` runtime evidence — never as
`observed-player-behavior`.

**Media with no recorded provenance supports nothing.** The default is `unknown`
rather than a guess from the file type, because a `.png` says nothing about who
was at the keyboard.

### The rule is enforced, not just documented

`studio evidence add` refuses a claim stronger than the cited media supports:

```text
studio: ART-0003 cannot support a 'observed' claim: ART-0003 was captured as
'unknown', which supports at most 'unknown'. Media with no recorded provenance
supports no classification. Record how it was captured before drawing anything
from it. Record it as 'unknown', or capture the artifact with a provenance that
supports the claim.
```

The check applies only to cited **media** (`screenshot`, `video`, `telemetry`,
`profile`). A build log is not something anyone mistakes for proof of play, and a
person who watched a playtest can still record what they saw without attaching a
file at all.

`studio artifact add` prints the constraint at registration time rather than
waiting for someone to over-claim, because the limit is most useful before the
claim is written.
