# Runtime types

A claim about a vector, a matrix or a table says nothing about the
object the code receives. `for xs in R^n, min(xs) <= f(xs) <= max(xs)`
is the same claim whether `f` takes a Python list, a `numpy.ndarray`, a
`pandas.Series` or a `polars.Series`. What the code receives is its
**runtime type**, and mathema samples each parameter as the runtime
type its signature names.

A value is drawn as mathema has always drawn it, a vector of numbers
with some positions possibly missing, then handed to the parameter's
**runtime type adapter**, which realises it as the object the function
expects just before each call. What the function returns is observed
back into a plain value before anything compares it: a `Series` result
compares as a vector, a `numpy.float64` as a number, a 2-D array as a
matrix. The draw, and any transform a law applies to it
(`mathema.f.scale_seq`, say), acts on the value before it is realised.

<!-- example: rt-mean run requires=pandas -->
```python
import numpy as np
import pandas as pd


def mean_of(xs: np.ndarray):
    return float(xs.mean())


def series_mean(xs: pd.Series):
    return float(xs.mean())
```

<!-- example: rt-mean verdicts fn=mean_of route=probe requires=pandas -->
```
for xs in R^n, min(xs) <= f(xs) <= max(xs)   # holds
```

<!-- example: rt-mean verdicts fn=series_mean route=probe requires=pandas -->
```
for xs in R^n, min(xs) <= f(xs) <= max(xs)   # holds
```

Sampled as a list, as it was before runtime types, `mean_of` raises
`AttributeError` (a list has no `.mean()`) and the claim is falsified;
sampled as the array its signature names, it holds.

## Detection, from the signature only

A parameter's runtime type is read from the signature, strongest
evidence first:

1. a marker: `Vec("n", runtime="pandas.Series")`, or `Mat("n", "n",
   runtime="numpy.ndarray")` for a matrix (see [matrix
   structure](matrix-structure.md));
2. the live annotation, as `typing.get_type_hints` resolves it:
   `np.ndarray`, `npt.NDArray[np.float64]`, `pd.Series`,
   `pd.DataFrame`, `pl.Series`, `pl.DataFrame`. A union gives one
   runtime type per member, and the first is sampled
   (`pd.Series | pd.DataFrame` is sampled as a Series);
3. the annotation's source text, when the hints do not resolve (a name
   imported only under `TYPE_CHECKING`, say), read through the
   module's own aliases and the usual `np`, `pd` and `pl`;
4. for code that cannot be annotated, a claims-file entry's
   `runtime_types:` field, used only for a parameter the signature
   says nothing about:

```yaml
risk.stats.sharpe:
  runtime_types:
    returns: pandas.Series
  claims:
    - statement: "for returns in [-0.1, 0.1]^n, f(returns) == f(returns)"
```

A docstring never decides a runtime type, and mathema never tries
runtime types one after another until the function accepts one. A
parameter nothing names is sampled as a list, exactly as before.

The record's identity names each parameter sampled as something other
than a list, with its evidence and the library version its semantics
hold under:

```yaml
identity:
  runtime_types:
    returns: {type: pandas.Series, evidence: "annotation: pandas.Series",
              library: pandas==3.0.6}
```

A proof's computation companion names the runtime type after the
number representation it computes in: `sharpe[float, pandas.Series]`.
A counterexample shows the drawn values as plain numbers, and the
sampling note says what they were realised as (`as pandas.Series`).

## The hint

When the body uses a parameter as a vector, a matrix or a table (a
method such as `.mean()` or `.std()`, `np.mean(x)`, `.T`, `@`,
indexing, a column read by name) but the signature names no runtime
type, the parameter is still sampled as a list, and in a module that
imports numpy, pandas or polars the record names the runtime type to
annotate:

<!-- illustration -->
```text
returns is used as a vector; this module imports pandas: annotate `returns: pd.Series` to sample it as one
```

The hint rides the note of every claim on the function when a list
cannot serve the use (a list has no `.mean()`), and `mathema check`
prints it under the function. When the function raises a
`TypeError`, `ValueError` or `AttributeError` on the list, the claim
is `skipped:misspecified` with the same hint, never `falsified`: the
list was the wrong object to hand the function. With a runtime type
declared, a raise falsifies as always.

## The built-in runtime types

