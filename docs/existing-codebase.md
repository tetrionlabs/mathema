---
hide:
  - toc
---

# Add claims to an existing codebase

This guide takes a package with functions, tests and no claims to a
passing `mathema verify`, without rewriting anything. It assumes the
[quick start](quickstart.md), so you have written one claim and seen a
record.

The running example is the fees module of a billing service, three
functions and a small test file:

<!-- example: codebase file=billing/__init__.py -->
```python
"""Fees and settlements for a billing service."""
```

<!-- example: codebase file=billing/fees.py -->
```python
def late_fee(days: int, base: float) -> float:
    """The fee for a payment that is `days` late: one percent of base a day."""
    return base * 0.01 * days


def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate."""
    return price * (1 - rate)


def settle(exposure: float) -> float:
    """The settlement amount for a signed exposure."""
    return abs(exposure)
```

<!-- example: codebase file=test_fees.py -->
```python
from billing.fees import discounted, settle


def test_discounted():
    assert discounted(100.0, 0.25) == 75.0


def test_settle():
    assert settle(-3.0) == 3.0
```

## 1. See where you stand

`mathema audit` gives every function under a package one line: where it
lives, whether it has claims, whether the derive route could prove
things about it, what state outside its parameters it touches, whether a
test report covers it, and how well its docstring states its intent.

<!-- example: codebase run -->
```bash
mathema audit billing --root .
```

<!-- example: codebase output -->
```text
                      ||              || derive route                 || typing                || globals                ||           || docs    ||
key          | span   || claims       || derives | cx | reason | code || typed | finite_domain || vars | mutates | funcs || tested    || quality || docsync
billing.fees
 .discounted | 6:8p   || {11 | 0 | -} || yes     | 1  | -      | -    || yes   | -             || -    | -       | -     || no-report || 4/5     || 26%
 .late_fee   | 1:3p   || {7 | 0 | -}  || yes     | 1  | -      | -    || yes   | -             || -    | -       | -     || no-report || 4/5     || 26%
 .settle     | 11:13p || {9 | 0 | -}  || yes     | 1  | -      | -    || yes   | -             || -    | -       | -     || no-report || 3/4     || 26%

0/3 claimed, 3/3 derivable, 3/3 lift unconditionally, 3/3 fully typed, 11/14 docstring quality criteria met, no coverage.json/.coverage report found, mean docsync 26%.
`derives` is what the derive route can do here, given the domain the signature, docstring and claims declare. The reason/code cells describe the UNCONDITIONAL lift, the body with nothing supplied, so a branch:needs-domain row reads blocked there and derives all the same, once a claim declares the domain that prunes the branch. Neither is a ceiling: a probe claim can still be written and adjudicated for every function here.
```

`0/3 claimed`, and all three could be proven. The `claims` cell reads
`{floor | actual | expected}`: the least a function of this shape gives
you to state (eleven for `discounted`, one per relevant built-in claim and
target), what it states (nothing yet), and what a function of this shape
typically carries (`-`: not known without a corpus). `tested` says
`no-report`: there is no coverage report yet for the tests to count.

## 2. Scaffold the store

`mathema init` writes the git files a tracked store wants and, for each
function with no claims, an empty placeholder in a claims file:

<!-- example: codebase run -->
```bash
mathema init billing --root .
cat claims/billing.fees.claims.yaml
```

<!-- example: codebase output -->
```text
mathema init: scaffolded git files:
  .gitattributes
  .mathema/.gitignore
mathema init: wrote stub entries to:
  claims/billing.fees.claims.yaml
# mathema init: bare declared stubs for billing.fees (fill in claims; an empty list means nothing declared yet)
billing.fees.discounted:
  claims: []
billing.fees.late_fee:
  claims: []
billing.fees.settle:
  claims: []
```

A stub is a task, not a claim. `init` is additive: run it again as the
package grows and it appends keys it has not seen, never touching a
claim you wrote.

## 3. Start from a suggestion

For one function, `mathema claims --suggest` renders the standard claims
mathema would check, each with the route it would take, in three
sections: claims that stand alone, questions with candidate answers
(which way f moves or bends in each parameter), and claims likely to be
unknowable (none here):

<!-- example: codebase run -->
```bash
mathema claims billing.fees.discounted --suggest --root .
```

<!-- example: codebase output match=subset -->
```text
billing.fees.discounted: 17 suggested claim(s) (adopt with: mathema claims KEY --adopt NAME)
 individual claims:
  - commutative: f(price, rate) == f(rate, price)  [route best]
  - associative: f(f(price, rate), c) == f(price, f(rate, c))  [route best]
  - is_deterministic: f(price, rate) == f(price, rate)  [route best]
  - is_state_safe: f(price, rate) == f(price, rate)  [route best]
  - is_numerically_stable: g(f, price, rate) == 1  [route best]
  - is_representation_safe[price]: is_representation_safe(price)  [route examine]
  - is_representation_safe[rate]: is_representation_safe(rate)  [route examine]
 questions with candidate answers (adopt every answer that holds):
  monotonicity[price]:
    - monotonic_increasing[price]: d(f(price, rate), price) >= 0  [route best]
    - monotonic_decreasing[price]: d(f(price, rate), price) <= 0  [route best]
  shape[price]:
    - affine[price]: d(f(price, rate), price, price) == 0  [route best]
    - convex[price]: d(f(price, rate), price, price) >= 0  [route best]
    - concave[price]: d(f(price, rate), price, price) <= 0  [route best]
  monotonicity[rate]:
    - monotonic_increasing[rate]: d(f(price, rate), rate) >= 0  [route best]
    - monotonic_decreasing[rate]: d(f(price, rate), rate) <= 0  [route best]
```

