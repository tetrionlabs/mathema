# `mathema verify`

The test-runner face and the CI gate: sweeps the spec store,
re-adjudicates every function whose `form` hash no longer matches its
record (new or changed code), and refreshes the machine records so the
next run has a baseline.

```bash
mathema verify [<key> ...] [--root .]
```

Given one or more store keys (canonical dotted `module.qualname`), the
sweep is confined to exactly those records, re-adjudicating and
re-stamping each in place. Freshness never skips a key you named:
the form-hash short-circuit is an optimisation for a whole-store
sweep, so asking about one key always re-checks it (this is the fix
the integrity-mismatch warning points at): the single-key form the reconcile workflow
points you at (`mathema verify mypkg.mod.fn` after a merge touched one
record). With no key it sweeps the whole store as before. A key that
names no record fails as a clear per-key problem line, exit 2.

## Arguments

| Flag | Meaning |
|---|---|
| `<key> ...` | zero or more store keys to confine the sweep to; omit for the whole store |
| `--root` | project root holding `.mathema/verified` and `claimspec.yaml` (default `.`) |
| `--all` | re-adjudicate everything, ignoring form-hash freshness |
| `--strict` / `--lenient` | one strictness pair shared with `check`; strict is the default here (CI gates a settled store), `--lenient` reports unverifiable claims and accepted risk instead of failing on them |
| `--status [TARGET]` | report fresh/stale per `@track_claims`-tagged function, adjudicate nothing, exit 0; an optional TARGET (dotted name or file path) is imported first so its tagged functions register |
| `--format` | `text` (default) or `json`: the whole sweep as data; per-key entries with `why`, gate `counts`, and claim rows in the same vocabulary `check --format compact` and the MCP tools speak (`stance`/`verdict`/`route`/`source`/`gates`, `counterexample` iff refuted). Exit codes are identical either way |
| `--output FILE` | write the report to a file instead of stdout |

Store keys are canonical dotted `module.qualname` names, resolved by
importing from `--root`; the target must be importable there (the
old `--target` file preload and its bare-name key fallback are gone;
a bare-name key now fails as a clear per-key problem line).

## What fails the run

| Finding | Default (strict) | `--lenient` |
|---|---|---|
| `falsified` claim | fails | fails |
| `unknown` claim, not accepted | fails | fails |
| `unknown` claim, accepted as risk | fails (shown as unverifiable) | passes, named in the row |
| `skipped` (unverifiable) claim | fails | passes, informational |
| unresolved global name | fails | fails |
| silently-unenforced declared domain | fails | passes, informational |
| [locked](lock.md) function whose body changed | fails, record untouched | fails, record untouched |
| lock removed outside `mathema unlock` | fails | fails |
| acceptance the [policy](pin.md#project-policy) rejects | fails | fails |

A falsified claim fails in every mode: the record keeps the
counterexample permanently (refutation is knowledge), but knowledge of
a broken claim is exactly what a gate is for. An unknown claim also
fails in every mode; in an agentic loop a claim nobody could
adjudicate is indistinguishable from one that would have failed, until
a human explicitly owns the gap with
[`mathema accept --as risk`](accept.md). Accepted risk is visible
relaxation, not laundering: `--lenient` proceeds past it (the row still
names it), strict mode still refuses it.

Freshness never bypasses the gate: a function whose `form` hash is
unchanged skips re-adjudication, but its *stored* verdicts are still
checked, a record carrying a falsified or open-unknown claim fails
the run even when nothing was re-run.

Exit codes: 0 clean; 1 gate failure; 2 usage/target/store error;
130 interrupted.

## Worked example

Continuing from [`mathema check`](check.md)'s `softmax` example, with
its record written by `write_spec()`:

```
$ mathema verify --root .
ok   functions.softmax: form changed; 2 hold, 0 refuted
0 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
```

Drop the normalization on purpose (`return exps` instead of dividing
by the total) and re-run:

```
$ mathema verify --root .
FAIL functions.softmax: form changed; 1 hold, 1 refuted  <- 1 falsified claim(s)
0 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
```

`sums_to_one` is correctly `falsified`, the counterexample is kept in
the record, and the exit code is 1. Restore the fix and re-verify:

```
$ mathema verify --root .
ok   functions.softmax: form changed; 2 hold, 0 refuted
0 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
```

Back to clean, and the baseline is refreshed; the next `verify` will
be fresh again until the code or the claim set actually changes.

## Unknown claims and accepted risk

A claim neither route could decide stays `unknown` and fails the run:

```
$ mathema verify --root .
FAIL functions.running_total: no baseline record; 0 hold, 0 refuted, 1 unknown  <- 1 unknown claim(s)
```

The ways out are real evidence (rewrite the claim or the code so a
route can decide it) or an explicit human decision to own the gap:

```
$ mathema accept functions.running_total never_overshoots_much --as risk \
      --note "loop shape is out of derive scope; monitored"
$ mathema verify --root . --lenient
ok   functions.running_total: form changed; 0 hold, 0 refuted, 1 accepted risk
```

Strict mode (the default) still refuses the accepted risk; it shows
up as an unverifiable claim, so a pipeline can choose whether owned
gaps block it. See [`mathema accept`](accept.md).

## `--status`: the fresh/stale report

`mathema verify --status` is the report-only face (the old standalone
`status` verb): one fresh/stale line per `@mathema.track_claims`-tagged
function, no adjudication, always exit 0. "Fresh" means the function's
current identity hash matches its last verified record; "stale" means
it changed since. Pass a target (`mathema verify --status pkg.mod` or
a file path) to import it first, so a script's own tagged functions
register under their real dotted keys:

```python
@mathema.track_claims
def my_fn(x: float) -> float:
    ...
```

## Mixed-grammar claims files

A declared-claims file/key can legitimately mix grammars, a core
`mathema` claim sitting next to a claim in some other grammar (tagged
`grammar: mathema-data`, say) under the same key. `verify` correctly
distinguishes a foreign-grammar claim from a genuine failure: it's
reported on its own, non-fatal line (`N not this grammar
(mathema-data)`), not counted toward strict-mode failure. The sweep's
closing lines name every grammar seen across the whole run versus what
this particular command actually verifies, `verify` never adjudicates
a foreign-grammar claim itself, whatever module owns that grammar; that
needs real data/context a static sweep can't provide.
