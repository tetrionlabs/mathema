# Missing values

Data arrives with gaps. A price feed skips a tick, a form leaves a field
empty, a join finds no match. Python code meets those gaps as `None` and
`nan`, and it usually treats them in one of a few ways without anyone
deciding it should. This page shows how mathema reads a value that is
not there, what a function can do with one, and how you write down what
yours does, so the claims about the numbers a function computes and the
claims about its gaps stay apart. Every output on the page is what the
code beside it prints.

## Two kinds of no value

Where the `None` sits decides what it means.

<!-- illustration -->
```text
price = None                   absent: the argument itself is not there
prices = [0.2, None, 0.7]      a list with three slots:
                                 slot 0  value 0.2
                                 slot 1  hole, member null
                                 slot 2  value 0.7
prices = [0.2, nan, 0.7]       slot 1 is a hole, member nan
price = nan                    a hole: a float's own missing value
```

- **absent**: the object is not there. An argument, a field of a record,
  a whole list. Python spells it `None`.
- **missing**: a slot holds no computable value. A `nan` in a float, a
  `None` element of a list, a `pd.NA` or `NaT` in a pandas Series, a
  polars `null`. A missing value is called a **hole**, and each spelling
  is a **member** of the hole class: `nan`, `null`, `NA`, `NaT`.

A scalar argument has no slot inside it, so a scalar `None` is always
absent, while `nan` is always a hole. Here is what Python does with each:

<!-- example: kinds file=prices.py -->
```python
import math


def volatility(variance: float) -> float:
    """The standard deviation for a variance."""
    return math.sqrt(variance)


def total_exposure(positions: list) -> float:
    """The sum of every position."""
    return sum(positions)
```

<!-- example: kinds run -->
```python
from prices import total_exposure, volatility


def outcome(expr):
    try:
        return repr(eval(expr))
    except Exception as exc:
        return type(exc).__name__


for expr in ['volatility(None)', 'volatility(float("nan"))',
             'total_exposure([0.2, None, 0.7])', 'total_exposure([0.2, float("nan")])',
             'total_exposure(None)']:
    print(f"{expr:36} {outcome(expr)}")
```

<!-- example: kinds output -->
```text
volatility(None)                     TypeError
volatility(float("nan"))             nan
total_exposure([0.2, None, 0.7])     TypeError
total_exposure([0.2, float("nan")])  nan
total_exposure(None)                 TypeError
```

The first and last calls pass `None` where an object belongs: absent. The
second passes a hole to a scalar, the third a list with a `null` hole in
slot 1, the fourth a list with a `nan` hole.

A claim states what its domain admits, completed from the annotation. A
`float` may be `nan`, so a claim over one admits it and mathema calls the
function there; an `Optional[float]` may also be absent; an `int` has no
hole. You write the short form, and the record shows what it resolved
to:

<!-- example: admits file=admits.py -->
```python
from typing import Optional


def volatility(variance: float) -> float:
    return variance ** 0.5


def fee(amount: Optional[float]) -> float:
    return 0.01 * amount


def lot_count(shares: int) -> int:
    return shares // 100


def exposure(positions: list) -> float:
    return sum(positions)
```

<!-- example: admits run -->
```python
import mathema
from admits import exposure, fee, lot_count, volatility


def statement(fn, text):
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    return next(p.statement for p in rec.probes if p.name == "c")


print(statement(volatility, "for variance in [0, 1], f(variance) >= 0"))
print(statement(fee, "for amount in [0, 100], f(amount) <= 1"))
print(statement(lot_count, "for shares in [0, 1000] subset Z, f(shares) >= 0"))
print(statement(volatility, "for variance in [0, 1] \\ {missing}, f(variance) >= 0"))
print(statement(exposure, "for positions in [0, 1]^n, f(positions) >= 0"))
```

