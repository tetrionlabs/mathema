# See what mathema knows about a library you call

Your function calls numpy. mathema ships claims about numpy's functions,
and when it sweeps your code it also adjudicates those claims for the
calls your code makes, against the numpy you have installed. This guide
shows how to see which of your calls are covered, which are not, and how
to state a claim about a call nothing covers. It assumes [the CDD
loop](tutorial.md).

The running example is a risk module with three functions, each with one
claim of its own:

<!-- example: library file=risk.py -->
```python
import numpy as np


def volatility(returns: np.ndarray) -> float:
    """Annualised volatility of daily returns."""
    return float(np.std(returns, ddof=1) * np.sqrt(252))


def value_at_risk(returns: np.ndarray) -> float:
    """The loss not exceeded on 95 percent of days, as a positive number."""
    return float(-np.percentile(returns, 5))


def spread(returns: np.ndarray) -> float:
    """The distance between the best and the worst day."""
    return float(np.ptp(returns))
```

<!-- example: library file=claims/risk.claims.yaml -->
```yaml
risk.volatility:
  claims:
    - name: nonneg
      statement: "for returns in [-0.1, 0.1]^n, assuming dim(returns) >= 2, f(returns) >= 0"
risk.value_at_risk:
  claims:
    - name: within_the_worst_day
      statement: "for returns in [-0.1, 0.1]^n, f(returns) <= -min(returns)"
risk.spread:
  claims:
    - name: nonneg
      statement: "for returns in [-0.1, 0.1]^n, f(returns) >= 0"
```

## 1. Ask what is known

<!-- example: library run requires=numpy -->
```bash
mathema compendium status --root .
```

<!-- example: library output -->
```text
numpy 2.5.3: 4 calls
  claims files:
    mathema/compendium/numpy/bounds.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/definitions.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/definitions_2_4.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/elementwise.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/linalg.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/linalg_2_4.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/reductions.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/scalars.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/statistics.claims.yaml (bundled, >=1.24,<3, in range)
  numpy.percentile  1 call, 1 row: 0 verified locally, 0 trusted, 0 falsified, 1 unsettled
  numpy.sqrt        1 call, 2 rows: 0 verified locally, 0 trusted, 0 falsified, 2 unsettled
  numpy.std         1 call, 3 rows: 0 verified locally, 0 trusted, 0 falsified, 3 unsettled
  no claims: numpy.ptp

(standard library calls are left out)
```

One block per library, headed by its installed version and the number of
calls, a call counted once per function that makes it. The claims files
are the ones mathema ships for numpy: a compendium is a claims file whose
keys are a library's functions rather than your own, with the range of
library versions it applies to, and each file is in range for the numpy
installed here. Then each called function that has rows, with how many
are settled: none yet, since nothing has run. `numpy.ptp` has no rows at
all, so what it does under your inputs is a black box to mathema until
someone states a claim about it.

## 2. Sweep

`mathema verify` adjudicates the rows for the library functions your
code calls, and only those, against the installed library. A project
that never calls numpy verifies none of numpy's rows.

<!-- example: library run requires=numpy -->
```bash
mathema verify --root .
```

<!-- example: library output -->
```text
ok   numpy.percentile: library claims from mathema/compendium/numpy/statistics.claims.yaml; no baseline record; 1 proven, 1 holds, 0 falsified
ok   numpy.sqrt: library claims from mathema/compendium/numpy/scalars.claims.yaml; no baseline record; 1 proven, 2 holds, 0 falsified
ok   numpy.std: library claims from mathema/compendium/numpy/reductions.claims.yaml; no baseline record; 1 proven, 3 holds, 0 falsified
ok   risk.spread: no baseline record; 1 proven, 1 holds, 0 falsified
ok   risk.value_at_risk: no baseline record; 1 proven, 1 holds, 0 falsified
ok   risk.volatility: no baseline record; 1 proven, 1 holds, 0 falsified
0 fresh (form unchanged, skipped), 6 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Each library row now has a record of its own under `.mathema/verified/`,
named by the file it came from. The `1 proven` on every line is
`dependencies_current`, the claim `verify` adds to each record that what
the function depends on has not moved.

## 3. Ask again

<!-- example: library run requires=numpy -->
```bash
mathema compendium status --root .
```

<!-- example: library output match=subset -->
```text
numpy 2.5.3: 4 calls
  numpy.percentile  1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.sqrt        1 call, 2 rows: 2 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.std         1 call, 3 rows: 3 verified locally, 0 trusted, 0 falsified, 0 unsettled
  no claims: numpy.ptp
