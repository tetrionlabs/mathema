# Working with coding agents

mathema does not need an agent, and nothing in the core depends on one. This
section is for people who pair with a coding agent (Claude Code, Cursor and
the like) and want the agent to use mathema without being able to decide on
its own what counts as correct.

The division of labour is simple to state: agents propose, mathema
adjudicates, people accept. An agent can write claims, run checks and read
every verdict and counterexample, which is most of the loop, but no verdict
ever comes from the agent, and no decision about what a verdict means for the
project is the agent's to make. That is what lets you hand an agent the
keyboard without handing it the definition of correct.

## What an agent can and cannot do

| An agent can | Only a person can |
|---|---|
| propose claims and check them against the real function | accept evidence as sufficient, or own a residual risk |
| read verdicts, counterexamples and the human-decision queue | record that a falsification was a wrong claim rather than a bug |
| lock a function it has finished | unlock a locked function |
| edit claims in docstrings and claims files | adopt an edited claim over the one already verified |

The last row is the one people ask about. When a claim that already has a
verified record is edited, weakened or narrowed, the verified version keeps
being checked and the sweep reports the claim as re-authored, until a person
adopts the change with `mathema accept KEY CLAIM --as superseded`. A claim
deleted from every authoring surface is restored from its verified record for
the same reason. An agent can propose a weaker claim; it cannot make the
record forget the stronger one.

## Set a PIN the agent does not know

Every acceptance and every unlock asks for a y/N confirmation, and an agent
with a shell can answer that. What it cannot answer is a PIN it does not know.
Set one yourself, in your own terminal:

```bash
mathema pin set
```

The PIN is read from the controlling terminal only, never from a pipe or a
subprocess, which is how an agent runs commands, and `--yes` skips the y/N
prompt but never the PIN. It is stored salted and hashed in
`~/.config/mathema/auth.yaml`, outside the project, and every acceptance made
with it carries its key id in the record. Without a PIN, `mathema accept
--yes` works for anyone with a shell, an agent included. The name on an
acceptance (`--by`, which defaults to your git `user.name`) is free text for
the same reason, so when it matters who decided, read the record's
`verified_by` key id rather than the name.

An agent with unrestricted shell access could still delete that file and set
a PIN of its own. That changes the key id, so the defence is to commit a
policy naming the key ids you accept:

```yaml
# .mathema/meta/policy.yaml
acceptance:
  require_verification: true
  keys: [a3f2c1]
```

With the policy committed, `mathema verify` fails on any acceptance that was
not made with one of those keys, so a signature the agent made for itself
fails CI rather than slipping through. Protect `.mathema/meta/` (and
`.mathema/verified/`) with your forge's code-owner review so the policy
itself changes only with a person's approval. [mathema pin](modes/pin.md) has
the details, including rotation.

None of this is a wall against an agent determined to subvert it, and it is
not meant to be one: it is a tripwire. The normal loop cannot cross it, and
every way around it leaves a trace in the record or the diff.

## Giving an agent the tools

Two pieces, both optional:

- **The MCP server.** `mathema mcp serve` exposes the checking tools
  (adjudicate a function, parse a claim, read the decision queue, lock) over
  MCP, and deliberately none of the deciding ones. Register it as a stdio
  server in your agent's MCP settings, run from the project's own
  environment. [The MCP interface](modes/mcp.md) lists every tool.
- **Agent skills.** `mathema init --agents` vendors skills and per-tool
  instructions from the
  [mathema-agents](https://github.com/tetrionlabs/mathema-agents) repository
  (not yet public), which teach an agent to run the claim loop properly rather
  than guess at it. It is the one command in mathema that fetches anything,
  and only when you run it. See [mathema init](modes/init.md).
