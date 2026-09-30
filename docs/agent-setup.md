# Set up mathema for a coding agent

This guide registers mathema's MCP server with the agent tool you use,
vendors the skills that teach the agent the claim loop, and puts in place
the two controls that stay with you: a PIN and a policy. It assumes you
have read [Working with coding agents](agents.md), which says what an
agent can and cannot do here.

The commands on this page write to your tool's configuration, fetch from
the network or read a PIN from your terminal, so they are shown rather
than run by the test suite behind the other pages. Each was run by hand
while this page was written; the server blocks were checked by starting
`mathema mcp serve --root <project>` from a project environment and
listing its tools over stdio.

## 1. Install the extra

<!-- checked by hand -->
```bash
pip install "mathema[mcp]"
```

The extra brings the MCP SDK. Without it, `mathema mcp serve` prints the
install hint and exits 2.

## 2. Register the server

The server runs on stdio: your tool starts `mathema mcp serve` as a
subprocess and talks to it over its standard input and output. Two
things matter in the configuration. Run it from the project's own
environment, because the tools import your code to check it, so the
`mathema` that serves must be the one installed beside your project's
dependencies. And give both paths in full, since the tool's working
directory is not your project's.

**Claude Code** reads `.mcp.json` at the project root; commit it so the
team shares one configuration.

<!-- checked by hand -->
```json
{
  "mcpServers": {
    "mathema": {
      "type": "stdio",
      "command": "/path/to/project/.venv/bin/mathema",
      "args": ["mcp", "serve", "--root", "/path/to/project"]
    }
  }
}
```

**Cursor** reads `.cursor/mcp.json` in the project, or `~/.cursor/mcp.json`
for every project. **Claude Desktop** reads
`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS and `%APPDATA%\Claude\claude_desktop_config.json` on Windows. Both
take the same block without the `type` field:

<!-- checked by hand -->
```json
{
  "mcpServers": {
    "mathema": {
      "command": "/path/to/project/.venv/bin/mathema",
      "args": ["mcp", "serve", "--root", "/path/to/project"]
    }
  }
}
```

In a project managed with uv, `"command": "uv"` with
`"args": ["run", "--directory", "/path/to/project", "mathema", "mcp",
"serve", "--root", "/path/to/project"]` does the same through uv.

Once the tool restarts, its server list shows `mathema` with fifteen
tools, three resources and three prompts. [The MCP interface](modes/mcp.md)
lists each one. None of them accepts a verdict from the agent, and there
is no accept tool: the deciding stays in the terminal, with you.

## 3. Vendor the skills

<!-- checked by hand -->
```bash
mathema init --agents claude
```

`init --agents` copies the [mathema-agents](https://github.com/tetrionlabs/mathema-agents)
skills, the agent-facing procedures for writing and checking claims, into
the place your tool reads them, plus the one adapter file that tool
wants. Name the tool (`claude`, `codex`, `gemini`, `cursor`, `copilot`,
`windsurf`, `cline`) or let bare `--agents` detect the one your project
already uses. This is the one command in mathema that reaches the
network, through your own `git`, and only when you run it. A file already
present is left as it is, so a re-run is safe. [`mathema init`](modes/init.md#the-agent-skills-agents)
has the table of where each tool's files land.

## 4. Set a PIN the agent does not know

<!-- checked by hand -->
```bash
mathema pin set
```

The PIN is read from the controlling terminal only, never from a pipe or
a subprocess, which is how an agent runs commands. `--yes` skips the y/N
prompt on `mathema accept` and never the PIN. It is stored salted and
hashed in `~/.config/mathema/auth.yaml` by default (`XDG_CONFIG_HOME`
moves it), outside the project, and every acceptance made with it carries
the credential's key id in the record.
`mathema pin status` prints the method and that key id; you need it for
the next step.

## 5. Commit a policy

An agent with a shell could remove `auth.yaml` and set a PIN of its own.
That changes the key id, so the defence is a committed policy naming the
key ids you accept, in `.mathema/meta/policy.yaml`:

<!-- checked by hand -->
```yaml
acceptance:
  require_verification: true
  keys: [a3f2c1]
```

With the policy committed, `mathema verify` fails on any acceptance that
was not made with one of those keys, at write time and again on every
sweep, so a signature the agent made for itself fails CI rather than
slipping through. Protect `.mathema/meta/` and `.mathema/verified/` with
your forge's code-owner review, so the policy itself changes only with a
person's approval. [`mathema pin`](modes/pin.md#project-policy) has the
full policy file.

## 6. What happens from here

The agent proposes claims and checks them with `adjudicate_target`,
reads every verdict and counterexample, sees what is waiting on a person
in `pending_decisions`, and may lock a function it has finished with
`lock_target`. What it cannot do is decide what a verdict means: accepting
evidence as sufficient, owning a risk, recording that a falsification was
a wrong claim, or unlocking a function all go through `mathema accept`
and `mathema unlock` at your terminal, behind the PIN. The table on
[Working with coding agents](agents.md#what-an-agent-can-and-cannot-do)
has the full division.
