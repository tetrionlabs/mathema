# Gate a pipeline with mathema verify

This guide wires `mathema verify` into a pipeline so that a pull request
fails on a falsified or undecided claim and passes on a clean store. It
assumes you have written a claim before ([quick start](quickstart.md)) and
know what a record is ([the CDD loop](tutorial.md)).

The running example is the fees module of a billing service from [Add
claims to an existing codebase](existing-codebase.md), as a later commit
left it: the late fee now grows with the log of the delay, which brings
in `math.log`, and the discount has a bug in it.

<!-- example: gate file=fees.py -->
```python
import math


def late_fee(days: int, base: float) -> float:
    """The fee for a payment that is `days` late."""
    return base * math.log(1 + days)


def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate."""
    return price * (1 + rate)
```

<!-- example: gate file=claims/fees.claims.yaml -->
```yaml
fees.late_fee:
  claims:
    - name: grows_with_delay
      statement: "for days in [0, 365] subset Z, base in [1, 100], f(days + 1, base) >= f(days, base)"
fees.discounted:
  claims:
    - name: never_raises_price
      statement: "for price in [0, 1e6], rate in [0, 1], f(price, rate) <= price"
```

## 1. Write the workflow

`mathema init --ci` writes the GitHub Actions workflow (`--ci gitlab`
writes a GitLab fragment and the `include:` line to add). It is written
only where absent, and it is yours to edit from then on.

<!-- example: gate run -->
```bash
mathema init --ci
cat .github/workflows/mathema-verify.yml
```

<!-- example: gate output -->
```text
mathema init: scaffolded git files:
  .gitattributes
  .mathema/.gitignore
mathema init: scaffolded the CI gate:
  .github/workflows/mathema-verify.yml
# mathema verify is the CI gate over the committed .mathema/ store: it
# re-adjudicates whatever changed and gates the result. verify is
# STRICT by default, which fails a falsified claim, an open unknown
# one, AND a claim that could not be checked at all (an unreachable
# surface, an unsupported shape). Most stores have some of the last
# kind at first, so expect the first run to be red and to tell you
# exactly which claims it means. Add --lenient to report those
# unverifiable claims and accepted risk without failing, and keep
# strict for falsified and unknown, once you have decided each one is
# understood. Exit codes: 0 clean, 1 gate failure, 2 broken invocation
# or store, so a failing gate is distinguishable from a broken job
# without parsing any output.
name: mathema
on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      # your project must import for its claims to adjudicate; adjust
      # this line to however your project installs
      - run: pip install -e . mathema
      - run: mathema verify --root .
      # optional: the claim-level delta since the base, for a PR comment
      # - run: mathema review --format json --output review.json
```

The one line you will change is the install step: your project has to
import for its claims to adjudicate, so it is installed the way your
project installs.

## 2. Commit the store

`init` also wrote `.gitattributes`, which marks the records
`linguist-generated` so their diff collapses by default, and
`.mathema/.gitignore`, which tracks `verified/`, `meta/` and `badges/`
and ignores regenerated state. Commit `.mathema/` with the code. The
workflow's `mathema verify --root .` reads that store: a record is the
durable statement of what was checked, and the next run needs it as its
baseline.

## 3. Read the first red run

Run the gate locally before the pipeline does. The last line prints the
exit code the job would see:

<!-- example: gate run -->
```bash
mathema verify --root .; echo "exit code $?"
```

<!-- example: gate output wrap=80 -->
```text
note fees.discounted: never_raises_price falsified on first adjudication. A
    declared claim is kept until a human decides it:
  (i) fix the code
  (ii) to record it as a discovery, run: mathema accept fees.discounted <claim>
      --as discovery
  (iii) supersede it
  (iv) to try a spelling first (it writes nothing), run: mathema check
      fees.discounted --claim "..."
FAIL math.log: library claims from mathema/compendium/math.claims.yaml; no
    baseline record; 1 proven, 0 holds, 0 falsified, 1 unknown  <- log_monotone
    unknown: derive route unliftable
       compendium:math declares 'log_monotone' for math.log; mathema verify
           recorded it unknown against the installed library:
       (i) to take it on its word, run: mathema accept math.log log_monotone
           --as trusted
       (ii) to decide it, restate the row, then run: mathema check math.log
           --claim "..."
FAIL fees.discounted: no baseline record; 1 proven, 0 holds, 1 falsified  <- 1
    falsified claim(s)
ok   fees.late_fee: no baseline record; 1 proven, 2 holds, 0 falsified
0 fresh (form unchanged, skipped), 3 adjudicated, 2 problem(s)
grammars detected: mathema; verified by this run: mathema
exit code 1
```

Three keys were adjudicated, and two of them fail the gate.

- `fees.discounted` is falsified: the bug. The `note` above it says what
  a declared claim does when it fails on first adjudication: it is kept,
  with its counterexample, until a person decides whether the code or the
  claim was wrong.