<!-- example: admits output -->
```text
for variance in [0.0, 1.0] : float|missing, f(variance) >= 0
for amount in [0.0, 100.0] : float|absent|missing, f(amount) <= 1
for shares in [0, 1000] : int, f(shares) >= 0
for variance in [0.0, 1.0] : float, f(variance) >= 0
for positions in ([0.0, 1.0] | {missing})^n : float, f(positions) >= 0
```

`: float|missing` says the claim admits a float's hole; `\ {missing}`
removes it, and the rendering keeps the exclusion because it says
something the type does not. Inside the brackets of `(... | {missing})^n`
the clause is about the slots of the vector.

## Five behaviours

Given a hole or an absence, a function does one of five things. Each is
defined by counting the missing and absent values in and out, so running
the function decides which:

| word | the output holds |
|---|---|
| `raises` | nothing: the call raises |
| `drops` | no missing or absent value |
| `propagates` | as many as the input, of the same kind |
| `converts` | as many, of the other kind (a hole in, `None` out) |
| `introduces` | any other count, including one from inputs that were all there |

The ones that cause trouble are the quiet ones. Each of these returns an
answer as if nothing had happened:

<!-- example: traps run -->
```python
from typing import Optional


def clamp_discount(rate: float) -> float:
    """A discount rate held to [0, 1]."""
    return max(0.0, min(1.0, rate))


def risk_label(score: Optional[float]) -> str:
    """"high" above one half, else "low"."""
    return "high" if score > 0.5 else "low"


def fee_rate(tier: int) -> Optional[float]:
    """The fee for a customer tier, None for a tier with no fee schedule."""
    return {1: 0.05, 2: 0.07}.get(tier)


print(clamp_discount(float("nan")))   # min(1.0, nan) is 1.0
print(risk_label(float("nan")))       # nan > 0.5 is False
print(fee_rate(3))                    # dict.get: None for a tier that exists
```

<!-- example: traps output -->
```text
1.0
low
None
```

`clamp_discount` turns a missing rate into a full discount, and
`risk_label` turns a missing score into `"low"`: both **drop** the hole
by an accident of comparison. `fee_rate` **introduces** an absence from
an input that was there.

## A value claim is judged on values

A claim such as "`clamp_discount(rate)` stays in `[0, 1]`" is about the
numbers the function computes. It is judged wherever the function
returns a value, including the value it returns for a dropped hole, and
never where the function returns no value or raises at a missing input.
That call is sorted into one of the five behaviours instead, and the
record says what happened there. A `nan` from inputs that were all there
still fails a value claim: the mathematics has a value at that point,
and the code gave none.

## One function at a time

The functions below come from one file of pricing code:

<!-- example: core file=pricing.py -->
```python
import math
from typing import Optional


def volatility(variance: float) -> float:
    """The standard deviation for a variance."""
    return math.sqrt(variance)


def risk_label(score: Optional[float]) -> str:
    """"high" above one half, else "low"."""
    return "high" if score > 0.5 else "low"


def clamp_discount(rate: float) -> float:
    """A discount rate held to [0, 1]."""
    return max(0.0, min(1.0, rate))


def log_return(ratio: float) -> float:
    """The log of a price ratio; a missing ratio is refused."""
    if ratio != ratio:
        raise ValueError("ratio is missing")
    return math.log(ratio)


def in_base_currency(amount: float, fx_rate: Optional[float] = None) -> float:
    """An amount converted at fx_rate; no rate means it is already in base."""
    if fx_rate is None:
        fx_rate = 1.0
    return amount * fx_rate


def fee_rate(tier: int) -> Optional[float]:
    """The fee for a customer tier, None for a tier with no fee schedule."""
    return {1: 0.05, 2: 0.07}.get(tier)
```

### The silent drop

Start with the failure. The claim is that a clamped rate lies in
`[0, 1]`:

<!-- example: core run -->
```python
import mathema
from pricing import clamp_discount

print(mathema.check(clamp_discount, claims=[mathema.claim(
    "for rate in R, 0 <= clamp_discount(rate) <= 1", name="in_unit")]))
```

