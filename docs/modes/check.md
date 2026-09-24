# `mathema check`

One-off interactive verification of a single function, module, or
package against its built-in laws and any inline `--claim`s, the way
you'd use mathema from a notebook. Lenient by default.

```bash
mathema check pkg.mod:fn [--claim "f(-x) == -f(x)"]
mathema check path/to/file.py:fn [--claim "..."]
```

## Arguments

| Flag | Meaning |
|---|---|
| `target` | a dotted name (`pkg.mod`, `pkg.mod.fn`, `pkg.mod:fn`) or a file path (`file.py`, `file.py:fn`); files import with real package context, so relative imports inside them work, and report keys are always the canonical dotted `module.qualname` |
| `--root` | project root to import dotted targets relative to (default `.`) |
| `--claim LAW` | ad-hoc claim to adjudicate, e.g. `"f(-x) == -f(x)"` (repeatable) |
| `--domain name=lo:hi` | declared parameter range (repeatable) |
| `--strict` / `--lenient` | one strictness pair shared with `verify`; lenient is the default here (the authoring loop iterates while claims are still being written); strict additionally counts skipped (unverifiable) claims and accepted risk as failures, a reporting filter over already-computed verdicts, never an adjudication mode |
| `--trials-scale FACTOR` | shrink the trial budget by `FACTOR` (FACTOR > 0) for a faster dev loop; a value above 1 is clamped to 1, so it never scales upward |
| `--format` | `text` (default), `json`, `compact`, `junit`, `github`, `md` |
| `--output FILE` | write the report to a file instead of stdout |

## Report formats

- **`text`**: human-readable, for a terminal.
- **`json`**: for artifacts; includes `tool`/`version`/`CDD_spec_version`/
  `functions`/`totals` fields.
- **`compact`**: the same adjudication as `json`, minified onto one
  line with no envelope: a bare array of one object per function
  (`key`, `passed`, `problems`, `claims`). Each claim row carries
  `stance`, `verdict`, `route`, `source`, `gates`, `reason`, and its
  `evidence.n`, plus a `counterexample` when there is one. Built for a
  program reading the result rather than a human or a CI widget, and
  the closest CLI equivalent of what the [MCP](mcp.md) tools return,
  so an agent that shells out and one that calls a tool see the same
  shape. Note `source` and `gates`: a suggested claim appears in the
  rows but has `gates: false` and never affects the exit code, so a
  client filtering on `gates` sees exactly what the gate saw.
- **`junit`**: for a GitLab test report widget.
- **`github`**: GitHub Actions annotation format.
- **`md`**: for a CI step summary.

## The trial budget

The probe route's `n` isn't a flat constant. It's decided once per
call, before any law runs, from the target function's own structure:

- **Higher**, from a base of 128 up to a max of 256, for a
  structurally riskier function, more branches, more loops, a wider
  or unbounded declared domain.
- **Lower**, down to 32, only when the derive route can *prove* the
  function is affine (a constant slope in every parameter) *and* the
  declared domain doesn't itself need the extra density, a wide or
  float-precision-risky domain skips the reduction even for a provably
  affine function.

Every verdict reports the exact `n` it used, plus a
`meta["mathema.confidence"]` score (1-4 stars, capped below the derive
route's own 5; sampling evidence is never proof, however extensive)
built from the same structural factors, so a reader can see *why* a
verdict deserves more or less trust without re-deriving it. From the
library, `mathema.check(fn, trials=N)` takes an exact count, with no
adaptivity at all.

`--trials-scale FACTOR` shrinks the whole budget by a flat factor
instead; `0.25` for a much faster dev loop, say, applied to
*everything*, an explicit `trials=N` included, not just the adaptive
default. It only ever shrinks (a value above 1 is accepted but has no
effect; there's no good reason to scale upward when a structurally
riskier function already gets more trials on its own), and it never
drops the budget below a floor that still means something: at least
16 trials, and at least enough to guarantee every special sampled
value (`0`, `±1`, `±1e-9`, `±1e6`, ...) is actually exercised once.
`--trials-scale 0` or a negative value is a clean CLI error, not a
silent 0-trial `holds`.

## Exit code

1 if any row had a problem; 0 otherwise, suitable for a pre-commit
check on a single target. A falsified or unknown claim is a problem in
every mode; `--strict` additionally counts unverifiable (skipped)
claims and a silently-unenforced declared domain. Only claims you
actually stated gate the exit code: standard claims mathema itself
volunteers (see [`mathema claims --suggest`](claims.md)) are shown for
adoption but never fail a run pre-adoption.

```bash
mathema check model.py --domain alpha=0:1 --claim 'excluded_outside_domain(alpha)'
mathema check model.py --format json --output claim-coverage.json
mathema check model.py --format junit --output claims.xml   # GitLab test widget
mathema check model.py --format github                      # Actions annotations
```

Worked pipeline configs for GitHub Actions and GitLab are in
`examples/ci/` in the repo.

## Worked example: softmax, start to finish

```python
# functions.py
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

```
$ mathema check functions.py:softmax --claim "sum(f(scores)) == 1"
ok   functions.softmax: source, no side effects; claims 3/3 adjudicated (0 proven, 3 holds, 0 falsified)
```

Break it on purpose (drop the normalization, `return exps` instead of
dividing by the total) and `sums_to_one` correctly falsifies, the row
fails and the exit code is 1 (see
[CDD in one page](../cdd.md#verdict-vocabulary): the counterexample is
kept as knowledge, *and* the run fails):

```
$ mathema check functions.py:softmax --claim "sum(f(scores)) == 1"
FAIL functions.softmax: source, no side effects; claims 3/3 adjudicated (0 proven, 1 holds, 2 falsified)  <- 2 falsified claim(s)
```

See [mathema verify](verify.md) for the same regression caught from the
CI-sweep angle instead.
