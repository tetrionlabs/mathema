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
importing from `--root`; the target must be importable there, and a
bare-name key fails as a clear per-key problem line.

## What fails the run

| Finding | Default (strict) | `--lenient` |
|---|---|---|
| `falsified` claim | fails | fails |
| `invalidated` claim (held before, fails now) | fails | fails |
| `unknown` claim, not accepted | fails | fails |
| `unknown` claim, accepted as risk | fails (`N accepted-risk claim(s)`) | passes, named in the row |
| `skipped` (unverifiable) claim | fails | passes, informational |
| unresolved global name | fails | fails |
| silently-unenforced declared domain | fails | passes, informational |
| record whose function no longer resolves | fails (names the rename when an unrecorded function has its form hash) | fails |
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

Continuing from [`mathema check`](check.md)'s `softmax` example:

<!-- example: sweep file=functions.py -->
```python
import math
from typing import Annotated
from mathema.types import Shape

def softmax(scores: Annotated[list, Shape("n")]) -> Annotated[list, Shape("n")]:
    """Turn a vector of real-valued scores into a probability distribution.

    Claims:
        sums_to_one: sum(f(scores)) == 1
    """
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]
```

with its record written by `write_spec()`:

<!-- example: sweep run -->
```python
import mathema
from functions import softmax

mathema.write_spec(softmax)
```

<!-- example: sweep session -->
```
$ mathema verify --root .
ok   functions.softmax: fresh
1 fresh (form unchanged, skipped), 0 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Drop the normalization on purpose (`return exps` instead of dividing
by the total):

<!-- example: sweep file=functions.py -->
```python
import math
from typing import Annotated
from mathema.types import Shape

def softmax(scores: Annotated[list, Shape("n")]) -> Annotated[list, Shape("n")]:
    """Turn a vector of real-valued scores into a probability distribution.

    Claims:
        sums_to_one: sum(f(scores)) == 1
    """
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    total = sum(exps)
    return exps
```

and re-run:

<!-- example: sweep session -->
```
$ mathema verify --root .
FAIL functions.softmax: form changed; 1 proven, 1 holds, 0 falsified, 1 invalidated  <- 1 invalidated claim(s)
0 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

`sums_to_one` now fails, and because it held before it is reported
as `invalidated` rather than `falsified`; the counterexample is kept
in the record, and the exit code is 1. Restore the fix (the first
version of `functions.py` above) and re-verify:

<!-- example: sweep file=functions.py -->
```python
import math
from typing import Annotated
from mathema.types import Shape

def softmax(scores: Annotated[list, Shape("n")]) -> Annotated[list, Shape("n")]:
    """Turn a vector of real-valued scores into a probability distribution.

    Claims:
        sums_to_one: sum(f(scores)) == 1
    """
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]
```

<!-- example: sweep session -->
```
$ mathema verify --root .
ok   functions.softmax: form changed; 1 proven, 2 holds, 0 falsified
0 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Back to clean, and the baseline is refreshed; the next `verify` will
be fresh again until the code or the claim set actually changes.

## Unknown claims and accepted risk

A claim neither route could decide stays `unknown` and fails the run.
Add a running balance in `balances.py`, with three claims in a claims
file:

<!-- example: sweep file=balances.py -->
```python
def running_total(xs: list, y0: float) -> float:
    """Add every value in xs to a starting balance y0."""
    total = y0
    for v in xs:
        total = v + total
    return total
```

<!-- example: sweep file=running_total.claims.yaml -->
```yaml
balances.running_total:
  claims:
    - name: shifts_with_start
      statement: "f(xs, y0) == f(xs, 0) + y0"
    - name: nonneg_for_nonneg_steps
      statement: "for xs in [0, 1]^n, f(xs, 0) >= 0"
    - name: never_overshoots_much
      statement: "assuming nonneg_for_nonneg_steps is proven, for xs in [0, 1]^n, f(xs, 0) <= len(xs)"
```

`never_overshoots_much` rests on `nonneg_for_nonneg_steps` being
proven, and that one only holds (the probe agrees; derive cannot settle
the sign of the lifted sum), so the dependent claim is `unknown`.
`shifts_with_start` proves on the derive route, and every proof spawns
a `shifts_with_start[float]` companion, the same law checked in
floating point (see
[the evidence ladder](../evidence-ladder.md#a-proof-is-the-mathematics-float-is-the-code)),
which holds. The second proven claim in the count is
`dependencies_current`, which `verify` adds to every record:

<!-- example: sweep session -->
```
$ mathema verify --root .
FAIL balances.running_total: no baseline record; 2 proven, 2 holds, 0 falsified, 1 unknown  <- 1 unknown claim(s)
ok   functions.softmax: fresh
1 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