- `math.log` is a function nobody on the team wrote. `late_fee` calls it,
  so the sweep adjudicated the claims mathema ships about it, and one of
  them, `log_monotone`, a derivative claim, is recorded `unknown`:
  `math.log` is a C function with no Python body for the derive route to
  lift, and the probe route does not evaluate `d(f(x), x)` by calling the
  function (`probe: skipped (unrecognized call 'd' ...)` in the record).
  An unknown claim fails the gate in every mode.
- `fees.late_fee` passes. The `1 proven` in every row is
  `dependencies_current`, the claim `verify` adds to each record that
  what the function depends on has not moved.

## 4. Decide about the row nobody wrote

An `unknown` on a library row is a decision for the team, not a flag to
set, and `--lenient` does not pass it. Two acceptances are available, and
the failure line named the first:

- `--as trusted` takes the compendium's word for the row at the level it
  claims. It is testimony, recorded as such, and a later sweep that can
  settle the row locally replaces it with a local verdict.
- `--as risk` records that the team owns the gap, with a note, and keeps
  the row visible in every report; strict mode still refuses it.

For a row mathema ships about a library you did not write, trusting it
is the usual decision. `--yes` answers the confirmation prompt, which is
acceptable when a person is typing the command and never in agent
tooling:

<!-- example: gate run -->
```bash
mathema accept math.log log_monotone --as trusted --by "Grace Hopper" --yes
mathema verify --root .; echo "exit code $?"
```

<!-- example: gate output wrap=80 -->
```text
accepting math.log :: log_monotone (verdict unknown) as trusted, by Grace Hopper
  - trust log_monotone at its claimed level (holds), on the word of
      compendium:math; `mathema verify` re-adjudicating this key replaces the
      testimony with a local verdict
written: trust log_monotone at its claimed level (holds), on the word of
    compendium:math; `mathema verify` re-adjudicating this key replaces the
    testimony with a local verdict
ok   math.log: fresh; library claims from mathema/compendium/math.claims.yaml
FAIL fees.discounted: fresh; 1 falsified claim(s)
ok   fees.late_fee: fresh
3 fresh (form unchanged, skipped), 0 adjudicated, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
exit code 1
```

Nothing was re-adjudicated: every form hash is unchanged, so the sweep
reads the stored verdicts, and the stored falsification still fails.

## 5. Fix the code, not the gate

There is no accepting a falsified claim as risk. The discount adds the
rate instead of subtracting it; fix it, and the changed form hash makes
the sweep re-adjudicate that one function:

<!-- example: gate file=fees.py -->
```python
import math


def late_fee(days: int, base: float) -> float:
    """The fee for a payment that is `days` late."""
    return base * math.log(1 + days)


def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate."""
    return price * (1 - rate)
```

<!-- example: gate run -->
```bash
mathema verify --root .; echo "exit code $?"
```

<!-- example: gate output -->
```text
ok   math.log: fresh; library claims from mathema/compendium/math.claims.yaml
ok   fees.discounted: form changed; 2 proven (1 claim, 1 built-in), 3 holds, 0 falsified
ok   fees.late_fee: fresh
2 fresh (form unchanged, skipped), 1 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
exit code 0
```

The claim is now proven, the lines under it hold (the floating-point
computation, and what `discounted` does with a `nan` price or rate), and
the gate is green. Had the claim been the wrong one rather than the code,
`mathema accept ... --as discovery` records the corrected claim instead;
[the CDD loop](tutorial.md) walks that fork.

## 6. Strict or lenient

`verify` is strict by default: falsified, invalidated and unknown claims
fail, and so do claims that could not be checked at all (`skipped`) and
gaps a person has accepted as risk. `--lenient` reports the last two by
name and proceeds; it never passes a falsified or an unaccepted unknown
claim. The full table is on [`mathema verify`](modes/verify.md#what-fails-the-run).

Keep the default. Decide each red claim, `accept --as risk` for a gap the
team owns and `--as trusted` for a library row, and add `--lenient` only
once every skipped or accepted-risk claim has been decided, so that a new
one still stops the pipeline.

## 7. Tell a failing gate from a broken job

Every verb exits 0 when nothing gated, 1 when the gate failed, 2 when
mathema could not run, and 130 when interrupted. A 2 is not a finding
about your code:

<!-- example: gate run -->
```bash
mathema verify fees.nosuch --root .; echo "exit code $?"
```

<!-- example: gate output -->
```text
mathema: no such key under .: fees.nosuch (nothing to verify)
exit code 2
```

Keep the two apart in the job: a step that treats any non-zero exit as a
failing claim hides a broken install or a mistyped key as a bug. The codes
are listed on [Verdicts and exit codes](verdicts.md#exit-codes).

## 8. The claim-level delta on the pull request

The workflow's last, commented line is optional: `mathema review
--format json --output review.json` compares the records at the base ref
with the working tree and reports which verdicts flipped and which claims
were added, removed or newly falsified, as data a job can post as a
comment. [`mathema review`](modes/review.md) has the worked example.
