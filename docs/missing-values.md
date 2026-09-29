# Missing values

A value can fail to be there in two ways, and code treats the two very
differently. This page shows how mathema reads each one, what a function
can do with it, and how you state what yours does, so a claim about the
values a function computes and a claim about what it does with no value
never get in each other's way. Every output below is what the code on
the page prints.

## Two kinds of no value

- **absent**: the object itself is not there. The argument, the list,
  the frame. Python spells it `None`.
- **missing**: a slot holds no computable value. `nan` in a float, a
  `None` element in a list, `pd.NA` or `NaT` in a pandas Series, a polars
  `null`. Each spelling is a **member** of the hole class: `nan`, `null`,
  `NA`, `NaT`.

**Position decides.** The same Python `None` is absence when it is the
argument and a hole (the member `null`) when it sits in a slot of a
container. A scalar argument has no slot inside it, so a scalar `None`
is always absence.

Here is what you pass, what Python does with it, and what mathema reads:

<!-- example: kinds file=mv.py -->
```python
import math
from typing import Optional



def sqrt_plain(x: float) -> float:
    return math.sqrt(x)


def total(xs: list) -> float:
    return sum(xs)
```

<!-- example: kinds run -->
```python
from mv import sqrt_plain, total


def call(expr):
    try:
        return repr(eval(expr))
    except Exception as exc:
        return type(exc).__name__


for expr in ['sqrt_plain(None)', 'sqrt_plain(float("nan"))',
             'total([0.2, None, 0.7])', 'total([0.2, float("nan")])',
             'total(None)']:
    print(f"{expr:30} {call(expr)}")
```

<!-- example: kinds output -->
```text
sqrt_plain(None)               TypeError
sqrt_plain(float("nan"))       nan
total([0.2, None, 0.7])        TypeError
total([0.2, float("nan")])     nan
total(None)                    TypeError
```

| you call | mathema reads |
|---|---|
| `sqrt_plain(None)` | `x` is absent |
| `sqrt_plain(float("nan"))` | `x` holds a hole, the member `nan` |
| `total([0.2, None, 0.7])` | `xs` is present; one slot is a hole, the member `null` |
| `total([0.2, float("nan")])` | one slot is a hole, the member `nan` |
| `total(None)` | `xs` itself is absent |

A claim states what its domain admits, completed from the annotation.
A `float` may be `nan`, so a claim over one admits it and mathema calls
the function there; an `Optional[float]` may also be absent; an `int`
has no hole:

<!-- example: admits run -->
```python
from typing import Optional

import mathema


def a(x: float) -> float: return x
def b(x: Optional[float]) -> float: return x
def c(x: int) -> int: return x
def d(xs: list) -> float: return xs[0]


for fn, text in [(a, "for x in [0, 1], f(x) == x"),
                 (b, "for x in [0, 1], f(x) == x"),
                 (c, "for x in [0, 1] subset Z, f(x) == x"),
                 (a, "for x in [0, 1] \\ {missing}, f(x) == x"),
                 (d, "for xs in [0, 1]^n, f(xs) == xs[0]")]:
    (row,) = [p for p in mathema.check(fn, claims=[mathema.claim(text, name="c")]).probes
              if p.name == "c"]
    print(row.statement)
```

<!-- example: admits output -->
```text
for x in [0.0, 1.0] : float|missing, f(x) = x
for x in [0.0, 1.0] : float|absent|missing, f(x) = x
for x in [0, 1] : int, f(x) = x
for x in [0.0, 1.0] : float, f(x) = x
for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) = xs[0]
```

`: float|missing` says the claim admits a float's hole; `\ {missing}`
removes it, and the rendering keeps the exclusion because it says
something the type does not. Inside the brackets of `(... | {missing})^n`
the clause is about the slots of the vector.

## Five behaviours

Given a missing or absent input, a function does one of five things.
Each is defined by counting no-value slots in and out, so running the
function decides it:

| word | what it means |
|---|---|
| `raises` | every call with the kind raises |
| `drops` | the output holds no missing or absent value at all |
| `propagates` | the output holds as many as the input, of the same kind |
| `converts` | as many, of the other kind (a hole in, `None` out) |
| `introduces` | any other count, including one from present inputs |

The traps are the quiet ones. Each of these returns a value as if
nothing had happened:

<!-- example: traps run -->
```python
from typing import Optional


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def label(x: Optional[float]) -> str:
    return "high" if x > 0.5 else "low"


def rate(k: int) -> Optional[float]:
    return {1: 0.05, 2: 0.07}.get(k)


print(clamp01(float("nan")))     # min(1.0, nan) is 1.0: the hole became 1.0
print(label(float("nan")))       # nan > 0.5 is False: the hole became "low"
print(rate(3))                   # dict.get: a None from a present input
```

<!-- example: traps output -->
```text
1.0
low
None
```

`clamp01` and `label` **drop** the hole: it turns into a definite value
by an accident of comparison. `rate` **introduces** an absence from an
input that was there.

## A value claim is judged on values

A claim such as `f(x) >= 0` is about the values the function computes.
It is judged wherever the function returns a value, the value it
returns at a dropped hole included, and never where the function
returns no value or raises at a missing input: that call is classified
into one of the five behaviours instead, and the record says what
happened there. A `nan` from inputs that hold no missing value is still
a failure of the value claim, since the mathematics has a value there
and the code produced none.

## One function at a time

Every record below comes from the same file:

<!-- example: core file=mv.py -->
```python
import math
from typing import Optional


def sqrt_plain(x: float) -> float:
    return math.sqrt(x)


def label(x: Optional[float]) -> str:
    return "high" if x > 0.5 else "low"


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def sqrt_guarded(x: float) -> float:
    if x != x:
        raise ValueError("x is missing")
    return math.sqrt(x)


def scaled(x: float, scale: Optional[float] = None) -> float:
    if scale is None:
        scale = 1.0
    return x * scale


def rate(k: int) -> Optional[float]:
    return {1: 0.05, 2: 0.07}.get(k)
```

### A float that propagates

<!-- example: core run -->
```python
import mathema
from mv import sqrt_plain

print(mathema.check(sqrt_plain, claims=[mathema.claim("for x in [0, 1], f(x) >= 0",
                                                      name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(sqrt_plain) · source, no side effects · form fafd8ee932cd
  proven  c: for x in [0.0, 1.0] : float|missing, f(x) >= 0
           ∀ x ∈ [0.0, 1.0] ⊂ ℝ; missing for x (float) means nan
  holds   c[float]: for x in [0.0, 1.0] : float|missing, f(x) >= 0 (43 draws)
           the float64 computation of c ran at 43 points: nan, every corner and 40 interior points; at x = nan f gave nan back
  proven  missing[x]: missing(f, x) propagates   [from math.sqrt's own policy row, which f calls; confirmed on the 43 draws of c[float]]
```

The proof is over the reals. Its `[float]` companion runs the real code
at `nan` too, and the record says what happened there. The last row is
a **policy row**, `missing(f, x) propagates`: what the function does
with a hole in `x`. `math.sqrt` has its own policy row in the bundled
compendium, and `sqrt_plain` makes that one call, so the row comes from
it and is proven. There is nothing to write.

### Two quiet bugs in one line

<!-- example: core run -->
```python
from mv import label

print(mathema.check(label, claims=[mathema.claim(
    'for x in [0, 1], f(x) in {"high", "low"}', name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(label) · source, no side effects · form ba84c5dc4cc6
  holds   c: for x in [0.0, 1.0] : float|absent|missing, f(x) in {"high", "low"} (34 draws)
           derive could not decide it (`in` is decided by execution: the symbolic lift has no reading of membership in a language or a set, so the probe route adjudicates it); the probe decided it; at x = None f raised TypeError; at x = nan f returned "low", so it drops the hole
  FALSIFY missing[x]: missing(f, x) propagates   [default for a float; f drops instead: nan in, "low" out]
           if "low" is the answer f should give for a missing x, write `missing(f, x) drops`; if not, make f raise or give nan back; or accept it as a discovery: mathema accept mv.label missing[x] --as discovery --corrected "missing(f, x) drops"
  FALSIFY absent[x]: f raised TypeError at x = None, and no claim says it may
           x is Optional[float], so f promised to take None. If the raise is intended, state `absent(f, x) raises(TypeError)`; otherwise handle None in f, or annotate x as float; or accept the raise as a discovery (mathema accept mv.label absent[x] --as discovery) and state `absent(f, x) raises(TypeError)`
```

The value claim holds: every value `label` returns is `"high"` or
`"low"`. The two policy rows carry what it does not say. A float may be
`nan`, and the default for a hole is to give it back; `label` turns it
into `"low"` instead. And `Optional[float]` promises to take `None`,
which the function then cannot: that raise is accounted for by no
claim, so it prints as a sentence with the claim to state if the raise
is what you meant.

### The silent drop no value claim can see

