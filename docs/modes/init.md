# `mathema init`

Additive and idempotent setup: scaffold the git ergonomics for a tracked
`.mathema/` store; for any targets, stub scaffolding for the unclaimed
functions [`mathema audit`](audit.md) finds (a concrete, enumerated task
list to fill in, not a claim itself); and, on request, vendor the
[mathema-agents](https://github.com/tetrionlabs/mathema-agents) skills for
your agent tool.

```bash
mathema init [mypkg mypkg.sub ...] [--agents [TOOL]]
```

## Arguments

| Flag | Meaning |
|---|---|
| `target` | zero or more importable module or package name(s), same as `audit`; omit to scaffold only the git files |
| `--root` | project root to write `.gitattributes`, `.mathema/.gitignore`, and `claims/` under (default: the nearest ancestor holding `.mathema/` within the enclosing git repository, else that repository, else `.`; never the home directory) |
| `--agents [TOOL]` | also vendor the mathema-agents skills for TOOL (`claude`, `codex`, `gemini`, `cursor`, `copilot`, `windsurf`, `cline`); bare `--agents` auto-detects the one your project already uses |
| `--agents-url` | git URL for the skills repo (default the mathema-agents repository, not yet public; also read from `MATHEMA_AGENTS_URL`) |
| `--agents-ref` | branch or tag of the skills repo to fetch (default: the branch matching your mathema minor line, such as `v0.6`, falling back to the repo's default branch); an explicit ref is never substituted |
| `--force` | overwrite vendored agent files that already exist (default: leave them) |
| `--ci [PROVIDER]` | also scaffold the verify-gate CI fragment (`github`, `gitlab`); bare `--ci` means github. Written only where absent, then it is yours to edit |

## The git scaffold

With or without a target, `init` writes (only where absent) the two
files a tracked store wants:

- **`.gitattributes`** marking `.mathema/verified/**/*.yaml`
  `linguist-generated`, so a records diff collapses by default and the
  store drops out of the repository's language stats, while staying
  expandable when you do want to read it. (`linguist-generated`, not
  `-diff`: the record stays reviewable.)
- **`.mathema/.gitignore`** tracking the durable evidence and required
  artifacts (`verified/`, `meta/`, `compendium/`, `badges/`) and ignoring
  regenerated state (`declared/`, `issues/`).

The evidence is meant to be committed: a verified record is the durable
statement of what was checked, and reviewers read it (by claim, with
[`mathema review`](review.md)) the way they read tests. A project that
would rather regenerate the store from its examples and tests can ignore
all of `.mathema/` instead; that is a local choice, not the default.

## The function stubs

For every discovered function with zero claims, writes a bare
`claims: []` declared entry, an explicit, empty placeholder, not a
claim, to `claims/<module>.claims.yaml`.

```yaml
mypkg.mod.branchy_fn:
  claims: []
mypkg.mod.pure_fn:
  claims: []
```

Additive and idempotent by construction: reads any existing file first
and only appends keys not already present (claimed *or* already
stubbed), so a hand-written claim sitting next to a stub is never
touched by a later re-run as the target package grows.

```
$ mathema init mypkg
mathema init: scaffolded git files:
  .gitattributes
  .mathema/.gitignore
mathema init: wrote stub entries to:
  claims/mypkg.mod.claims.yaml
```

Running it again once the git files are in place and every stub has
either been filled in or left alone:

```
$ mathema init mypkg
mathema init: git files already in place
mathema init: no stubs needed, every discovered function already has a claim, or none were found
mathema init: nothing to do
```

## The agent skills (`--agents`)

`mathema init --agents <tool>` vendors the
[mathema-agents](https://github.com/tetrionlabs/mathema-agents) skills,
the agent-facing procedures for writing and checking claims, and copies
the one adapter your tool reads. Where each piece lands depends on the
tool, so name yours (or let bare `--agents` detect it):

| tool | `skills/` lands in | adapter copied |
|---|---|---|
| `claude` | `.claude/skills/` | (none; the skills dir is the adapter) |
| `codex` (also `zed`, `aider`, `jules`) | `./skills/` | `AGENTS.md` |
| `gemini` | `./skills/` | `GEMINI.md` |
| `cursor` | `./skills/` | `.cursor/rules/` |
| `copilot` | `./skills/` | `.github/copilot-instructions.md` |
| `windsurf` | `./skills/` | `.windsurf/rules/` |
| `cline` (also `roo`) | `./skills/` | `.clinerules/` |

```
$ mathema init --agents claude
mathema init: git files already in place
mathema init: vendored mathema-agents skills for claude:
  .claude/skills/design-claims/SKILL.md
  .claude/skills/use-mathema-mcp/SKILL.md
```

Only the skills and your tool's adapter are copied, never the skills
repo's own notes, license, or history. A file already present is left as
it is (`--force` overwrites), so a re-run is safe and a local edit
survives. Bare `--agents` with no tool detected (or several) vendors
`skills/` neutrally and prints the table above so you finish by hand.

**mathema reaches the network only when you ask it to.** Every other
command is offline; `--agents` is the one that fetches, and it does so
through your `git` (so a private repo works if your git can already read
it). If the fetch cannot happen (no network, `git` missing, or you lack
access to the repo), init says so plainly, prints the manual steps, and
still exits cleanly, its own scaffolding is already done.

## The CI gate (`--ci`)

`mathema init --ci` writes the verify-gate workflow an adopting repo
would otherwise write from scratch: `.github/workflows/mathema-verify.yml`
(or, with `--ci gitlab`, a `.gitlab-ci.mathema.yml` fragment plus the
`include:` line to add). The job installs your project and mathema, then
runs `mathema verify --root .`, whose strict default is the gate: exit 0
clean, 1 gate failure, 2 broken invocation, so CI can tell a failing
gate from a broken job without parsing output. The file is written only
where absent and is yours to edit from then on; the one line you will
likely change is the install step, marked in the file.
