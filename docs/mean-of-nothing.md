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

## The claim, and what pandas promised

A mean of returns in `[-1, 1]` lies in `[-1, 1]`:

<!-- example: mean run requires=pandas -->
```python
import mathema
from returns import mean_return

value = mathema.claim("for xs in [-1, 1]^n, -1 <= f(xs) <= 1", name="bounded")
print(mathema.check(mean_return, claims=[value]))
```

<!-- example: mean output -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  bounded  for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1   falsified at xs = []
    holds      computation  for xs in ([-1.0, 1.0])^n : float, -1 <= f(xs) <= 1   445 entries across 99 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f([])   f(xs) returns nan at xs = []: no value for no data, and no empty policy is stated
                            possible fixes:
                              (i) if nan for no data is intended, state: mean_return([]) in {missing}
                              (ii) guard the empty input at entry
    proven     policy       f([..., missing, ...]) assuming count(xs) >= 1   drops, from pandas.Series.mean's own policy row, which f calls
    falsified  policy       f([..., missing, ...]) assuming count(xs) == 0   raises TypeError, where the word is propagates (from pandas.Series.mean's own policy row, which f calls)
                            possible fixes:
                              (i) exclude missing
                              (ii) handle missing at entry
```

Read it from the top. The headline is the claim as mathema resolved it:
a float slot may be missing, so `[-1, 1]^n` became
`([-1.0, 1.0] | {missing})^n`. The `computation` line holds on every
series of values it ran: a mean of numbers in `[-1, 1]` stays there.

The `f([])` line is the empty series: its mean is `nan`, which counts
as no value until a policy for the empty input is stated, and that is
the headline's witness (the last section returns to it).

The other two `policy` lines say what `mean_return` does with a slot
that is not there. A pandas Series slot can be `nan`, `null` (a `None`
element) or `NA`, and mathema put each one in. `mean_return` makes one
library call, and pandas' own policy rows (bundled with mathema) say
what `Series.mean` does: it drops holes while values remain, and gives a
hole back when none do. Each line names its case after `assuming`. The
first, a series with a value left (`count(xs) >= 1`), is that first row,
proven. The second, a series with none (`count(xs) == 0`), is the second
row, and it is falsified: at
`xs = [NA]`, a series whose only slot is pandas' `NA`, `xs.mean()` is
`pd.NA` and `float(pd.NA)` raises `TypeError`, where pandas' row says a
hole comes back.

## The gate: is it missing-safe?

`is_missing_safe(f)` asks whether every missing member has a policy the
code follows:

<!-- example: mean run -->
```python
print(mathema.check(mean_return, claims=[value, mathema.claim("is_missing_safe(f)")]))
```

<!-- example: mean output -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  bounded  for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1   falsified at xs = []
    holds      computation  for xs in ([-1.0, 1.0])^n : float, -1 <= f(xs) <= 1   445 entries across 99 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f([])   f(xs) returns nan at xs = []: no value for no data, and no empty policy is stated
                            possible fixes:
                              (i) if nan for no data is intended, state: mean_return([]) in {missing}
                              (ii) guard the empty input at entry
    proven     policy       f([..., missing, ...]) assuming count(xs) >= 1   drops, from pandas.Series.mean's own policy row, which f calls
    falsified  policy       f([..., missing, ...]) assuming count(xs) == 0   raises TypeError, where the word is propagates (from pandas.Series.mean's own policy row, which f calls)
                            possible fixes:
                              (i) exclude missing
                              (ii) handle missing at entry
  falsified is_missing_safe[f]: is_missing_safe(f)
           xs (pandas.Series): nan and null follow pandas.Series.mean's own policy row (drops when values remain, propagates when every slot is missing); NA does not: f raises TypeError when every slot is NA
           counterexample xs = [NA]: f raised TypeError
           (i) if the raise is intended, state: assuming count(xs) == 0, missing(f, xs, NA) raises(TypeError)
           (ii) if not, change f
```

The value claim's block repeats above it, since the gate is checked
beside it. `nan` and `null` follow pandas' rows. `NA` does not, and no
claim says it may raise, so the gate is falsified with the call that
shows it, and with the claim that would state the raise if it is what
you meant.

## And with no slots at all?

An empty series has no slots, so no holes; it is a question of its own,
`is_empty_safe(xs)`, and mathema builds the empty value as the
parameter's own runtime type, an empty float Series:

<!-- example: mean run -->
```python
print(mathema.check(mean_return, claims=[value, mathema.claim("is_empty_safe(xs)")]))
```

<!-- example: mean output -->
```text
mathema.Record(mean_return) · source, no side effects · form cb973acd88fd
  bounded  for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1   falsified at xs = []
    holds      computation  for xs in ([-1.0, 1.0])^n : float, -1 <= f(xs) <= 1   445 entries across 99 draws, sizes (1, 1) to (8, 1)
    falsified  policy       f([])   f(xs) returns nan at xs = []: no value for no data, and no empty policy is stated
                            possible fixes:
                              (i) if nan for no data is intended, state: mean_return([]) in {missing}
                              (ii) guard the empty input at entry
    proven     policy       f([..., missing, ...]) assuming count(xs) >= 1   drops, from pandas.Series.mean's own policy row, which f calls
    falsified  policy       f([..., missing, ...]) assuming count(xs) == 0   raises TypeError, where the word is propagates (from pandas.Series.mean's own policy row, which f calls)
                            possible fixes:
                              (i) exclude missing
                              (ii) handle missing at entry
  falsified is_empty_safe[xs]: is_empty_safe(xs)
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

<!-- example: mean output -->
```text
mathema.Record(mean_return) · source, no side effects · form 9671b357ded6
  bounded  for xs in ([-1.0, 1.0] | {missing})^n : float, -1 <= f(xs) <= 1   holds
    holds      computation  for xs in ([-1.0, 1.0])^n : float, -1 <= f(xs) <= 1   531 entries across 124 draws, sizes (1, 1) to (8, 1)
    holds      policy       f([])
    proven     policy       f([..., missing, ...]) assuming count(xs) >= 1   drops, from pandas.Series.mean's own policy row, which f calls
  proven    is_empty_safe[xs]: is_empty_safe(xs)
  holds     no_values: assuming count(xs) == 0, missing(f, xs) raises(ValueError)   [stated; confirmed on the 124 draws of bounded]
  proven    is_missing_safe[f]: is_missing_safe(f)
           xs (pandas.Series): nan, null and NA drop when values remain, from pandas.Series.mean's own policy row; raises ValueError when every slot is missing, stated
```

Every member now has a policy the code follows, from pandas' row where
values remain and from the stated one where none do, so the gate is
proven; the empty series meets the guard, a deliberate rejection, so
`is_empty_safe` is proven too. The value claim holds, and its headline
with it: the policy lines under it are the empty series, which meets
the guard, and pandas' row for a series with values in it, and the
stated `no_values` covers the rest.

See [missing values](missing-values.md) for the two kinds, the five
behaviours and the policy rows in general.