<!-- example: core run -->
```python
from mv import clamp01

print(mathema.check(clamp01, claims=[mathema.claim(
    "for x in R, 0 <= f(x) <= 1", name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(clamp01) · source, no side effects · form bc9fa73b5bd1
  proven  c: for x in R|missing, 0 <= f(x) <= 1
           ∀ x ∈ ℝ; missing for x (float) means nan
  holds   c[float]: for x in R|missing, 0 <= f(x) <= 1 (43 draws)
           the float64 computation of c ran link by link, and every link holds; at x = nan f returned 1.0, so it drops the hole
  FALSIFY missing[x]: missing(f, x) propagates   [default for a float; f drops instead: nan in, 1.0 out]
           if 1.0 is the answer f should give for a missing x, write `missing(f, x) drops`; if not, make f raise or give nan back; or accept it as a discovery: mathema accept mv.clamp01 missing[x] --as discovery --corrected "missing(f, x) drops"
```

`1.0` is between 0 and 1, so the value claim is right to pass. What is
wrong is that a hole became a definite answer, and the policy row is
where that shows. Write `missing(f, x) drops` if `1.0` is what you want;
most people want the hole back (`if x != x: return x`), after which the
default row holds.

### The code already says it: a guard

<!-- example: core run -->
```python
from mv import sqrt_guarded

print(mathema.check(sqrt_guarded, claims=[mathema.claim(
    "for x in [0, 1], f(x) >= 0", name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(sqrt_guarded) · source, no side effects · form 956dbc0fec33
  holds   c[float]: for x in [0.0, 1.0] : float|missing, f(x) >= 0 (43 draws)
           the float64 computation of c ran at 43 points: nan, every corner and 40 interior points; at x = nan f raised ValueError
  proven  missing[x]: missing(f, x) raises(ValueError)   [from the guard on line 2; confirmed on the 43 draws of c[float]]
```

A raising guard on a member is the function stating its policy, so the
row comes from the guard. Coverage is per member: `x != x` covers `nan`
and not `pd.NA`; on a `float` the only hole is `nan`, so it is complete.

### None as a flag

<!-- example: core run -->
```python
from mv import scaled

print(mathema.check(scaled, claims=[mathema.claim(
    "for x in [0, 1], scale in [0.5, 2], f(x, scale) == x * scale", name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(scaled) · source, no side effects · form c0f6dfdbe44d
  holds   c: for x in [0.0, 1.0] : float|missing, scale in [0.5, 2.0] : float|absent|missing, f(x, scale) = scale*x (161 draws)
           derive could not decide the branch at line 2 (scale is None); the probe decided it; at x = nan f gave nan back; at scale = None f returned 0.364, so it drops the absence; at scale = nan f gave nan back
  proven  absent[scale]: absent(f, scale) drops   [from the guard on line 2; confirmed on the 161 draws of c]
```

`if scale is None: scale = 1.0` replaces the absence with a value, so
`scale = None` is a drop, read from the guard.

### An absence the return type declares

<!-- example: core run -->
```python
from mv import rate

print(mathema.check(rate, claims=[mathema.claim(
    "for k in [0, 3] subset Z, f(k) <= 1", name="c")]))
```

<!-- example: core output match=subset -->
```text
mathema.Record(rate) · source, no side effects · form c1cba0e35dda
  proven  c: for k in [0, 3] : int, f(k) <= 1
           ∀ k in the declared finite domain (4 points)
           f returns None at k = 0, which its return type Optional[float] allows; that point has no value to compare, so it is recorded, not judged
  proven  absent[f]: absent(f) introduces   [from the return type Optional[float]: f returned None at k = 0 from present inputs; confirmed on the draws of c]
```

`-> Optional[float]` declares that the result may be absent, so the
`None` at `k = 0` is recorded and not judged, and `absent(f)
introduces` comes from the return type. The same body annotated `->
float` fails the value claim at that point: a `None` from present
inputs is no value.

## Containers: vectors, arrays and series

A container's slots can hold holes, and each runtime type has its own
members: a list slot may hold `null` (a `None` element) or `nan`, a
numpy array `nan`, a pandas Series `nan`, `null` or `NA`. The floor of
every claim over a container meets the degenerate cases first (a
one-slot vector, an all-hole one, a hole at each end), then random
draws carrying holes.

<!-- example: containers file=mv.py -->
```python
import numpy as np


def total(xs: list) -> float:
    return sum(xs)


def mean_np(xs: np.ndarray) -> float:
    return float(np.mean(xs))
```