<!-- example: core output -->
```text
mathema.Record(clamp_discount) · source, no side effects · form bc9fa73b5bd1
  in_unit  for rate in R|missing, 0 <= clamp_discount(rate) <= 1   falsified at rate = nan
    proven     mathematics  for rate in R, 0 <= clamp_discount(rate) <= 1
    holds      computation  for rate in R, 0 <= clamp_discount(rate) <= 1   43 draws
    falsified  policy       f(nan)   no missing policy stated; returns 1.0
                            possible fixes:
                              (i) if dropping nan is intended, run: mathema accept pricing.clamp_discount missing[rate] --as discovery --corrected "missing(f, rate) drops"
                              (ii) exclude nan
                              (iii) handle nan at entry
```

Read it from the top. The headline is the claim as mathema resolved
it, `rate in R|missing` (a float may be `nan`), and its verdict. Under
it, the `mathematics` line is the claim over the real numbers, proven;
the `computation` line runs the real code in float64, and holds. The
last line is a **policy line**: what `clamp_discount` does with a
missing `rate`. No policy was stated, so mathema assumed the default for
a float, that a hole comes back as a hole, and the code does something
else: at `rate = nan` it returned `1.0`. That falsifies the headline,
and the line under it lists the ways forward. If a full discount is what
a missing rate should mean, state it: `missing(f, rate) drops`. If not,
take `nan` out of the claim (`for rate in R \ {missing}`), or handle it
at entry, giving the hole back (`if rate != rate: return rate`) or
raising.

### Two bugs in one line

<!-- example: core run -->
```python
from pricing import risk_label

print(mathema.check(risk_label, claims=[mathema.claim(
    'for score in [0, 1], risk_label(score) in {"high", "low"}', name="labels")]))
```

<!-- example: core output -->
```text
mathema.Record(risk_label) · source, no side effects · form ba84c5dc4cc6
  labels  for score in [0.0, 1.0] : float|absent|missing, risk_label(score) in {"high", "low"}   falsified at score = nan
    holds      computation  for score in [0.0, 1.0] : float, risk_label(score) in {"high", "low"}   34 draws
    falsified  policy       f(nan)   no missing policy stated; returns "low"
                            possible fixes:
                              (i) if dropping nan is intended, run: mathema accept pricing.risk_label missing[score] --as discovery --corrected "missing(f, score) drops"
                              (ii) exclude nan
                              (iii) handle nan at entry
    falsified  policy       f(None)   no absent policy stated; raises TypeError
                            possible fixes:
                              (i) if the raise is intended, run: mathema accept pricing.risk_label absent[score] --as discovery --corrected "absent(f, score) raises(TypeError)"
                              (ii) exclude None
                              (iii) handle None at entry
```

The mathematics holds: every label is `"high"` or `"low"`. The two
policy lines carry what it does not say, and both falsify the headline.
A missing score becomes `"low"`, the same silent drop as above. And
`Optional[float]` promises to take `None`, which the function cannot:
`None > 0.5` raises. No claim says it may; if the raise is what you
meant, state `absent(f, score) raises(TypeError)`.

### The code already says it

A float that propagates through a library call, a guard, and `None` used
as a flag each settle their own policy line:

<!-- example: core run -->
```python
from pricing import in_base_currency, log_return, volatility

print(mathema.check(volatility, claims=[mathema.claim(
    "for variance in [0, 1], volatility(variance) >= 0", name="nonneg")]))
print(mathema.check(log_return, claims=[mathema.claim(
    "for ratio in [0.5, 2], log_return(ratio) <= 1", name="bounded")]))
print(mathema.check(in_base_currency, claims=[mathema.claim(
    "for amount in [0, 100], fx_rate in [0.5, 2], "
    "in_base_currency(amount, fx_rate) == amount * fx_rate", name="scales")]))
```

