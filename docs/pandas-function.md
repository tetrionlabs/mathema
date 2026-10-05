# Claims about a pandas function

The [quick start](quickstart.md) took a claim about a scalar function
from falsified to proven. This page does the same for a function that
takes a pandas `Series`, and shows the two things that change: how mathema
hands the function a real `Series`, and how a claim about it is proven for
every length of the series, with nothing missing in it, by reading the
pandas calls in the body.

It needs the `pandas` extra (`pip install "mathema[pandas]"`).

## The function

A strategy's daily returns, and two numbers a desk computes from them:

<!-- example: pandas file=returns.py -->
```python
import numpy as np
import pandas as pd


def average_return(returns: pd.Series) -> float:
    """The mean of a series of periodic returns."""
    return float(returns.mean())


def sharpe(returns: pd.Series) -> float:
    """The annualised Sharpe ratio of daily returns, at a zero risk-free rate."""
    return returns.mean() / returns.std(ddof=1) * np.sqrt(252)
```

## A first claim, and what the function received

The average of a series lies between its smallest and its largest value.
`returns in [-0.1, 0.1]^n` says: a vector of one or more entries, every
entry between a 10 percent loss and a 10 percent gain. A float entry may
also be missing (`nan`, or pandas' `NA`), and `\ {missing}` takes those
out, so this claim is about series with every day present. What a
function does with a missing day is a separate question, with its own
page: [Missing values](missing-values.md).

<!-- example: pandas run requires=pandas -->
```python
import mathema
from returns import average_return

record = mathema.check(average_return, claims=[
    "for returns in [-0.1, 0.1]^n \\ {missing}, min(returns) <= f(returns) <= max(returns)"])
print(record)
```

<!-- example: pandas output wrap=80 -->
```text
mathema.Record(average_return) · source, no side effects · form cb973acd88fd
  proven    min_returns_le_f_returns_le_max_returns: for returns in [-0.1,
      0.1]^n : float, min(returns) <= f(returns) <= max(returns)
           ∀ returns over [-0.1, 0.1] with nothing missing, returns of every
               length of at least one
```

The claim is `proven`, and the line under it says over what: every
series with entries in the range, of every length of at least one, with
nothing missing. The `: float` after the range is what mathema resolved
`[-0.1, 0.1]^n \ {missing}` to: float entries, none of them missing. The
signature says `returns: pd.Series`, so whenever mathema runs the
function it first builds a `Series` from the vector it drew; had the
parameter been annotated `np.ndarray`, it would build an array instead,
and a parameter nothing names is passed as a list.

The proof itself came from reading the body. `returns.mean()` is a call
mathema knows: it ships a definition row for `pandas.Series.mean`, a
claim stating what the method computes in the grammar's own words, and
with the call read through that row the claim becomes a statement about
sums over a sequence of symbolic length:

<!-- example: pandas run requires=pandas -->
```python
import textwrap

print(textwrap.fill(record.probes[0].sketch, 78))
```

<!-- example: pandas output -->
```text
link 1: min(returns) <= f(returns): taking pandas.Series.mean as mean(a)
(axiom, bundled with mathema, pandas 2 to 3.x); through the pandas.Series.mean
definition row, lowered to sums over returns at a symbolic length: the
relation holds for every length of at least one (min(returns) is at most
mean(returns)); link 2: f(returns) <= max(returns): taking pandas.Series.mean
as mean(a) (axiom, bundled with mathema, pandas 2 to 3.x); through the
pandas.Series.mean definition row, lowered to sums over returns at a symbolic
length: the relation holds for every length of at least one (max(returns) is
at least mean(returns))
```

## A claim that is wrong, and the witness

A Sharpe ratio is unchanged by leverage: scale every return by the same
positive `c` and the ratio comes out the same. `let s = mathema.f.scale_seq`
names that scaling, `let c be [0.1, 10]` the range of leverage, and `~=`
asks for equality up to floating-point tolerance:

<!-- example: pandas run requires=pandas -->
```python
from returns import sharpe

record = mathema.check(sharpe, claims=[mathema.claim(
    "for returns in [-0.1, 0.1]^n \\ {missing}, let s = mathema.f.scale_seq, "
    "let c be [0.1, 10], f(s(returns, c)) ~= f(returns)",
    name="leverage_invariant")])
print(record)
```

<!-- example: pandas output wrap=80 -->
```text
mathema.Record(sharpe) · source, no side effects · form 099872a2a5ee
  leverage_invariant  let s = mathema.f.scale_seq, let c be [0.1, 10.0], for
      returns in [-0.1, 0.1]^n : float, f(s(returns, c)) ~= f(returns)
      falsified at returns = [0.0], c = 4.2636586502253655
    falsified  mathematics  let s = mathema.f.scale_seq, let c be [0.1, 10.0],
        for returns in [-0.1, 0.1]^n ⊂ ℝ, f(s(returns, c)) ~= f(returns)
        counterexample returns = [0.0], c = 4.2636586502253655: the computation
        returns NaN here (f returned nan)
    holds      policy       f([])
```

The headline carries the witness, and the lines under it say where it
came from. The `mathematics` line is falsified at that point; the
`policy` line covers the empty series, tried separately, and holds.

Read the witness. `returns = [0.0]` is a series of one day. Its standard
deviation with `ddof=1` is undefined, pandas returns NaN, and `sharpe`
returns NaN with it. NaN is no value, so the claim has no value at that
point, and a claim with no value at a point inside its domain is
falsified there. The code is right: a one-day series has no Sharpe
ratio. The claim was too wide, because it never said which series it was
about.

## Say what the claim is about

A premise, written after `assuming`, names the series the ratio is
defined for: here `std(returns, ddof=1) > 0`.

<!-- example: pandas run requires=pandas -->
```python
record = mathema.check(sharpe, claims=[mathema.claim(
    "for returns in [-0.1, 0.1]^n \\ {missing}, let s = mathema.f.scale_seq, "
    "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
    "f(s(returns, c)) ~= f(returns)",
    name="leverage_invariant")])
print(record)
```

<!-- example: pandas output wrap=80 -->
```text
mathema.Record(sharpe) · source, no side effects · form 099872a2a5ee
  leverage_invariant  assuming std(returns, ddof=1) > 0, let s =
      mathema.f.scale_seq, let c be [0.1, 10.0], for returns in [-0.1, 0.1]^n :
      float, f(s(returns, c)) ~= f(returns)   proven
    proven     mathematics  assuming std(returns, ddof=1) > 0, let s =
        mathema.f.scale_seq, let c be [0.1, 10.0], for returns in [-0.1, 0.1]^n
        ⊂ ℝ, f(s(returns, c)) ~= f(returns)
    holds      computation  assuming std(returns, ddof=1) > 0, let s =
        mathema.f.scale_seq, let c be [0.1, 10.0], for returns in [-0.1, 0.1]^n
        : float, f(s(returns, c)) ~= f(returns)   166 entries across 34 draws,
        sizes (2, 1) to (8, 1)
    holds      policy       f([])
```

The `mathematics` line is proven, and the `computation` line runs the
same claim through the real code in floating point, on 34 seeded
series of two to eight days, and holds. The premise took the one-day
series out, and mathema reads it exactly. The standard deviation of equal returns is 0 over the reals, so
a constant series is outside the claim too, on both lines alike: mathema computes the premise's `std` exactly rather than
through the function's floating point, so a constant series whose float
standard deviation rounds to `1e-17` is still outside.

The proof rested on two rows this time. The record names each one, with
the file it came from:

<!-- example: pandas run requires=pandas -->
```python
proof = record.probes[0]
print(textwrap.fill(proof.sketch, 78))
for row in proof.meta["mathema.definitions"]:
    print(row["key"], row["source"])
```

<!-- example: pandas output -->
```text
taking pandas.Series.mean as mean(a) (axiom, bundled with mathema, pandas 2 to
3.x); taking pandas.Series.std as std(a, ddof=1) (axiom, bundled with mathema,
pandas 2 to 3.x); through the pandas.Series.mean definition and
pandas.Series.std definition rows, lowered to sums over returns at a symbolic
length: the relation holds for every length
pandas.Series.mean mathema/compendium/pandas/series.claims.yaml
pandas.Series.std mathema/compendium/pandas/series.claims.yaml
```

## A claim that is false and stays false

Adding a constant to every return is a different matter: the mean moves
and the standard deviation does not, so the ratio changes. State it as if
it were invariant, and the witness shows both sides:

<!-- example: pandas run requires=pandas -->
```python
record = mathema.check(sharpe, claims=[mathema.claim(
    "for returns in [-0.1, 0.1]^n \\ {missing}, let s = mathema.f.shift_seq, "
    "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
    "f(s(returns, c)) ~= f(returns)",
    name="shift_invariant")])
print(record.probes[0].verdict)
print(record.probes[0].counterexample)
```

<!-- example: pandas output -->
```text
falsified
returns = [-0.04129585799119448, 0.003979158413648126, 0, 0.0423245296012931, 0.02250156794927212, 0.0999998, 0]; c = 6.86: 2471.7681022329703 vs 6.5493395473758484
```

Seven days of returns, each shifted up by 6.86: a Sharpe ratio of about
2,472 against the original's 6.5. Sampling is seeded, so the same
witness comes back on every run.

## Where next

- [Runtime types](runtime-types.md) is the reference behind this page:
  how a parameter's runtime type is read from the signature, the hint
  mathema prints when a body uses a list as a `Series`, and claims over
  `DataFrame` columns.
- [The evidence ladder](evidence-ladder.md) places `proven` and the
  computation line under it on their rungs.
- [See what mathema knows about a library you call](library-claims.md)
  shows which of the pandas and numpy calls your code makes have rows like
  the two above, and how to state one for a call nothing covers.
- [The claim grammar](grammar.md) has one example per form used here:
  `[a, b]^n`, `let c be [0.1, 10]`, `let s = mathema.f.scale_seq`, a
  premise such as `std(returns, ddof=1) > 0` written after `assuming`,
  and `~=`.