<!-- example: containers run -->
```python
import mathema
from mv import mean_np, total

print(mathema.check(total, claims=[mathema.claim("for xs in [0, 1]^n, f(xs) >= 0",
                                                 name="c")]))
print(mathema.check(mean_np, claims=[mathema.claim(
    "for xs in [0, 1]^n, 0 <= f(xs) <= 1", name="c")]))
```

<!-- example: containers output match=subset -->
```text
mathema.Record(total) · source, no side effects · form dacf931fef1e
  proven  c: for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0
           ∀ xs ∈ [0.0, 1.0]ⁿ ⊂ ℝ, xs of every length; missing for xs (list) means null or nan
  holds   c[float]: for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0 (53 draws, sizes (1, 1) to (8, 1), 248 entries in all)
           the float64 computation of c ran at 53 points: null, nan, every corner and 40 interior points; at xs = [null] f raised TypeError; at xs = [nan] f gave nan back
  FALSIFY missing[xs, null]: missing(f, xs, null) propagates   [default for a list slot that may be null; f raises instead: a null slot in, TypeError]
           if the raise is intended, write `missing(f, xs, null) raises(TypeError)`; if not, make f skip or fill the null slot; or accept it as a discovery: mathema accept mv.total missing[xs, null] --as discovery --corrected "missing(f, xs, null) raises(TypeError)"
  holds   missing[xs, nan]: missing(f, xs, nan) propagates   [default for a list slot that may be nan; confirmed on the 53 draws of c[float]. Keep it by writing it (mathema claims mv.total --write), or change the word to raises or drops if f should do otherwise]
mathema.Record(mean_np) · source, no side effects · form ce47d44bdab7
  holds   c: for xs in ([0.0, 1.0] | {missing})^n : float, 0 <= f(xs) <= 1 (111 draws, sizes (1, 1) to (8, 1), 676 entries in all)
           every link of the chained comparison holds; at xs = [nan] f gave nan back
  proven  missing[xs]: missing(f, xs) propagates   [from numpy.mean's own policy row, which f calls; confirmed on the 111 draws of c]
```

`sum` treats the two members of a list slot differently: it raises on a
`None` element and gives a `nan` back. The record says so member by
member, and the claim to write names the member. `np.mean` gives the
hole back, and the row comes from numpy's own. A pandas mean is a
longer story, told in [the mean of nothing](mean-of-nothing.md).

## Policy rows, defaults and `mathema claims --write`

A policy row is a claim like any other, in one short form:

<!-- illustration -->
```text
missing(f, x) propagates
absent(f, x) raises(TypeError)
missing(f, xs, null) raises(TypeError)
assuming count(xs) >= 1, missing(f, xs) drops
absent(f) introduces
```

The member narrows a row to one spelling; a premise on `count(...)`
(the number of value slots) splits a behaviour where the count decides
it. Where a kind reaches a parameter, the record carries a row for it,
and the bracket says where it came from:

- **default for a float, which may be nan**: the type alone admits the
  kind and you said nothing. A hole propagates by default; a `None` an
  unannotated parameter may take raises.
- **from math.sqrt's own policy row** or **from the guard on line 2**:
  the code says it.
- **observed**: you admitted the kind (an `Optional`, a listed `None`),
  so there is no default word; what the code did is written, and a raise
  stays unaccounted for until you state it.
- **stated**: yours.

`mathema claims` lists a function's rows by state, and `--write` puts
the ones the code confirms in your claims file, where changing a policy
is editing one word:

<!-- example: write file=pricing.py -->
```python
import math


def root(x: float) -> float:
    """Claims:
        nonneg: for x in [0, 4], f(x) >= 0
    """
    return math.sqrt(x)


def clamp01(x: float) -> float:
    """Claims:
        unit: for x in R, 0 <= f(x) <= 1
    """
    return max(0.0, min(1.0, x))
```

<!-- example: write session -->
```
$ mathema claims pricing.clamp01
pricing.clamp01: no declared claims (mathema claims --suggest lists candidates)
pricing.clamp01: 1 policy row about x
  contradicted by the code (choose the word, or change the code; --write leaves these out):
    FALSIFY missing[x]: missing(f, x) propagates   [default for a float; f drops instead: nan in, 1.0 out]
             if 1.0 is the answer f should give for a missing x, write `missing(f, x) drops`; if not, make f raise or give nan back; or accept it as a discovery: mathema accept pricing.clamp01 missing[x] --as discovery --corrected "missing(f, x) drops"
```

<!-- example: write session -->
```
$ mathema claims pricing.root --write
pricing.root: wrote 1 policy row to claims/policies.claims.yaml: missing[x]
```