```

Verified locally means proven or holding in this project's store, on
this machine's numpy. The gap is unchanged.

## 4. State what you rely on

A compendium file of your own closes the gap. It sits with your other
claims files, names the library and the versions the row applies to, and
its keys are the library's functions with the library's own parameter
names (`numpy.ptp` takes `a`):

<!-- example: library file=claims/numpy.claims.yaml -->
```yaml
compendium: numpy
versions: ">=2,<3"

numpy.ptp:
  claims:
    - name: range
      statement: "for a in [-100, 100]^n, f(a) == max(a) - min(a)"
      route: probe
```

`route: probe` asks for the row to be checked by running the function,
since `ptp` hands its array to a compiled routine the derive route cannot
read. The next sweep adjudicates the new row and nothing else, every
other record being fresh:

<!-- example: library run requires=numpy -->
```bash
mathema verify --root .
```

<!-- example: library output match=subset -->
```text
ok   numpy.ptp: library claims from claims/numpy.claims.yaml; no baseline record; 1 proven, 1 holds, 0 falsified
6 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
```

<!-- example: library run requires=numpy -->
```bash
mathema compendium status --root .
```

<!-- example: library output -->
```text
numpy 2.5.3: 4 calls
  claims files:
    mathema/compendium/numpy/bounds.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/definitions.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/definitions_2_4.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/elementwise.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/linalg.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/linalg_2_4.claims.yaml (bundled, >=2.4,<3, in range)
    mathema/compendium/numpy/reductions.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/scalars.claims.yaml (bundled, >=1.24,<3, in range)
    mathema/compendium/numpy/statistics.claims.yaml (bundled, >=1.24,<3, in range)
    claims/numpy.claims.yaml (project, >=2,<3, in range)
  numpy.percentile  1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.ptp         1 call, 1 row: 1 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.sqrt        1 call, 2 rows: 2 verified locally, 0 trusted, 0 falsified, 0 unsettled
  numpy.std         1 call, 3 rows: 3 verified locally, 0 trusted, 0 falsified, 0 unsettled

(standard library calls are left out)
```

Your file is listed beside the bundled ones as `project`, and `ptp` has
left the `no claims` line. A key in your file that a bundled file also
states shadows the bundled entry for that function.

## 5. When a row cannot be settled here

A row `verify` cannot settle against the installed library is recorded
`unknown` or `skipped`, and it fails the gate like any other. The
decision is the team's: `mathema accept KEY CLAIM --as trusted` takes the
compendium's word for the row at the level it claims, as testimony a
later local verdict replaces, and `--as risk` records that the team owns
the gap. [Gate a pipeline with mathema verify](gate-a-pipeline.md#4-decide-about-the-row-nobody-wrote)
walks through one, and [`mathema accept`](modes/accept.md#-as-trusted)
has the exact semantics.

## Behind this page

- [Claims transfer](claims-transfer.md#in-the-compendium) is the
  reference for compendium files: the header fields, aliases, per-row
  version ranges, how defaults are held, and the two kinds of row.
- [`mathema compendium`](modes/compendium.md) has `update`, which drafts
  rows for the calls your project makes, and `export`, for publishing a
  library's own verified claims.
- [`mathema verify`](modes/verify.md#library-claims-lazy-by-default-a-file-up-front)
  explains the lazy sweep and how to adjudicate a whole claims file up
  front.