| runtime type | carries | a missing position | notes |
|---|---|---|---|
| `list` (and `tuple`) | vector, matrix (nested lists), table (dict of lists) | `None`, NaN | a matrix is drawn as nested lists up to 64 per axis |
| `numpy.ndarray` | vector (1-D), matrix (2-D) | NaN | |
| `pandas.Series` | vector | NaN, `None`, `pd.NA` | a business-day index from 2020-01-01 |
| `pandas.DataFrame` | table | NaN, `None`, `pd.NA` | the Series index |
| `polars.Series` | vector | null, NaN | |
| `polars.DataFrame` | table | null, NaN | |

Missing is one concept in mathema, whatever a library calls it: every
spelling in the table reads back as missing when a function returns
it, a polars NaN included (polars itself treats NaN as an ordinary
float), and an adapter can realise a missing position in each of its
spellings (the first one listed is the one it uses by default).

numpy, pandas and polars stay optional: an adapter whose library is not
installed is absent, and a parameter it would have claimed is sampled
as a list. Install them with the `numpy`, `pandas` and `polars`
extras.

## Series and DataFrames in claims

A claim over vectors reads the same whatever the runtime type: the
drawn vector is evaluated as an array, the function receives its own
runtime type, and a returned `Series`, `DataFrame` or array compares
element by element. So one claim text holds for a `numpy.ndarray`, a
`pandas.Series` and a `polars.Series` alike, and every vector construct
works on it: `norm`, `dot`, `mean`, `returns * c`, `returns + c` (see
[matrix structure](matrix-structure.md) for what each operator means).

<!-- example: rt-series run requires=pandas -->
```python
import numpy as np
import pandas as pd
import polars as pl


def scale_numpy(returns: np.ndarray, c: float):
    return returns * c


def scale_pandas(returns: pd.Series, c: float):
    return returns * c


def scale_polars(returns: pl.Series, c: float):
    return returns * c
```

<!-- example: rt-series verdicts fn=scale_pandas requires=pandas -->
```
for returns in R^n, c in [-2, 2], f(returns, c) == c * returns   # holds
for returns in R^n, c in [-2, 2], norm(f(returns, c)) ~= abs(c) * norm(returns)   # holds
for returns in R^n, c in [-2, 2], mean(f(returns, c)) ~= c * mean(returns)   # holds
for returns in R^n, c in [-2, 2], mean(f(returns, c)) ~= mean(returns) + c   # falsified
```

<!-- example: rt-series verdicts fn=scale_polars requires=polars -->
```
for returns in R^n, c in [-2, 2], f(returns, c) == c * returns   # holds
for returns in R^n, c in [-2, 2], dot(f(returns, c), returns) ~= c * norm(returns)**2   # holds
```

A table parameter (a `pandas.DataFrame` or `polars.DataFrame`) is drawn
with one column per name the claim or the body reads, and a claim reads
a column as a vector, by attribute or by item: `df.returns`,
`df["returns"]`. A returned DataFrame compares with another column by
column, and its own columns read the same way (`f(df)["a"]`); the
arithmetic of a whole table (`f(df) - 1`) is not claim syntax yet.

<!-- example: rt-frame run requires=pandas -->
```python
import pandas as pd


def scale_column(df: pd.DataFrame, c: float):
    return df["returns"] * c


def shifted(df: pd.DataFrame):
    return df + 1
```

<!-- example: rt-frame verdicts fn=scale_column requires=pandas -->
```
for c in [-2, 2], f(df, c) == c * df.returns   # holds
for c in [-2, 2], f(df, c) == c * df["returns"]   # holds
for c in [-2, 2], f(df, c) == df.returns + c   # falsified
```

<!-- example: rt-frame verdicts fn=shifted requires=pandas -->
```
f(df)["a"] == df["a"] + 1   # holds
f(df) == df   # falsified
```

The derive route reads a Series or array method through its
definition row (next section), and a column of a DataFrame as a vector
of its own, whose methods read through the Series rows.

## Proofs on pandas and numpy code