A suggestion is not verified and never gates until someone adopts it. A
higher rate means a lower price, so adopt the one that says so:

<!-- example: codebase run -->
```bash
mathema claims billing.fees.discounted --adopt "monotonic_decreasing[rate]" --root .
cat claims/adopted.claims.yaml
```

<!-- example: codebase output -->
```text
adopted monotonic_decreasing[rate] into ./claims/adopted.claims.yaml: d(f(price, rate), rate) <= 0
billing.fees.discounted:
  claims:
  - name: monotonic_decreasing[rate]
    statement: d(f(price, rate), rate) <= 0
    route: best
    grammar: mathema
```

## 4. Try it before the sweep writes anything

`mathema check` adjudicates a function's claims and writes no record, so
it is the place to find out whether a claim is right before `verify`
keeps it:

<!-- example: codebase run -->
```bash
mathema check billing.fees.discounted --root .
```

<!-- example: codebase output -->
```text
FAIL billing.fees.discounted: source, no side effects; claims 1/1 adjudicated (0 proven, 0 holds, 1 falsified)  <- 1 falsified claim(s)
```

Falsified. The witness says why:

<!-- example: codebase run -->
```python
import mathema
from billing.fees import discounted

(p,) = mathema.claims.check_conjectures(discounted, [
    mathema.claim("d(f(price, rate), rate) <= 0", name="monotonic_decreasing[rate]")])
print(p.verdict, p.counterexample)
```

<!-- example: codebase output -->
```text
falsified rate=-2.72559 -> -32.66347642639832, rate=4.92258 -> 34.39055087522713 at price = -8.76733 (not decreasing)
```

The derivative of `price * (1 - rate)` in `rate` is `-price`, which is
positive when the price is negative, and the claim said nothing about
prices. Both values were computed at the same price, the one the witness
prints after `at`. (`d(f(price, rate), rate)` is
the derivative in `rate`; [the claim grammar](grammar.md#calculus) lists
the calculus forms.) The suggestion was right about the function and silent about its
domain, which is the usual state of a suggestion. Say what the function
is for, a price that is never negative and a rate between none and all
of it:

<!-- example: codebase file=claims/adopted.claims.yaml -->
```yaml
billing.fees.discounted:
  claims:
  - name: monotonic_decreasing[rate]
    statement: "for price in [0, 1e6], rate in [0, 1], d(f(price, rate), rate) <= 0"
    route: best
    grammar: mathema
```

## 5. Put a claim beside the code

A claim can also live in the function's docstring, where the next reader
of the code sees it. `settle` returns a magnitude:

<!-- example: codebase file=billing/fees.py -->
```python
def late_fee(days: int, base: float) -> float:
    """The fee for a payment that is `days` late: one percent of base a day."""
    return base * 0.01 * days


def discounted(price: float, rate: float) -> float:
    """The price after applying a discount rate."""
    return price * (1 - rate)


def settle(exposure: float) -> float:
    """The settlement amount for a signed exposure.

    Claims:
        nonneg: f(exposure) >= 0
    """
    return abs(exposure)
```

The two places are equal: a docstring claim and a claims-file claim are
adjudicated the same way, and [Authoring claims](authoring.md) says which
wins when both name the same claim.

## 6. The first sweep

<!-- example: codebase run -->
```bash
mathema verify --root .
mathema audit billing --root . --filter unclaimed --cols key,claims
```

<!-- example: codebase output -->
```text
ok   billing.fees.discounted: no baseline record; 2 proven, 0 holds, 0 falsified
ok   billing.fees.late_fee: no baseline record; 1 proven, 0 holds, 0 falsified
ok   billing.fees.settle: no baseline record; 2 proven, 1 holds, 0 falsified
0 fresh (form unchanged, skipped), 3 adjudicated, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
{"prefix":"billing.fees.","cols":["key","claims"],"rows":[["late_fee",0]]}
```

Both claims proved on the derive route, and every record also carries
`dependencies_current`, the claim `verify` adds that what the function
depends on has not moved; that is the second `proven` on the two claimed
functions and the only one on `late_fee`. The `1 holds` on `settle` is
the proof's `[float]` companion, the same claim run through the real code
in floating point. `--filter unclaimed` is the list of what is left, as
data, cut to two columns with `--cols`: one function. The records under
`.mathema/verified/` are the evidence, and they are meant to be committed
with the code.

## 7. Let the tests you have count

The tests already exercise `discounted` and `settle`. Run them under
coverage once, and `mathema coverage` counts their lines beside the lines
mathema's own probes and proofs reached:

<!-- example: codebase run -->
```bash
python -m coverage run -m pytest -q test_fees.py
python -m coverage json -q
mathema coverage billing --root .
```

<!-- example: codebase output match=subset -->
```text
2 passed in 0.05s
100%  billing.fees.discounted  [test+probe+derive]
100%  billing.fees.late_fee  [probe]
100%  billing.fees.settle  [test+probe+derive]

implementation coverage: 100%
```

`late_fee` has no claim of its own, so it reads `probe` alone:
`coverage` runs mathema's standard claims about a function while tracing
it, and the lines they ran count, but a proof counts the body as
modelled only for a claim included for the function and recorded by the
sweep, as `discounted`'s and `settle`'s are.
[`mathema coverage`](modes/coverage.md) explains the three sources and
what happens to a test report when the code moves on. From here, [Gate a
pipeline with mathema verify](gate-a-pipeline.md) puts the sweep in CI,
and [From a pytest test to a claim](from-a-pytest-test.md) turns the
tests you already have into claims.