<!-- example: core output -->
```text
mathema.Record(volatility) · source, no side effects · form fafd8ee932cd
  nonneg  for variance in [0.0, 1.0] : float|missing, volatility(variance) >= 0   holds
    proven     mathematics  for variance in [0.0, 1.0] ⊂ ℝ, volatility(variance) >= 0
    holds      computation  for variance in [0.0, 1.0] : float, volatility(variance) >= 0   43 draws
    proven     policy       f(nan)   propagates, from math.sqrt's own policy row, which f calls
mathema.Record(log_return) · source, no side effects · form cdfe6bbcc84d
  bounded  for ratio in [0.5, 2.0] : float|missing, log_return(ratio) <= 1   holds
    proven     mathematics  for ratio in [0.5, 2.0] ⊂ ℝ, log_return(ratio) <= 1
    holds      computation  for ratio in [0.5, 2.0] : float, log_return(ratio) <= 1   42 draws
    proven     policy       f(nan)   raises(ValueError), from the guard on line 3
mathema.Record(in_base_currency) · source, no side effects · form c0f6dfdbe44d
  scales  for amount in [0.0, 100.0] : float|missing, fx_rate in [0.5, 2.0] : float|absent|missing, in_base_currency(amount, fx_rate) = amount*fx_rate   holds
    holds      computation  for amount in [0.0, 100.0] : float, fx_rate in [0.5, 2.0] : float, in_base_currency(amount, fx_rate) = amount*fx_rate   161 draws
    holds      policy       f(amount=nan)   no missing policy stated; assumed propagates
    holds      policy       f(fx_rate=nan)   no missing policy stated; assumed propagates
    proven     policy       f(fx_rate=None)   drops, from the guard on line 3
```

`volatility` makes one call, to `math.sqrt`, and `math.sqrt` has its
own policy row in the bundled compendium: the hole comes back. The
policy line comes from it, proven. `log_return` raises on a missing ratio behind a
guard, so the row comes from the guard. `in_base_currency` replaces an
absent `fx_rate` with `1.0`, a drop, read from the same kind of guard.

### An absence the return type declares

<!-- example: core run -->
```python
from pricing import fee_rate

print(mathema.check(fee_rate, claims=[mathema.claim(
    "for tier in [0, 3] subset Z, fee_rate(tier) < 1", name="below_one")]))
```

<!-- example: core output -->
```text
mathema.Record(fee_rate) · source, no side effects · form c1cba0e35dda
  below_one  for tier in [0, 3] : int, fee_rate(tier) < 1   proven
    proven     mathematics  for tier in [0, 3] ⊂ ℤ, fee_rate(tier) < 1
    proven     policy       absent(f) introduces   from the return type Optional[float]: f returned None at tier = 0 from present inputs; confirmed on the draws of below_one
```

`-> Optional[float]` declares that the result may be absent, so the
`None` at `tier = 0` is recorded and not judged, and `absent(f)
introduces` comes from the return type. The same body annotated `->
float` fails the claim at that point: a `None` from inputs that were all
there is no value.

## Containers: lists, arrays and series

A container's slots can hold holes, and each runtime type has its own
members: a list slot may hold `null` (a `None` element) or `nan`, a
numpy array `nan`, a pandas Series `nan`, `null` or `NA`. Every claim
over a container first meets the awkward cases (a one-slot vector, an
all-hole one, a hole at each end), then random draws with holes in
them.

<!-- example: containers file=portfolio.py -->
```python
import numpy as np


def total_exposure(positions: list) -> float:
    """The sum of every position."""
    return sum(positions)


def average_return(returns: np.ndarray) -> float:
    """The mean of a series of returns."""
    return float(np.mean(returns))
```

<!-- example: containers run -->
```python
import mathema
from portfolio import average_return, total_exposure

print(mathema.check(total_exposure, claims=[mathema.claim(
    "for positions in [0, 1]^n, total_exposure(positions) >= 0", name="nonneg")]))
print(mathema.check(average_return, claims=[mathema.claim(
    "for returns in [0, 1]^n, 0 <= average_return(returns) <= 1", name="unit")]))
```

