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
for xs in [-1e6, 1e6]^n, min(xs) <= f(xs) <= max(xs)   # holds
```

<!-- example: rt-mean verdicts fn=series_mean route=probe requires=pandas -->
```
for xs in [-1e6, 1e6]^n, min(xs) <= f(xs) <= max(xs)   # holds
```

Sampled as a list, as it was before runtime types, `mean_of` raises
`AttributeError` (a list has no `.mean()`) and the claim is falsified;
sampled as the array its signature names, it holds.
Over all of `R^n` the mean overflows: at two of the largest doubles the
float64 sum is `inf`, so the computation is falsified there while the
mathematics is still proven (see [the computation
line](evidence-ladder.md#a-proof-is-the-mathematics-float-is-the-code)).

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
   module's own aliases and the usual `np`, `pd` and `pl` (and any
   alias a registered adapter states);
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
type, how it is drawn depends on the use. Each runtime type adapter
declares the uses its type supports and a list does not: attributes
(`.iloc`, `.columns`, `.shape`), methods (`.mean()`, `.dropna()`),
methods called with a column name (`df.groupby("k")`), and `@`. When
every use the body makes of the parameter (apart from what every Python
object has, such as `.__class__`) is one the types of exactly one
library the module imports support, the parameter is drawn as that
library's type, and the record says so ("the body uses it as a pandas
DataFrame"). A library's Series and DataFrame both supporting the uses,
the body's usage decides: a column read or a keyed method makes it the
DataFrame, a vector use the Series. A single use the type does not
declare (`x.weight` beside `x.sum()`) keeps the parameter a list, and
the hint names that use; uses the types of two imported libraries both
support also keep it a list, and the hint names each type:

<!-- example: rt-promote run inline requires=polars -->
```python
import numpy as np
import pandas as pd
import mathema


def first_row_share(df):
    totals = df.groupby("k")["v"].sum()
    first = df.iloc[0]
    return first["v"] / totals[first["k"]]


def spread(xs):
    return xs.max() - xs.min()


def sum_and_weight(x):
    return x.sum() * x.weight


mathema.analyze(first_row_share).runtime_types["df"][0].evidence  # 'the body uses it as a pandas DataFrame'
mathema.analyze(spread).runtime_hints["xs"]["text"]  # 'xs is used as a vector; this module imports pandas and numpy, whose types both support that use: to sample it as one, annotate: xs: pd.Series or xs: np.ndarray'
mathema.analyze(sum_and_weight).runtime_hints["x"]["text"]  # 'x is used as a vector; this module imports pandas, but pandas.Series does not support x.weight: annotate x with the type it has'
```

In a module that imports pandas alone, `spread`'s `xs` is drawn as a
pandas Series; with numpy alone, as an ndarray. When the body's uses
are ones a list also serves (indexing, `np.mean(x)`), the hint names
the runtime type of the library the module imports:

<!-- illustration -->
```text
returns is used as a vector; this module imports pandas: to sample it as one, annotate: returns: pd.Series
```

The hint rides the note of every claim on the function when a list
cannot serve the use (a list has no `.mean()`), and `mathema check`
prints it under the function. When the function raises a
`TypeError`, `ValueError` or `AttributeError` on the list, the claim
is `skipped:misspecified` with the same hint, never `falsified`: the
list was the wrong object to hand the function. With a runtime type
declared, a raise falsifies as always.

A parameter annotated with any other type (`dict`, `Mapping[str,
int]`, `list[float]`, a class of its own) has no hint: its annotation
decides how it is drawn, whatever attributes the body reads off it.
`order: dict` is drawn as a dict even when the body calls
`order.values()` in a module that imports numpy. Only an annotation of
`Any` or `object` leaves the reading to the body.

A class mathema has no way to draw (one of your own that is not a
dataclass, with no runtime type adapter and no language adaptor for it)
is never drawn as something else: a claim that would draw it is
`skipped` with no evaluable inputs, and the note names the class and
the two ways to supply one, a runtime type adapter or a binding in the
claim (`for b in L[...]`). A claim that passes an instance itself
(`f(Box((2, 3))) == 6`) draws nothing for it and is checked as usual.

## The built-in runtime types

| runtime type | carries | a missing position | notes |
|---|---|---|---|
| `list` (and `tuple`) | vector, matrix (nested lists), table (dict of lists) | `None`, NaN | a matrix is drawn as nested lists up to 64 per axis |
| `numpy.ndarray` | vector (1-D), matrix (2-D) | NaN | |
| `pandas.Series` | vector | NaN, `None`, `pd.NA` | a business-day index from 2020-01-01 |
| `pandas.DataFrame` | table | NaN, `None`, `pd.NA` | the Series index; each column in the dtype of its type ([tables](#tables)) |
| `polars.Series` | vector | null, NaN | |
| `polars.DataFrame` | table | null, NaN | each column in the dtype of its type; a hole in a string or boolean column is null |

A missing position is a hole, one concept in mathema whatever a library
calls it: every spelling in the table reads back as `missing` when a
function returns it, a polars NaN included (polars itself treats NaN as
an ordinary float), and an adapter can realise a hole in each of its
spellings (the first one listed is the one it uses by default). The
container itself set to `None` is `absent`, the other kind. What a
function does with each is its policy row; see [missing
values](missing-values.md).

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
for returns in [-1e6, 1e6]^n, c in [-2, 2], f(returns, c) == c * returns   # holds
for returns in [-1e6, 1e6]^n, c in [-2, 2], norm(f(returns, c)) ~= abs(c) * norm(returns)   # holds
for returns in [-1e6, 1e6]^n, c in [-2, 2], mean(f(returns, c)) ~= c * mean(returns)   # holds
for returns in [-1e6, 1e6]^n, c in [-2, 2], mean(f(returns, c)) ~= mean(returns) + c   # falsified
```