A body such as `returns.mean() / returns.std(ddof=1) * np.sqrt(252)`
is proven on the derive route, for every length of `returns`, by
reading each library call through its **definition row**: a library
claim that states what the function computes in the grammar's own
words (`pandas.Series.std` is `std(a, ddof=1)`, see
[claims transfer](claims-transfer.md#definition-rows)). The call
`returns.std(ddof=1)` resolves through the parameter's runtime type to
the key `pandas.Series.std`, `np.mean(returns)` through the module's
imports to `numpy.mean`, and `A.T` on an array to `numpy.ndarray.T`;
the call's arguments are bound against the row, and the body then
reads `mean(returns) / std(returns, ddof=1) * sqrt(252)`. A claim about
it is decided as mathematics: over a vector, as sums over a sequence
of symbolic length (see [the derive route](derive-route.md#vectors-through-definition-rows));
over a matrix, in the matrix algebra.

<!-- example: rt-proofs run requires=pandas -->
```python
import numpy as np
import pandas as pd


def sharpe(returns: pd.Series):
    return returns.mean() / returns.std(ddof=1) * np.sqrt(252)


def volatility(returns: pd.Series):
    return returns.std() * np.sqrt(252)


def transpose(A: np.ndarray):
    return A.T
```

A Sharpe ratio is unchanged by leverage (scaling every return by the
same `c > 0`), and is not unchanged by adding a constant to every
return:

<!-- example: rt-proofs verdicts fn=sharpe requires=pandas -->
```
for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, let c be [0.1, 10], assuming std(returns, ddof=1) > 0, f(s(returns, c)) ~= f(returns)   # proven
for returns in [-0.1, 0.1]^n, let s = mathema.f.shift_seq, let c be [0.1, 10], assuming std(returns, ddof=1) > 0, f(s(returns, c)) ~= f(returns)   # falsified
for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, let c be [0.1, 10], f(s(returns, c)) ~= f(returns)   # falsified
```

The third claim drops the premise, and is false: where the returns do
not vary (every return equal, or a single return) the standard
deviation is 0 or undefined, `sharpe` returns NaN, and the claim has no
value there. The derive route finds the region from the rewritten
body, executes `sharpe` at a point of it (`returns=[0.0]`), and
falsifies the claim with that witness. The premise names the returns
the ratio is about, and it is read exactly: the standard deviation of
equal returns is 0 over the reals, so a constant vector is outside the
claim, on the proof and on the computation check alike, however float
arithmetic rounds it.

Volatility is unchanged by a shift and scales with leverage; being
unchanged by leverage is the false sibling:

<!-- example: rt-proofs verdicts fn=volatility requires=pandas -->
```
for returns in [-0.1, 0.1]^n, let s = mathema.f.shift_seq, let c be [0.1, 10], assuming dim(returns) >= 2, f(s(returns, c)) ~= f(returns)   # proven
for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, let c be [0.1, 10], assuming dim(returns) >= 2, f(s(returns, c)) ~= c * f(returns)   # proven
for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, let c be [0.1, 10], assuming dim(returns) >= 2, f(s(returns, c)) ~= f(returns)   # falsified
```

<!-- example: rt-proofs verdicts fn=transpose requires=pandas -->
```
for A in R^(n,n), f(f(A)) == A   # proven
for A in R^(n,n), f(A) == A   # falsified
```

The record names each row a proof read through, with where it came
from and its standing here:

<!-- example: rt-proofs run requires=pandas -->
```python
import mathema

record = mathema.check(sharpe, claims=[
    "for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, "
    "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
    "f(s(returns, c)) ~= f(returns)"])
print(record)
proof = record.probes[0]
print(proof.sketch)
for row in proof.meta["mathema.definitions"]:
    print(row["key"], row["row"], row["status"], row["source"])
```

<!-- example: rt-proofs output -->
```text
mathema.Record(sharpe) · source, no side effects · form ef276c12c167
  proven  f_s_returns_c_approx_f_returns: assuming std(returns, ddof=1) > 0, let s = mathema.f.scale_seq, let c be [0.1, 10.0], for returns in ([-0.1, 0.1] | {missing})^n : float, f(s(returns, c)) ~= f(returns)
           ∀ returns over [-0.1, 0.1] with nothing missing, returns of every length from 2; missing for returns (pandas.Series) means nan, null or NA
  holds   f_s_returns_c_approx_f_returns[float, pandas.Series]: assuming std(returns, ddof=1) > 0, let s = mathema.f.scale_seq, let c be [0.1, 10.0], for returns in ([-0.1, 0.1] | {missing})^n : float, f(s(returns, c)) ~= f(returns) (43 draws, sizes (2, 1) to (8, 1), 229 entries in all)
           the float64 computation of f_s_returns_c_approx_f_returns ran at 43 points: nan, null, NA, every corner and 37 interior points; f drops a missing slot when values remain (returns = [nan, -0.087, -0.1], c = 0.1) and gives a hole back when every slot is missing (returns = [nan, -0.087, -0.1], c = 0.1); at returns = [null, -0.087, -0.1] f raised TypeError, which no claim accounts for: state `missing(f, returns, null) raises(TypeError)`, or make f return a value there; at returns = [NA, -0.087, -0.1] f returned HoledArray([        nan, -0.0087012 ,...: the hole became a value; write `missing(f, returns, NA) drops` to accept this, or guard the input
  FALSIFY missing(f, returns)   [f treats a missing returns more than one way: propagates at returns = [nan, -0.087, -0.1], c = 0.1: f returned [nan, -0.0087, -0.01]; drops at returns = [nan, -0.087, -0.1], c = 0.1: f returned -162; raises at returns = [null, -0.087, -0.1], c = 0.1: f raised TypeError]
           state what f should do for each case with a premise, e.g. `assuming count(returns) >= 1, missing(f, returns) drops`, or make f treat it one way
through the pandas.Series.mean definition and pandas.Series.std definition rows, lowered to a sum over returns at a symbolic length; holds for every length
pandas.Series.mean definition bundled mathema/compendium/pandas/series.claims.yaml
pandas.Series.std definition bundled mathema/compendium/pandas/series.claims.yaml
```

A proof through definition rows is `proven` like any other, and its
`[float, pandas.Series]` companion runs the real code in float64. A call
no row covers is named in the derive note (`pandas.Series.ewm has no
definition row`), and such a claim is adjudicated by sampling.

### Running extrema, least and greatest elements, and columns

A running maximum (`prices.cummax()`), a least element (`.min()`) and
a greatest (`.max()`) have no closed form as a sum, so the derive
route knows each through its bounds: `cummax(a)[i]` is at least
`a[i]` and is one of `a[0..i]`, so for positive prices `0 <
a[i] / cummax(a)[i] <= 1`; `min(v)` is at most every element of `v`
and at most its mean, `max(v)` at least them. The maximum drawdown of
a price path, the largest fall from its running peak as a fraction of
that peak, lies between -1 and 0:

<!-- example: rt-drawdown run requires=pandas -->
```python
import pandas as pd


def max_drawdown(prices: pd.Series) -> float:
    return float((prices / prices.cummax() - 1.0).min())


def weighted_return(df: pd.DataFrame) -> float:
    return float((df.w * df.r).sum())
```

<!-- example: rt-drawdown verdicts fn=max_drawdown requires=pandas -->
```
for prices in [1, 100]^n, f(prices) <= 0   # proven
for prices in [1, 100]^n, f(prices) >= -1   # proven
for prices in [1, 100]^n, f(prices) < 0   # falsified
for prices in [1, 100]^n, f(prices) >= -0.5   # falsified
```

A drawdown is not always negative: a path that never falls has
drawdown 0, and sampling finds one. The proof names the bound it used:

<!-- example: rt-drawdown run requires=pandas -->
```python
import mathema

record = mathema.check(max_drawdown, claims=[
    "for prices in [1, 100]^n, f(prices) <= 0"])
proof = record.probes[0]
print(proof.verdict, proof.route)
print(proof.condition)
print(proof.sketch)
```

<!-- example: rt-drawdown output -->
```text
proven derive
∀ prices over [1.0, 100.0] with nothing missing, prices of every length
through the pandas.Series.cummax definition and pandas.Series.min definition rows, lowered to a sum over prices at a symbolic length; holds for every length (every element of prices / cummax(prices) - 1.0 is <= 0 (0 < prices[i] / cummax(prices)[i] <= 1), so min(prices / cummax(prices) - 1.0) is too)
```

A DataFrame's columns are vectors on the derive route too, read by
attribute or by item, and a Series method called on an expression of
them reads through the Series rows: a weighted return is the dot
product of its weight and return columns.

<!-- example: rt-drawdown verdicts fn=weighted_return requires=pandas -->
```
for df in [0, 1]^n, f(df) ~= dot(df.w, df.r)   # proven
for df in [0, 1]^n, f(df) ~= dot(df["r"], df["w"])   # proven
for df in [0, 1]^n, f(df) ~= dot(df.w, df.w)   # falsified
```

## Adding a runtime type

A package adds a runtime type by registering an adapter under the
entry-point group `mathema.runtime_types`:

```toml
[project.entry-points."mathema.runtime_types"]
torch = "my_package.adapters:TorchTensorAdapter"
```

An adapter (`mathema.runtime_types.RuntimeTypeAdapter`) states its
`name` (`"torch.Tensor"`), the `kinds` it carries (`vec`, `mat`,
`table`) and the modules it `requires`, and provides three methods:
`detect(annotation)`, which reads one annotation (a live type, or its
source text as a string) and returns a `Detection` or None;
`realise(abstract, options)`, which builds the object passed to the
function from an `AbstractVec`, `AbstractMat` or `AbstractTable`; and
`observe(obj)`, which turns a returned object into an abstract value or
a plain number, or returns `NotMine`. A built-in adapter wins a name
clash, and an adapter that fails to load is skipped with a warning.