<!-- example: write session -->
```
$ cat claims/policies.claims.yaml
pricing.root:
  claims:
  - name: missing[x]
    statement: missing(f, x) propagates
    note: from math.sqrt's own policy row, which f calls; confirmed on the 43 draws
      of nonneg[float]
```

A contradicted row is never written: you choose the word, `drops` if
`1.0` is the answer for a missing `x`, and state it.

## Definitions: which values are holes

Which values a runtime holds as missing is a **definition**, stated once
under the runtime type, `missing := {null, nan}`, and taken at face
value. mathema ships the ones for pandas and polars; a project adds its
own the same way (see [definitions](claims-transfer.md#definitions)).
A claim over a polars Series then resolves `missing` to that runtime's
members, and the record says so:

<!-- example: defines run -->
```python
import polars as pl

import mathema


def total_pl(xs: pl.Series) -> float:
    return float(xs.sum())


rec = mathema.check(total_pl, claims=[mathema.claim(
    "for xs in [0, 1]^n, f(xs) >= 0", name="c")])
(row,) = [p for p in rec.probes if p.name == "c"]
print(row.meta["mathema.missing"]["means"])
```

<!-- example: defines output -->
```text
missing for xs (polars.Series) means null or nan
```

## The gates and `enforce_domain`

A policy row is one fact about one parameter. `is_missing_safe(f)` and
`is_absent_safe(f)` state complete knowledge: every parameter that
admits the kind has a policy the code follows at every member. They are
proven when each member's policy comes from the code or is stated and
confirmed, hold when some member is confirmed by running it alone, and
are falsified by a contradiction, a member treated more than one way, a
raise no claim accounts for, or a `None` from present inputs the return
type does not declare. mathema offers them (`mathema claims KEY
--suggest`) and never asserts them for you.

<!-- example: gates file=mv.py -->
```python
import math
from typing import Optional


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)
```

<!-- example: gates run -->
```python
import mathema
from mv import root_opt

print(mathema.check(root_opt, claims=[mathema.claim("for x in [0, 4], f(x) >= 0"),
                                      mathema.claim("is_missing_safe(f)"),
                                      mathema.claim("is_absent_safe(f)")]))
```

<!-- example: gates output match=subset -->
```text
mathema.Record(root_opt) · source, no side effects · form 04f945e667a0
  proven  is_missing_safe[f]: is_missing_safe(f)
           x (float): nan propagates, from math.sqrt's own policy row
  FALSIFY is_absent_safe[f]: is_absent_safe(f)
           x (float): None raises TypeError, unaccounted
           counterexample x = None: f raised TypeError
```

`@enforce_domain()` turns the policy rows into a runtime guarantee. It
is opt-in. A `raises` row rejects the input at entry with a
`MissingValueError` (a `DomainError`) that names the parameter and the
member; a `drops` or `propagates` row is checked on the result;
`converts` and `introduces` enforce nothing:

<!-- example: enforce run -->
```python
import math
from typing import Optional

import mathema


@mathema.enforce_domain()
@mathema.claims_decorator("absent(f, x) raises(TypeError)",
                          "missing(f, x) propagates")
def root(x: Optional[float]) -> float:
    return math.sqrt(x) if x == x else 0.0


for arg in (None, float("nan"), 4.0):
    try:
        print(root(arg))
    except mathema.MissingValueError as exc:
        print(exc)
```

<!-- example: enforce output -->
```text
root(): x = None is absent, and its policy says f raises there (absent(f, x) raises(TypeError))
root(): x = nan in, 0.0 out: f drops the hole, and its policy says propagates (missing(f, x) propagates)
2.0
```

## What is not missing

- An empty container: zero slots, so no holes; `is_empty_safe(xs)`
  asks what the function does there.
- An infinity: a value. An infinity from a finite input fails a value
  claim, as a `nan` from present inputs does.
- A row a function filters out of a table: a change of shape, not a
  hole.

## What changed in 0.6.1

- The two words, `absent` and `missing` (`None` still reads as
  `absent`), with the members `nan`, `null`, `NA` and `NaT`; a domain
  renders what it admits.
- A value claim is judged on values; a missing input is classified into
  one of the five behaviours.
- Policy rows, their defaults, `mathema claims --write`, and the bundled
  policy rows for `math`, numpy, pandas and polars.
- `is_missing_safe(f)`, `is_absent_safe(f)`, `is_empty_safe` realised
  through the runtime type, and `enforce_domain` reading the policy
  rows.