<!-- example: containers output -->
```text
mathema.Record(total_exposure) · source, no side effects · form dacf931fef1e
  nonneg  for positions in ([0.0, 1.0] | {missing})^n : float, total_exposure(positions) >= 0   falsified at positions = [null]
    proven     mathematics  for positions in ([0.0, 1.0])^n ⊂ ℝ, total_exposure(positions) >= 0
    holds      computation  for positions in ([0.0, 1.0])^n : float, total_exposure(positions) >= 0   208 entries across 44 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f([..., null, ...])   no missing policy stated; raises TypeError
                            possible fixes:
                              (i) if the raise is intended, run: mathema accept portfolio.total_exposure missing[positions, null] --as discovery --corrected "missing(f, positions, null) raises(TypeError)"
                              (ii) exclude null
                              (iii) handle null at entry
    holds      policy       f([..., nan, ...])   no missing policy stated; assumed propagates
mathema.Record(average_return) · source, no side effects · form ce47d44bdab7
  unit  for returns in ([0.0, 1.0] | {missing})^n : float, 0 <= average_return(returns) <= 1   holds
    holds      computation  for returns in ([0.0, 1.0])^n : float, 0 <= average_return(returns) <= 1   418 entries across 102 draws, sizes (1, 1) to (8, 1)
    proven     policy       f([..., nan, ...])   propagates, from numpy.mean's own policy row, which f calls
```

`sum` treats the two members of a list slot differently: it raises on a
`None` element and gives a `nan` back. The record says so member by
member, and the claim to write names the member. `np.mean` gives the
hole back, and the row comes from numpy's own. A pandas mean is a
longer story, told in [the mean of nothing](mean-of-nothing.md).

## Strings and records

A string has no hole, so a `str` parameter admits nothing missing; an
`Optional[str]` admits absence. A language binding (`L[unicode]`, see
[language domains](language.md)) draws real strings, and `| {None}` adds
the absence. The claim below is about a greeting:

<!-- example: strings file=names.py requires=mathema_language -->
```python
from typing import Optional


def greeting(nickname: Optional[str]) -> str:
    """A greeting for a customer's nickname."""
    return "Hi " + nickname.strip()
```

<!-- example: strings run requires=mathema_language -->
```python
import mathema
from names import greeting

print(mathema.check(greeting, claims=[mathema.claim(
    "for nickname in L[unicode] | {None}, len(greeting(nickname)) >= 3",
    name="long_enough")]))
```

<!-- example: strings output match=subset -->
```text
mathema.Record(greeting) · source, no side effects · form 4ddaf64c7461
  long_enough  for nickname in L[unicode]|None, len(greeting(nickname)) >= 3   falsified at nickname = None
    holds      computation  for nickname in L[unicode], len(greeting(nickname)) >= 3   223 draws
    falsified  policy       f(None)   no absent policy stated; raises AttributeError
                            possible fixes:
                              (i) if the raise is intended, run: mathema accept names.greeting absent[nickname] --as discovery --corrected "absent(f, nickname) raises(AttributeError)"
                              (ii) exclude None
                              (iii) handle None at entry
```

The computation holds on every string. `nickname = None` was drawn
first, because the binding admits it, and the function raised there;
the `f(None)` policy line says no claim allows that raise, which is why
the headline is falsified.

A record's field has the same two kinds, and where the `None` sits
decides which. A field or key holding `None` is absent, and so is a key
that is not there, an index past the end, or a step below an absent
object; an element of a list holding `None` is a hole. Absence has two
members, as the hole class has several: `null`, the key is there
holding `None`, and `unset`, the key is left out. They differ where a
difference matters (in a PATCH body, `{}` leaves a note alone and
`{"note": null}` clears it), so a binding on a path can admit or
exclude each, `\ {unset}` or `\ {null}`:

<!-- example: slip file=slips.py -->
```python
def delivery_note(order: dict) -> str:
    """The note printed on a delivery slip."""
    return order["note"].strip()
```

<!-- example: slip run -->
```python
import mathema
from slips import delivery_note

print(mathema.check(delivery_note, claims=[mathema.claim(
    'for order.note in {"ring twice", "leave at the door"} | {None} \\ {null}, '
    'len(delivery_note(order)) >= 1', name="has_text")]))
```

<!-- example: slip output -->
```text
mathema.Record(delivery_note) · source, no side effects · form 723add5de9a8
  holds     has_text: for order.note in {"leave at the door", "ring twice", absent} \ {null}, len(delivery_note(order)) >= 1 (87 draws)
           derive could not decide it (function body is not derivable, likely reason: unsupported-construct: unsupported-call (line 3), an expression form the derive vocabulary doesn't cover yet), so the probe decided it by running the code; at order.note, a key left out, f raised KeyError
  falsified absent[order.note]: f raised KeyError at order.note, a key left out, and no claim says it may
           (i) if the raise is intended, state: absent(f, order.note) raises(KeyError)
           (ii) if not, handle it in f
           (iii) to exclude it where order.note is bound, write: \ {unset}
           (iv) to accept the raise as a discovery, run: mathema accept slips.delivery_note absent[order.note] --as discovery --corrected "absent(f, order.note) raises(KeyError)"
```

A field's no-value is a missing input as a parameter's is: the value
claim is judged on the notes that are there, the raise at the key left
out is said on the claim's row, and the path has a policy row of its
own. `absent(f, order.note, unset) raises(KeyError)` states it; the
second argument of a policy row is a parameter or a path, with the same
member forms (`absent(f, order.note, null) drops`,
`missing(f, order.lines[*].qty) propagates`).

A witness names the member: `order.note unset` for a key left out,
`order.note = null (absent)` for a key holding `None`, and
`order.lines[1] = null (hole)` for an element of a list. On a path that
ends at a field `null` is the absence member; on one that ends at an
element (`order.lines[*]`) it is the hole member. Written for a
parameter itself, `null` is its absence, the same as `None`.
`is_absent_safe(f)` reaches into a record's fields: an `Optional` field
of a dataclass or a pydantic model is called with `None` too.

## Policy rows, defaults and `mathema claims --write`

A policy row is a claim like any other, in one short form:

<!-- illustration -->
```text
missing(f, rate) propagates
absent(f, score) raises(TypeError)
missing(f, positions, null) raises(TypeError)
assuming count(xs) >= 1, missing(f, xs) drops
absent(f) introduces
```

The member narrows a row to one spelling; a premise on `count(...)`
(the number of value slots) or `len(...)` (every slot) splits a
behaviour where the size decides it.

A row decided from calls carries the route `probe:counterfactual`: each
call at a hole is made again with the hole filled, and the difference
says what the function did with it. `clamp_discount` returns `1.0` for a
missing rate; filled with `1.0` and with `2.0` it returns `1.0` again,
but filled with `0.9` it returns `0.9`, so it read the slot and drops
the hole. When no fill changes the answer, the function is
indifferent to the slot: it returned a value with the hole there, which
breaks `raises` and `propagates`, and says nothing for `drops`,
where ignoring a slot and replacing a hole look the same. Where a kind reaches a parameter,
the record carries a row for it, and the bracket says whose word it is:

- **default for a float, which may be nan**: the type admits the kind
  and nobody said anything. A hole propagates by default; a `None` an
  unannotated parameter may take raises.
- **from math.sqrt's own policy row** or **from the guard on line 2**:
  the code says it.
- **observed**: you admitted the kind (an `Optional`, a listed `None`),
  so there is no default; what the code did is written down, and a
  raise stays open until a claim says it may.
- **stated**: yours.