The ways out are real evidence (rewrite the claim or the code so a
route can decide it) or an explicit human decision to own the gap
(`--yes` here answers the confirmation prompt). Naming the key
re-checks it, so the row counts the accepted claim:

<!-- example: sweep session -->
```
$ mathema accept balances.running_total never_overshoots_much --as risk --note "the premise only holds empirically; monitored" --by "Charles Babbage" --yes
accepting balances.running_total :: never_overshoots_much (verdict unknown) as risk, by Charles Babbage
  - reclassify never_overshoots_much: unknown -> skipped:unknown_but_accepted (strict mode still refuses it; lenient proceeds)
written: reclassify never_overshoots_much: unknown -> skipped:unknown_but_accepted (strict mode still refuses it; lenient proceeds)
$ mathema verify balances.running_total --root . --lenient
ok   balances.running_total: targeted re-verify; 2 proven, 2 holds, 0 falsified, 1 accepted risk
0 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Strict mode (the default) still refuses the accepted risk, so a
pipeline can choose whether owned gaps block it:

<!-- example: sweep session -->
```
$ mathema verify balances.running_total --root .
FAIL balances.running_total: targeted re-verify; 2 proven, 2 holds, 0 falsified, 1 accepted risk  <- 1 accepted-risk claim(s)
0 fresh (form unchanged, skipped), 1 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

See [`mathema accept`](accept.md).

## Moved functions

A record is keyed by the function's dotted name, so a function moved to
another module leaves its record under a key that no longer resolves,
and that key fails the run. Move `running_total` from `balances.py` to
`ledger.py`, and rename its claims file stanza to match:

<!-- example: sweep run -->
```bash
mv balances.py ledger.py
```

<!-- example: sweep file=running_total.claims.yaml -->
```yaml
ledger.running_total:
  claims:
    - name: shifts_with_start
      statement: "f(xs, y0) == f(xs, 0) + y0"
    - name: nonneg_for_nonneg_steps
      statement: "for xs in [0, 1]^n, f(xs, 0) >= 0"
    - name: never_overshoots_much
      statement: "assuming nonneg_for_nonneg_steps is proven, for xs in [0, 1]^n, f(xs, 0) <= len(xs)"
```

When the orphan's form hash matches a function that has no record, the
failure line says so and names the exact remedy, and the new key is
held back rather than given a fresh record that would start its
history over:

<!-- example: sweep session -->
```
$ mathema verify --root .
FAIL balances.running_total: cannot resolve to a live function (declared in .mathema/verified/balances.running_total.yaml); its form hash matches ledger.running_total, which has no record. If it moved, a human keeps its history with: mathema accept ledger.running_total --as reconciled --from balances.running_total
FAIL ledger.running_total: no record yet, and its form hash matches the orphan record balances.running_total; nothing was adjudicated or written for this key. If it moved, a human keeps its history with: mathema accept ledger.running_total --as reconciled --from balances.running_total; if it is a different function, remove the orphan record instead
ok   functions.softmax: fresh
1 fresh (form unchanged, skipped), 0 adjudicated, 2 problem(s)
grammars detected: mathema; verified by this run: mathema
```

The rename carries the whole record (claims, acceptances and their
history, lineage, PIN stamp, lock) to the new key and removes the old
file; see [moved functions](accept.md#moved-functions-as-reconciled-from).
The project's source is parsed, never imported, to find the match, and
only when an orphan exists. In `--format json` the orphan's entry
carries `moved_to` and `remedy`, and the held-back key has `why:
"moved-pending"` with `moved_from` and `remedy`.

## A record's history

A claim row's `meta` keeps `mathema.previous_verdict` when its verdict
changes: one step, the verdict immediately before this one. There is no
history field, because the verified layer is committed to git and git
is the history. `mathema review [<ref>]` reads it by claim (which
verdicts flipped, which claims were added, removed or reconciled), and
`git log .mathema/verified` lists every commit that changed a record.

## `--status`: the fresh/stale report

`mathema verify --status` is the report-only face: one fresh/stale line per `@mathema.track_claims`-tagged
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
