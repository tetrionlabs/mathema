# `mathema review`

Read the verified store by CLAIM, not by raw YAML diff. `mathema review`
compares the records at a git ref (the base, default `HEAD`) against the
working tree and reports the handful of facts a reviewer actually needs:
which verdicts flipped, which claims were added or removed, which are
newly falsified, and which records a human reconciled.

```bash
mathema review [<ref>] [--root .] [--format text|json] [--output FILE]
```

## Arguments

| Flag | Meaning |
|---|---|
| `ref` | the base git ref to compare the working tree against (default `HEAD`) |
| `--root` | project root holding `.mathema/verified` (default `.`) |
| `--format` | `text` (default) or `json`: the delta as data, for a CI job to post as a PR comment |
| `--output FILE` | write the report to a file instead of stdout |

## What it reports

Keyed by function (`module.qualname`), and within each, by claim name:

- **verdict flips** (`old -> new`), with newly `falsified` or
  `invalidated` claims marked `!!`,
- **claims added** and **claims removed** between the two states,
- **newly falsified** claims (a flip into `falsified`, or an added claim
  that lands `falsified`),
- **reconciled** records (a human blessed the current contents with
  [`mathema accept --as reconciled`](accept.md#-as-reconciled-after-a-merge-rebase-or-a-declared-claim-edit)).

The closing summary counts each movement across the whole store.

## Why not a raw diff

A `git diff` over `.mathema/verified/` shows every re-anchored lineage
line and every reordered row, burying the one verdict that actually
changed. `review` reads both states as records and diffs their claims, so
a flip from `holds` to `falsified` reads as one line, not a wall of YAML.
It is the reviewer-facing counterpart to the CI badge snapshot: a human
summary, and a `--format json` a pipeline can post on the pull request.

## Worked example

```
$ mathema review HEAD
Claim changes since HEAD: 1 function(s), 1 verdict flip(s), 1 added, 0 removed, 0 newly falsified, 0 reconciled.

functions.softmax
    sums_to_one: holds -> invalidated  !!
    + bounded
```

`sums_to_one` regressed and a new `bounded` claim was declared; the
reviewer sees exactly that, and nothing else. A claim that held at the
base and now has a counterexample is `invalidated`, not newly
falsified, so the falsified count stays at 0.

## The record shape it reads

A verified record is deliberately self-contained (everything needed to
read and re-check a claim rides its row) but not verbose. Empty and
derivable fields are omitted rather than written as null placeholders:
a claim carries `n`, `counterexample`, `note`, `sketch`, `tolerance`, and
`meta` only when they say something; `condition` rides a derive row (where
it is the proof's own quantifier) but not a probe row (where it merely
restates the statement and domain); a per-row `grammar` appears only when
it differs from the record's grammar. Claim rows are sorted by name, so a
non-deterministic probe order never shows up as a diff. None of this
touches the integrity checksum, which covers only each claim's name,
verdict, and acceptance, plus the identity and lock forms.

**Surface versus author.** Two provenance facts are kept apart, because
they answer different questions:

- **`authored.surface`** is *where* the claim was written, the load-bearing
  gating fact: `docstring`, `claims-file` (a declared claims file),
  `decorator`, `annotation`, `inline`, `suggested` (mathema volunteered
  it, and a suggestion never gates until a human adopts it), `builtin` (the
  structural battery), or `compendium`.
- **`authored.by`** is *who* proposed the claim, an optional identity: an
  AI model, a harness, or a git username. It is absent unless stated,
  either on the claim's own `authored` statement or through the
  `MATHEMA_CLAIM_SOURCE` environment a harness sets when an agent proposes
  claims. It is never stamped on a surface mathema itself generated
  (`builtin`/`suggested`/`compendium`), which mathema authored, not the
  agent that ran the verification.

Neither is the `route` (`probe`/`derive`/`examine`), which is *how* the
claim was checked. Where a claim came from, who wrote it, and how it was
adjudicated are three separate axes, and the record keeps them so.