A row the code contradicts, and a raise no claim accounts for, fail
`mathema verify` like any falsified claim. `mathema claims` lists a
function's rows by state, and `--write` puts them in your claims file,
where changing a policy is editing one word:

<!-- example: write file=shop.py -->
```python
import math


def volatility(variance: float) -> float:
    """Claims:
        nonneg: for variance in [0, 4], f(variance) >= 0
    """
    return math.sqrt(variance)


def clamp_discount(rate: float) -> float:
    """Claims:
        in_unit: for rate in R, 0 <= f(rate) <= 1
    """
    return max(0.0, min(1.0, rate))
```

<!-- example: write session -->
```
$ mathema claims shop.clamp_discount
shop.clamp_discount: no declared claims (to list candidates, run: mathema claims shop.clamp_discount --suggest)
shop.clamp_discount: 1 policy row about rate
  contradicted by the code (change the word, the code, or accept it as a discovery; --write writes these with the contradiction in the note):
    falsified missing[rate]: missing(f, rate) propagates   [mathema's default word for a float, not a claim of yours; f drops instead: nan in, 1.0 out]
             (i) if 1.0 is the answer f should give for a missing rate, state: missing(f, rate) drops
             (ii) if not, make f raise or give nan back
             (iii) to accept it as a discovery, run: mathema accept shop.clamp_discount missing[rate] --as discovery --corrected "missing(f, rate) drops"
```

<!-- example: write session -->
```
$ mathema claims shop.clamp_discount --write
shop.clamp_discount: wrote 1 policy row to claims/policies.claims.yaml: missing[rate].
The code contradicts missing[rate] (f drops, nan in, 1.0 out):
(i) change the word in the file or change f
(ii) to accept it as a discovery, run: mathema accept shop.clamp_discount missing[rate] --as discovery --corrected "missing(f, rate) drops"
```

<!-- example: write session -->
```
$ cat claims/policies.claims.yaml
shop.clamp_discount:
  claims:
  - name: missing[rate]
    statement: missing(f, rate) propagates
    note: 'written by mathema claims --write: mathema''s default word for a float,
      not a claim of yours; contradicted by the code on 2026-09-30: f drops, nan in,
      1.0 out'
```

The contradicted row is written with the contradiction in its note, so
the next `mathema verify` fails on it until you change the word, change
the code, or accept it as a discovery.

## Which values are holes

