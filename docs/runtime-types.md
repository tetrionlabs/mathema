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

The derive route does not yet read a column or a Series method; such a
claim is adjudicated by sampling.

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
