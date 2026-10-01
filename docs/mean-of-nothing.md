# The mean of nothing

A one-line function, the kind every analytics codebase has, and a
question its tests never ask: what does it do when there is nothing to
average? This page follows mathema from the first claim to the fix,
showing the record at each step.

<!-- example: mean file=returns.py -->
```python
import pandas as pd


def mean_return(xs: pd.Series) -> float:
    """The mean of a series of returns."""
    return float(xs.mean())
```

The series it will meet, slot by slot:

<!-- illustration -->
```text
[0.02, NaN, -0.01]     slot 1 is a hole (member nan): pandas skips it, mean 0.005
[NaN, None]            every slot a hole (members nan, null): pandas gives NaN
[<NA>]                 every slot a hole (member NA): xs.mean() is pd.NA
[]                     no slots at all: empty, not missing
```

## The value claim holds

A mean of returns in `[-1, 1]` lies in `[-1, 1]`:

<!-- example: mean run -->
```python
import mathema
from returns import mean_return

value = mathema.claim("for xs in [-1, 1]^n, -1 <= f(xs) <= 1", name="bounded")
print(mathema.check(mean_return, claims=[value]))
```

<!-- example: mean output match=subset -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  holds   bounded: for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1 (617 entries across 118 draws, sizes (1, 1) to (8, 1))
           every link of the chained comparison holds; f drops a missing slot when values remain (xs = [nan, 0.317, -0.0865, 0.455, 1]) and gives a hole back when every slot is missing (xs = [nan], [null]); at an all-NA series it raises TypeError instead
```

It holds on every value `mean_return` returns. The note says what
happened at the missing inputs the draws carried: a pandas Series slot
can be `nan`, `null` (a `None` element) or `NA`, and mathema put each
one in. pandas skips missing slots in a mean, so a partly missing series
still has a mean. When every slot is missing there is no value to
average and pandas gives a hole back, `nan`, which is no value to
judge, so the value claim is not asked there. And at an all-`NA` series
the function raises: `xs.mean()` is `pd.NA`, and `float(pd.NA)` raises
`TypeError`.

## The policy rows say what pandas promised

The same record carries the policy rows, what `mean_return` does with a
value that is not there:

<!-- example: mean run -->
```python
record = mathema.check(mean_return, claims=[value])
print(record)
```

<!-- example: mean output match=subset -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  proven  missing[xs, count >= 1]: assuming count(xs) >= 1, missing(f, xs) drops   [from pandas.Series.mean's own policy row, which f calls; confirmed on the 118 draws of bounded]
  FALSIFY missing[xs, count == 0]: assuming count(xs) == 0, missing(f, xs) propagates   [from pandas.Series.mean's own policy row, which f calls; f raises TypeError instead at xs = [NA]]
           state `assuming count(xs) == 0, missing(f, xs, nan) propagates`, `assuming count(xs) == 0, missing(f, xs, null) propagates` and `assuming count(xs) == 0, missing(f, xs, NA) raises(TypeError)` if that is intended, or change f
```

`mean_return` makes one library call, and pandas' own policy rows
(bundled with mathema) say what `Series.mean` does: it drops holes while
values remain, and gives a hole back when none do. `count(xs)` is the
number of value slots, so the premises split the calls exactly where
pandas does. The first row is proven. The second is falsified: at `xs = [NA]`
the function raises where pandas' row says a hole comes back. The
record names the three claims that would state what the code does, one
per member.

## The gate: is it missing-safe?

`is_missing_safe(f)` asks whether every missing member has a policy the
code follows:

<!-- example: mean run -->
```python
print(mathema.check(mean_return, claims=[value, mathema.claim("is_missing_safe(f)")]))
```

<!-- example: mean output match=subset -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  FALSIFY is_missing_safe[f]: is_missing_safe(f)
           xs (pandas.Series): nan and null follow pandas.Series.mean's own policy row (drops when values remain, propagates when every slot is missing); NA does not: f raises TypeError when every slot is NA
           counterexample xs = [NA]: f raised TypeError
```

`nan` and `null` follow pandas' rows. `NA` does not, and no claim says
it may raise, so the gate is falsified with the call that shows it.

## And with no slots at all?

An empty series has no slots, so no holes; it is a question of its own,
`is_empty_safe(xs)`, and mathema builds the empty value as the
parameter's own runtime type, an empty float Series:

<!-- example: mean run -->
```python
print(mathema.check(mean_return, claims=[value, mathema.claim("is_empty_safe(xs)")]))
```

<!-- example: mean output match=subset -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  FALSIFY is_empty_safe[xs]: is_empty_safe(xs)
           counterexample xs = [] (an empty float Series): f returned nan for the empty input; raise, or return a value
```

The mean of nothing is `nan` in pandas, as in numpy; `statistics.mean`
raises, and polars gives `None`. A `nan` handed back for the empty input
looks like a number to the caller and poisons whatever it touches next.

## The fix

The function has no mean to give when no value is there, so it says so,
once, for the empty series and the all-missing one alike:

<!-- example: mean file=returns_fixed.py -->
```python
import pandas as pd


def mean_return(xs: pd.Series) -> float:
    """The mean of a series of returns."""
    if xs.count() == 0:
        raise ValueError("no returns to average")
    return float(xs.mean())
```

That raise is a choice, so it is stated as the policy for the calls
with no value slot, beside the row pandas already gives for the rest:

<!-- example: mean run -->
```python
import returns_fixed

print(mathema.check(returns_fixed.mean_return, claims=[
    value,
    mathema.claim("assuming count(xs) == 0, missing(f, xs) raises(ValueError)",
                  name="no_values"),
    mathema.claim("is_missing_safe(f)"),
    mathema.claim("is_empty_safe(xs)"),
]))
```

<!-- example: mean output match=subset -->
```text
mathema.Record(mean_return) · source, no side effects · form 9671b357ded6
  holds   bounded: for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1 (768 entries across 149 draws, sizes (1, 1) to (8, 1))
           every link of the chained comparison holds; f drops a missing slot when values remain (xs = [nan, 0.317, -0.0865, 0.455, 1]); when every slot is missing (nan, null, NA) it raises ValueError instead
  proven  is_empty_safe[xs]: is_empty_safe(xs)
  holds   no_values: assuming count(xs) == 0, missing(f, xs) raises(ValueError)   [stated; confirmed on the 149 draws of bounded]
  proven  is_missing_safe[f]: is_missing_safe(f)
           xs (pandas.Series): nan, null and NA drop when values remain, from pandas.Series.mean's own policy row; raises ValueError when every slot is missing, stated
  proven  missing[xs, count >= 1]: assuming count(xs) >= 1, missing(f, xs) drops   [from pandas.Series.mean's own policy row, which f calls; confirmed on the 149 draws of bounded]
```

Every member now has a policy the code follows, from pandas' row where
values remain and from the stated one where none do, so the gate is
proven; the empty series meets the guard, a deliberate rejection, so
`is_empty_safe` is proven too. The value claim still holds on every
value, and the note now says the function raises `ValueError` wherever
every slot is missing.

See [missing values](missing-values.md) for the two kinds, the five
behaviours and the policy rows in general.