Which values a runtime holds as missing is a **definition**, stated once
under the runtime type, `missing := {null, nan}`, and taken at face
value. mathema ships the ones for pandas and polars; a project adds its
own the same way (see [definitions](claims-transfer.md#definitions)). A
claim over a polars Series resolves `missing` to that runtime's members,
and the record says so:

<!-- example: defines file=pl_prices.py -->
```python
import polars as pl


def total_volume(volumes: pl.Series) -> float:
    """The traded volume over a session."""
    return float(volumes.sum())
```

<!-- example: defines run -->
```python
import mathema
from pl_prices import total_volume

rec = mathema.check(total_volume, claims=[mathema.claim(
    "for volumes in [0, 1]^n, total_volume(volumes) >= 0", name="nonneg")])
(row,) = [p for p in rec.probes if p.name == "nonneg"]
print(row.meta["mathema.missing"]["means"])
```

<!-- example: defines output -->
```text
missing for volumes (polars.Series) means null or nan
```

## The gates and `enforce_domain`

A policy row is one fact about one parameter. `is_missing_safe(f)` and
`is_absent_safe(f)` state that every parameter admitting the kind has a
policy the code follows at every member. mathema offers them
(`mathema claims KEY --suggest`) and never asserts them for you.

<!-- example: core run -->
```python
print(mathema.check(risk_label, claims=[mathema.claim(
    'for score in [0, 1], risk_label(score) in {"high", "low"}'),
    mathema.claim("is_missing_safe(f)"), mathema.claim("is_absent_safe(f)")]))
```

<!-- example: core output -->
```text
mathema.Record(risk_label) · source, no side effects · form ba84c5dc4cc6
  risk_label_score_in_high_low  for score in [0.0, 1.0] : float|absent|missing, risk_label(score) in {"high", "low"}   falsified at score = nan
    holds      computation  for score in [0.0, 1.0] : float, risk_label(score) in {"high", "low"}   34 draws
    falsified  policy       f(nan)   no missing policy stated; returns "low"
                            possible fixes:
                              (i) if dropping nan is intended, run: mathema accept pricing.risk_label missing[score] --as discovery --corrected "missing(f, score) drops"
                              (ii) exclude nan
                              (iii) handle nan at entry
    falsified  policy       f(None)   no absent policy stated; raises TypeError
                            possible fixes:
                              (i) if the raise is intended, run: mathema accept pricing.risk_label absent[score] --as discovery --corrected "absent(f, score) raises(TypeError)"
                              (ii) exclude None
                              (iii) handle None at entry
  holds     is_missing_safe[f]: is_missing_safe(f)
           score (float): nan drops, confirmed by calling f at score = nan; no claim states it yet
  falsified is_absent_safe[f]: is_absent_safe(f)
           score (float): None raises TypeError, and no claim says it may
           counterexample score = None: f raised TypeError
           score is Optional[float], so f promised to take None.
           (i) if the raise is intended, state: absent(f, score) raises(TypeError)
           (ii) if not, handle None in f, or annotate score as float
           (iii) to accept the raise as a discovery, run: mathema accept pricing.risk_label absent[score] --as discovery --corrected "absent(f, score) raises(TypeError)"
```

`is_missing_safe` holds, not proven: the one hole a float holds was
tried and f drops it, but that is what the code did, not what anyone
said it should do. Writing `missing(f, score) drops` makes it a stated
policy, and the gate proven. `is_absent_safe` is falsified by the raise
on `None`, with the claim to state beneath it.

`@enforce_domain()` turns the policy rows into a runtime check. It is
opt-in. A `raises` row refuses the input before the function runs, with
the exception the row names (mathema's `DomainError` where it names
none) and one sentence naming the parameter and the member; a `drops` or
`propagates` row is checked on the result, with a `MissingValueError` (a
kind of `DomainError`); `converts` and `introduces` enforce nothing:

<!-- example: enforce run -->
```python
import math
from typing import Optional

import mathema


@mathema.enforce_domain()
@mathema.claims_decorator("absent(f, variance) raises(TypeError)",
                          "missing(f, variance) propagates")
def volatility(variance: Optional[float]) -> float:
    return math.sqrt(variance) if variance == variance else 0.0


for arg in (None, float("nan"), 4.0):
    try:
        print(volatility(arg))
    except (TypeError, mathema.DomainError) as exc:
        print(exc)
```

<!-- example: enforce output -->
```text
enforce_domain is active and raised TypeError because variance is None
volatility(): at variance = nan f returned 0.0, dropping the hole, but its policy says propagates (missing(f, variance) propagates)
2.0
```

## What is not missing

- An empty container: zero slots, so no holes. `is_empty_safe(xs)` asks
  what the function does with one, building it as the parameter's own
  runtime type.
- An infinity: a value. An infinity from a finite input fails a value
  claim, as a `nan` from inputs that were all there does.
- A row a function filters out of a table: a change of shape, not a
  hole.

## What changed in 0.6.1

- The two words, `absent` and `missing` (`None` still reads as `absent`),
  with the members `nan`, `null`, `NA` and `NaT`; a domain renders what
  it admits.
- A value claim is judged on values; a missing input is sorted into one
  of the five behaviours.
- Policy rows, their defaults, `mathema claims --write`, and the bundled
  policy rows for `math`, numpy, pandas and polars.
- `is_missing_safe(f)`, `is_absent_safe(f)`, `is_empty_safe` built
  through the runtime type, and `enforce_domain` reading the policy rows.