<!-- example: rt-series verdicts fn=scale_polars requires=polars -->
```
for returns in [-1e6, 1e6]^n, c in [-2, 2], f(returns, c) == c * returns   # holds
for returns in [-1e6, 1e6]^n, c in [-2, 2], dot(f(returns, c), returns) ~= c * norm(returns)**2   # holds
```

A table parameter (a `pandas.DataFrame` or `polars.DataFrame`) is drawn
with one column per name the claim or the body reads, or the claim
binds ([tables](#tables)), and a claim reads a column as a vector, by
attribute or by item: `df.returns`, `df["returns"]`. A returned
DataFrame compares with another column by column, and its own columns
read the same way (`f(df)["a"]`); the arithmetic of a whole table
(`f(df) - 1`) is not claim syntax yet.

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
for df in [-1e6, 1e6]^n, c in [-2, 2], f(df, c) == c * df.returns   # holds
for df in [-1e6, 1e6]^n, c in [-2, 2], f(df, c) == c * df["returns"]   # proven
for df in [-1e6, 1e6]^n, c in [-2, 2], f(df, c) == df.returns + c   # falsified
```

<!-- example: rt-frame verdicts fn=shifted requires=pandas -->
```
f(df)["a"] == df["a"] + 1   # holds
f(df) == df   # falsified
```

The derive route reads a Series or array method through its
definition row (the section after next), and a column of a DataFrame as
a vector of its own, whose methods read through the Series rows.

## Tables

A table is named columns of one length, its row count `n`, which it
shares with every other parameter whose domain names `n`, as vectors
do: `for df in [0, 1]^n, w in [0, 1]^n` draws `w` as long as `df` has
rows. Its columns are the ones the claim or the body reads (`df.qty`,
`df["qty"]`) and the ones the claim binds, and a column's binding says
what it holds:

| binding | the column holds |
|---|---|
| `df.fee in [0, 10]^n` | numbers |
| `df.qty in [0, 100]^n subset Z` | integers |
| `df.side in {"buy", "sell"}^n` | strings |
| `df.open in {True, False}^n` | booleans |

A column with no binding of its own is drawn from the table's domain
(`for df in [0, 1]^n`), or from the reals. Every column holds the holes
the table's type admits; `\ {missing}` on a column's binding excludes
them from that column alone, and `\ {nan}` excludes one member. pandas
receives each column in the dtype pandas holds such a column in: its
string dtype, `bool`, `int64` or `float64`, a string or boolean column
with a hole spelled `None` as `object`, and a hole spelled `NA` in the
nullable `string`, `boolean` or `Float64`; a string or boolean column
with no value at all (holes only, or no rows) takes a dtype that states
its type, pandas' string dtype on pandas 3, else the nullable `string`
or `boolean`. polars receives `String`,
`Boolean`, `Int64` or `Float64`, a hole in a string or boolean column
as null. A table the function returns is read back with the same names
and types, and a string or boolean column compares element by element
like any other.

<!-- example: rt-table run requires=polars -->
```python
import pandas as pd
import polars as pl


def totals(df: pd.DataFrame):
    return df.sum()


def totals_polars(df: pl.DataFrame):
    return df.sum()


def signed_qty(df: pd.DataFrame):
    return df.qty.where(df.side == "buy", -df.qty)
```

A buy keeps its quantity and a sell negates it, so the size of each
signed quantity is the quantity, and the signed quantity is not:

<!-- example: rt-table verdicts fn=signed_qty requires=pandas -->
```
for df.side in {"buy", "sell"}^n \ {missing}, df.qty in [0, 100]^n subset Z \ {missing}, abs(f(df)) == df.qty   # holds
for df.side in {"buy", "sell"}^n \ {missing}, df.qty in [0, 100]^n subset Z \ {missing}, f(df) == df.qty   # falsified
```

A reduction answers one value per column, and a claim reads the value
for a column by its name. pandas answers `df.sum()` with a Series
labelled by the column names, read back with its labels, so
`f(df)["qty"]` is the sum of column `qty` whatever the table's other
columns and their order; polars answers with a one-row DataFrame, whose
column `qty` holds the sum. A position reads a position: the columns
here are drawn `qty` then `fee`, so `f(df)[0]` is the sum of `qty` and
`f(df)[1]` the sum of `fee`.

<!-- example: rt-table verdicts fn=totals requires=pandas -->
```
for df.qty in [0, 100]^n subset Z \ {missing}, df.fee in [0, 10]^n \ {missing}, f(df)["qty"] ~= sum(df.qty)   # holds
for df.qty in [0, 100]^n subset Z \ {missing}, df.fee in [0, 10]^n \ {missing}, f(df)["fee"] ~= sum(df.fee)   # holds
for df.qty in [0, 100]^n subset Z \ {missing}, df.fee in [0, 10]^n \ {missing}, f(df)[1] ~= sum(df.qty)   # falsified
```

<!-- example: rt-table verdicts fn=totals_polars requires=polars -->
```
for df.qty in [0, 100]^n subset Z \ {missing}, df.fee in [0, 10]^n \ {missing}, f(df)["qty"] ~= sum(df.qty)   # holds
for df.qty in [0, 100]^n subset Z \ {missing}, df.fee in [0, 10]^n \ {missing}, f(df)["fee"] ~= sum(df.qty)   # falsified
```

Code that reads a table without knowing its library uses the neutral
operations in `mathema.runtime_types`: `column_names(t)`,
`column_types(t)` (`{"qty": "int", "side": "str"}`, each one of
`float`, `int`, `bool` and `str`), `column(t, name)` and
`row_count(t)`. Each reads a pandas or polars DataFrame, a table a
registered adapter carries, or the plain dict of columns a draw is.

<!-- example: rt-table run inline requires=polars -->
```python
from mathema.runtime_types import column_names, column_types, row_count

frame = pl.DataFrame({"qty": [3, 5], "side": ["buy", None]})
column_names(frame)  # ('qty', 'side')
column_types(frame)  # {'qty': 'int', 'side': 'str'}
row_count(pd.DataFrame({"qty": [3, 5, 8]}))  # 3
```

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
mathema.Record(sharpe) · source, no side effects · form py:ef276c12c167
  f_s_returns_c_approx_f_returns  assuming std(returns, ddof=1) > 0, let s = mathema.f.scale_seq, let c be [0.1, 10.0], for returns in ([-0.1, 0.1] | {missing})^n : float, f(s(returns, c)) ~= f(returns)   falsified at f([nan, -0.009, 0.000606])
    proven     mathematics  assuming std(returns, ddof=1) > 0, let s = mathema.f.scale_seq, let c be [0.1, 10.0], for returns in ([-0.1, 0.1])^n ⊂ ℝ, f(s(returns, c)) ~= f(returns)
    holds      computation  assuming std(returns, ddof=1) > 0, let s = mathema.f.scale_seq, let c be [0.1, 10.0], for returns in ([-0.1, 0.1])^n : float, f(s(returns, c)) ~= f(returns)   210 entries across 36 draws, sizes (2, 1) to (8, 1)
    falsified  policy       f([..., missing, ...])   f([nan, -0.009, 0.000606]) returns -9.81
                            no missing policy stated
                            possible fixes:
                              (i) if dropping missing is intended, run: mathema accept sharpe missing[returns] --as discovery --corrected "missing(f, returns) drops"
                              (ii) exclude missing
                              (iii) handle missing at entry
taking pandas.Series.mean as mean(a) (axiom, bundled with mathema, pandas 2.2 to 3.x); taking pandas.Series.std as std(a, ddof=1) (axiom, bundled with mathema, pandas 2.2 to 3.x); through the pandas.Series.mean definition and pandas.Series.std definition rows, read as sums over returns at a symbolic length: the relation holds for every length
pandas.Series.mean definition bundled mathema/compendium/pandas/series.claims.yaml
pandas.Series.std definition bundled mathema/compendium/pandas/series.claims.yaml
```

A proof through definition rows is `proven` like any other: that is the
`mathematics` line. The `computation` line runs the real code in float64
and holds. The headline is still falsified, by a `policy` line: the claim
admits a missing day (`[-0.1, 0.1]^n` lets a float entry be `nan` or
`NA`), nothing in it says what `sharpe` should do with one, so mathema
assumed the missing value would reach the result, and it does not.
pandas' `mean` and `std` skip it, so `sharpe` drops the missing day and
returns a number. Stating that behaviour (`missing(f, returns) drops`)
or excluding missing values from the claim
(`[-0.1, 0.1]^n \ {missing}`) settles it. A call no row covers is named
in the derive note (`pandas.Series.ewm has no definition row`), and such
a claim is adjudicated by sampling.

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
drawdown 0, and sampling finds one. Checked with its empty-input line,
the claim itself is falsified at the empty series, whose drawdown is
`nan`; the proof over every non-empty series stays in its sketch, and
names the bound it used:

<!-- example: rt-drawdown run requires=pandas -->
```python
import textwrap

import mathema

record = mathema.check(max_drawdown, claims=[
    "for prices in [1, 100]^n, f(prices) <= 0"])
proof = record.probes[0]
print(proof.verdict, proof.route)
print(proof.condition)
print(textwrap.fill(proof.sketch, 78))
```

<!-- example: rt-drawdown output -->
```text
falsified probe
∀ prices over [1.0, 100.0] with nothing missing, prices of every length of at least one
taking pandas.Series.cummax as cummax(a) (axiom, bundled with mathema, pandas
2.2 to 3.x); taking pandas.Series.min as min(a) (axiom, bundled with mathema,
pandas 2.2 to 3.x); through the pandas.Series.cummax definition and
pandas.Series.min definition rows, read as sums over prices at a symbolic
length: the relation holds for every length of at least one (every element of
prices / cummax(prices) - 1.0 is <= 0 (0 < prices[i] / cummax(prices)[i] <=
1), so min(prices / cummax(prices) - 1.0) is too)
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
a plain number, or returns `NotMine`. An adapter carrying `table`
realises each column of the `AbstractTable` in the type
`element_type(column)` names and observes a table it is handed back as
an `AbstractTable` (see [extending
mathema](extending.md#runtime-type-adapters)). An adapter may also state
`ALIASES`, the module aliases its library is usually imported under
(`{"pd": "pandas"}` for the pandas adapters): an annotation's source
text is read through them, and the hint for an undeclared parameter
names the adapter's runtime type in a module that imports its library.
It may state `USES`, a `mathema.runtime_types.BodyUses`, the body uses
its type supports and a list does not, by which an unannotated
parameter is drawn as its type ([The hint](#the-hint);
[extending mathema](extending.md#runtime-type-adapters)).
A built-in adapter wins a name clash, and an adapter that fails to
load is skipped with a warning.
