# `mathema coverage`

Implementation coverage: the share of each function's own statements that
some evidence has exercised. Three sources count, and their union is the
score: a test run that executed the line, read from a coverage report that
already exists; a mathema probe that executed it while checking the
function; and a proof of a claim included for the function, which counts
the lines the proof modelled (the whole body, unless the proof was over
part of the domain and names its branches). A proof is one on the derive
route or one from the function's structure (the examine route).

A claim is included when it is declared on the function (a docstring or
decorator claim), when it sits in a claims file, or when it is a
suggestion you adopted into a claims file or accepted with `mathema
accept --as evidence`. Wherever it lives, a claim counts only once it
has a verified record (`mathema verify`, or `write_spec` for a claim in a
docstring): the coverage run's own proof never counts until then, so
coverage never certifies itself. The standard claims `coverage` checks
while tracing, and suggestions nobody adopted, never count as proofs.

```bash
mathema coverage [targets] [--root .]
mathema coverage --stamp [--root .]
mathema coverage [targets] --run-tests
```

Omit the targets to cover every function the store knows under `--root`,
the rootwide analogue of `verify`. This is a separate pass, never part of
`check`, and needs no third-party dependency: the probe source traces
with the standard library and the statement count comes from the `ast`
module. The `coverage` extra is needed only to read a native `.coverage`
report; a `coverage.json` export is read without it.

## Arguments

| Flag | Meaning |
|---|---|
| `targets` | importable module or package names; omit for every function the store knows |
| `--root ROOT` | project root holding `.mathema/` and any coverage report to merge |
| `--stamp` | record the content hash of every source file the existing report measured, so its freshness is judged by content rather than file times; run it after the tests that produced the report |
| `--run-tests` | first re-run the project's tests under coverage to refresh the test source; needs the `coverage` extra |

## One line per function

Each function gets one line: the percentage, the key, the sources that
covered it in brackets and, below 100, the one action that would raise
the score most. The running example is a ledger: a settlement function
with a `gross` mode, and a running total with a proven claim.

<!-- example: cov file=ledger.py -->
```python
def settle(exposure: float, mode: str = "net") -> float:
    """The settlement amount for a signed exposure.

    Claims:
        nonneg: f(exposure, "net") >= 0
    """
    amount = abs(exposure)
    if mode == "gross":
        return amount * 1.5
    return amount


def running_total(xs: list, y0: float) -> float:
    """Add every value in xs to a starting balance y0.

    Claims:
        shifts_with_start: f(xs, y0) == f(xs, 0) + y0
    """
    total = y0
    for v in xs:
        total = v + total
    return total
```

A proof counts only once the claim has a verified record, so record the
two docstring claims first (`mathema verify` then keeps the records
current):

<!-- example: cov run requires=coverage -->
```python
import mathema
from ledger import running_total, settle

for fn in (running_total, settle):
    mathema.write_spec(fn)
```

<!-- example: cov run -->
```bash
mathema coverage ledger --root .
```

<!-- example: cov output -->
```text
100%  ledger.running_total  [probe+derive]
 75%  ledger.settle  [probe]  -> add a claim or test exercising line(s) 9

implementation coverage: 88%
```

`running_total` is covered twice over: the probe ran every line while
checking `shifts_with_start`, and the claim, recorded and proved on the
derive route, counts the whole body. `settle` is at 75%: nothing that ran the
function passed `"gross"`, so line 9 was never reached, and the remedy
names the line. The project figure is weighted by statements, not
averaged over functions.

## The test source

The tests you already run count too. mathema reads a coverage report that
exists at the root, `coverage.json` first, then a native `.coverage`, and
never runs your tests unless you ask with `--run-tests`. A test of the
`gross` mode, run under coverage, reaches line 9:

<!-- example: cov file=test_ledger.py -->
```python
from ledger import settle


def test_gross_settlement():
    assert settle(-100.0, "gross") == 150.0
```

<!-- example: cov run -->
```bash
python -m coverage run -m pytest -q test_ledger.py
python -m coverage json -q
mathema coverage ledger --root .
```

<!-- example: cov output match=subset -->
```text
1 passed in 0.02s
100%  ledger.running_total  [probe+derive]
100%  ledger.settle  [test+probe]

implementation coverage: 100%
test report freshness: by file modification time (to judge by content, after the tests run: mathema coverage --stamp)
```

## When a report stops counting

A report keys its lines by line number, so once a source file changes
those lines can point at the wrong statements. A stale file's lines are
left out of the score and reported as reclaimable by a re-run of the
tests. Freshness is judged per source file in one of two ways, and the
last line of the report says which:

- **by file modification time**, when there is no stamp: a file is stale
  when it was modified after the report was written. That is reliable
  only on the machine that ran the tests, because a checkout resets file
  times.
- **by content hash**, once the report is stamped: `coverage.sources.json`
  beside the report holds the sha256 of every file it measured and of the
  report itself, so a file's lines count exactly while its content still
  matches, in a fresh checkout or a CI artifact as much as here. A stamp
  written for a different report is ignored.

<!-- example: cov run -->
```bash
mathema coverage --stamp --root .
```

<!-- example: cov output -->
```text
stamped coverage.sources.json: the report's freshness is now judged by each source file's content hash
```

Add a flat fee to `ledger.py` and the report is stale for that file:

<!-- example: cov file=ledger.py -->
```python
def settle(exposure: float, mode: str = "net") -> float:
    """The settlement amount for a signed exposure.

    Claims:
        nonneg: f(exposure, "net") >= 0
    """
    amount = abs(exposure)
    if mode == "gross":
        return amount * 1.5
    return amount


def running_total(xs: list, y0: float) -> float:
    """Add every value in xs to a starting balance y0.

    Claims:
        shifts_with_start: f(xs, y0) == f(xs, 0) + y0
    """
    total = y0
    for v in xs:
        total = v + total
    return total


def fee(x: float) -> float:
    """A flat fee."""
    return 2.0
```

<!-- example: cov run -->
```bash
mathema coverage ledger --root .
```

<!-- example: cov output -->
```text
100%  ledger.fee  [probe]
100%  ledger.running_total  [probe+derive]
 75%  ledger.settle  [probe]  -> re-run tests: reclaims +25% (stale coverage report)

implementation coverage: 89%
(up to 100% after re-running the tests)
test report freshness: by content hash (coverage.sources.json)
```

The test lines for `settle` are not lost, only set aside until the tests
run again. `--run-tests` does that in one step: it re-runs the tests
under coverage, combines the data files a parallel or subprocess run
leaves behind, exports the report and stamps it. A report made by another
tool, `pytest --cov` in CI for example, needs `mathema coverage --stamp`
run once afterwards in the same tree.

## Where the number goes

The project figure is the implementation corner of
[`mathema badges`](badges.md), and the MCP tool `implementation_coverage`
returns the same per-function rows to an agent. mathema's own functions
get no probe source when mathema measures itself, since a probe's lines
cannot be told apart from the machinery's; test and derive lines still
count.
