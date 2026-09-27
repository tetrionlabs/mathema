# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The runtime type adapter protocol and the built-in adapters: `list`
(and `tuple`), `numpy.ndarray`, `pandas.Series`, `pandas.DataFrame`,
`polars.Series` and `polars.DataFrame`.

An adapter never imports its library until it is asked to realise or
observe a value, and the registry treats an adapter whose library is
not installed as absent, so numpy, pandas and polars stay optional.
"""
from __future__ import annotations

import math
import typing
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ._abstract import AbstractMat, AbstractTable, AbstractVec, NotMine

#: the kinds of abstract value an adapter can carry
KINDS = frozenset({"vec", "mat", "table"})


@dataclass(frozen=True)
class Detection:
    """An adapter's claim on a parameter: the adapter's name, the kind
    of abstract value the parameter carries (`vec`, `mat` or `table`),
    and the evidence, stated as the record states it
    (`"annotation: pandas.Series"`)."""
    adapter: str
    kind: str
    evidence: str


@runtime_checkable
class RuntimeTypeAdapter(Protocol):
    """What a runtime type adapter provides.

    `name` is the runtime type's dotted name (`"pandas.Series"`),
    `kinds` the abstract kinds it carries, `requires` the modules that
    must be importable for it to be used. `detect(annotation)` reads
    one annotation, a live type or its source text, and returns a
    `Detection` or None. `realise(abstract, options)` builds the object
    passed to the function from an abstract value. `observe(obj)`
    turns a returned object into an abstract value or a plain number,
    or returns `NotMine` for an object that is not its runtime type.
    """
    name: str
    kinds: frozenset
    requires: tuple

    def detect(self, annotation) -> "Detection | None": ...

    def realise(self, abstract, options: dict) -> Any: ...

    def observe(self, obj) -> Any: ...


def _annotation_text(annotation) -> "str | None":
    """The source text of a string annotation, or None for a live
    object."""
    return annotation.strip() if isinstance(annotation, str) else None


def _root_module(obj) -> str:
    return (getattr(obj, "__module__", "") or "").split(".", 1)[0]


def _missing_to(values, missing, fill) -> list:
    return [fill if k in missing else v for k, v in enumerate(values)]


def _spelling(options: dict, spellings: dict, default: str):
    """The value a missing position is realised as: the spelling
    `options["missing"]` names among the runtime type's own
    `spellings`, else its default one. Missing is one concept; each
    spelling is a way a library can hold it."""
    choice = str((options or {}).get("missing", default)).lower()
    if choice not in spellings:
        raise ValueError(f"missing spelled {choice!r} is not one of "
                         f"{sorted(spellings)}")
    return spellings[choice]()


class ListAdapter:
    """`list` and `tuple`: the runtime type every sequence was sampled
    as before runtime types existed. A matrix is a list of row lists,
    up to `SIZE_CAP` per axis, where pure-Python operations on it stay
    fast."""
    name = "list"
    kinds = frozenset({"vec", "mat", "table"})
    requires: tuple = ()
    #: the largest side a matrix is sampled with as nested lists
    SIZE_CAP = 64

    def detect(self, annotation):
        text = _annotation_text(annotation)
        if text is not None:
            head = text.split("[", 1)[0].strip().lower()
            if head in ("list", "tuple", "typing.list", "typing.tuple"):
                return Detection(self.name, _list_kind(text),
                                 f"annotation text: {text}")
            return None
        origin = typing.get_origin(annotation) or annotation
        if origin in (list, tuple):
            return Detection(self.name, _list_kind(repr(annotation)),
                             f"annotation: {_type_name(annotation)}")
        return None

    #: how a list can hold a missing position
    MISSING = {"none": lambda: None, "nan": lambda: math.nan}

    def realise(self, abstract, options):
        if isinstance(abstract, AbstractMat):
            return [list(r) for r in abstract.rows]
        if isinstance(abstract, AbstractTable):
            return {name: self.realise(col, options)
                    for name, col in abstract.columns.items()}
        return _missing_to(abstract.values, abstract.missing,
                           _spelling(options, self.MISSING, "none"))

    def observe(self, obj):
        from ._abstract import abstract_of
        if isinstance(obj, (list, tuple)):
            found = abstract_of(obj)
            return found if found is not None else NotMine
        return NotMine


def _list_kind(text: str) -> str:
    inner = text.split("[", 1)[1] if "[" in text else ""
    return "mat" if inner.lower().startswith(("list", "tuple")) else "vec"


def _alias_value(annotation):
    """What a type alias stands for: `npt.NDArray[np.float64]` is a
    subscripted `type` statement alias whose value is
    `np.ndarray[...]`; any other annotation is itself."""
    for _ in range(4):
        origin = typing.get_origin(annotation)
        value = getattr(origin, "__value__", None) \
            or getattr(annotation, "__value__", None)
        if value is None:
            return annotation
        annotation = value
    return annotation


def _type_name(annotation) -> str:
    if isinstance(annotation, type):
        module = annotation.__module__
        return (annotation.__qualname__ if module == "builtins"
                else f"{module}.{annotation.__qualname__}")
    return repr(annotation).replace("typing.", "")


class NumpyAdapter:
    """`numpy.ndarray`: a vector as a 1-D array, a matrix as a 2-D one;
    a missing position is NaN."""
    name = "numpy.ndarray"
    kinds = frozenset({"vec", "mat"})
    requires = ("numpy",)

    def detect(self, annotation):
        text = _annotation_text(annotation)
        if text is not None:
            head = text.split("[", 1)[0].strip()
            if head in ("numpy.ndarray", "numpy.typing.NDArray",
                        "ndarray", "NDArray"):
                return Detection(self.name, "vec",
                                 f"annotation text: {text}")
            return None
        annotation = _alias_value(annotation)
        if _root_module(annotation) != "numpy" and _root_module(
                typing.get_origin(annotation)) != "numpy":
            return None
        import numpy as np
        if annotation is np.ndarray or typing.get_origin(annotation) \
                is np.ndarray:
            return Detection(self.name, "vec", "annotation: numpy.ndarray")
        return None

    def realise(self, abstract, options):
        import numpy as np
        if isinstance(abstract, AbstractMat):
            return np.array([list(r) for r in abstract.rows])
        if isinstance(abstract, AbstractTable):
            raise TypeError("numpy.ndarray does not carry a table")
        return np.array(_missing_to(abstract.values, abstract.missing,
                                    _spelling(options, {"nan": lambda:
                                                        math.nan}, "nan")))

    def observe(self, obj):
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
        if not isinstance(obj, np.ndarray):
            return NotMine
        if obj.ndim == 0:
            return obj.item()
        if obj.ndim == 1:
            values = tuple(v.item() if hasattr(v, "item") else v
                           for v in obj)
            missing = frozenset(k for k, v in enumerate(values)
                                if isinstance(v, float) and v != v)
            return AbstractVec(values, missing)
        if obj.ndim == 2:
            return AbstractMat(tuple(tuple(v.item() for v in row)
                                     for row in obj))
        return NotMine


def _default_index(n: int, options: dict):
    """A pandas business-day index of `n` dates from `options["start"]`
    (default 2020-01-01), the index a realised Series or DataFrame
    carries."""
    import pandas as pd
    return pd.bdate_range(options.get("start", "2020-01-01"), periods=n)


class PandasSeriesAdapter:
    """`pandas.Series`: a vector with a business-day index starting on
    2020-01-01; a missing position is NaN."""
    name = "pandas.Series"
    kinds = frozenset({"vec"})
    requires = ("pandas",)

    def detect(self, annotation):
        return _pandas_detect(self, annotation, "Series", "vec")

    def realise(self, abstract, options):
        if not isinstance(abstract, AbstractVec):
            raise TypeError("pandas.Series carries a vector")
        return _pandas_column(abstract, options,
                              _default_index(len(abstract), options))

    def observe(self, obj):
        import pandas as pd
        if isinstance(obj, pd.Series):
            return _vec_from_pandas(obj)
        if obj is pd.NA:
            return math.nan
        return NotMine


class PandasDataFrameAdapter:
    """`pandas.DataFrame`: a table, one float column per abstract
    column, with the Series adapter's index."""
    name = "pandas.DataFrame"
    kinds = frozenset({"table"})
    requires = ("pandas",)

    def detect(self, annotation):
        return _pandas_detect(self, annotation, "DataFrame", "table")

    def realise(self, abstract, options):
        import pandas as pd
        if not isinstance(abstract, AbstractTable):
            raise TypeError("pandas.DataFrame carries a table")
        n = len(next(iter(abstract.columns.values()))) \
            if abstract.columns else 0
        index = _default_index(n, options)
        return pd.DataFrame(
            {name: _pandas_column(col, options, index)
             for name, col in abstract.columns.items()},
            index=index)

    def observe(self, obj):
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return AbstractTable({str(c): _vec_from_pandas(obj[c])
                                  for c in obj.columns})
        return NotMine


def _pandas_column(abstract: AbstractVec, options: dict, index):
    """A vector as a pandas Series on `index`, a missing position held
    as `nan` (a float Series, the default), `None` (an object Series)
    or `pd.NA` (a nullable `Float64` Series)."""
    import pandas as pd
    spellings = {"nan": lambda: math.nan, "none": lambda: None,
                 "na": lambda: pd.NA}
    fill = _spelling(options, spellings, "nan")
    values = _missing_to(abstract.values, abstract.missing, fill)
    if fill is None:
        return pd.Series(values, index=index, dtype=object)
    if fill is pd.NA:
        return pd.Series(values, index=index, dtype="Float64")
    return pd.Series(values, index=index)


def _vec_from_pandas(series) -> AbstractVec:
    mask = series.isna().tolist()
    values = tuple(math.nan if m else (v.item() if hasattr(v, "item")
                                       else v)
                   for v, m in zip(series.tolist(), mask))
    return AbstractVec(values, frozenset(k for k, m in enumerate(mask)
                                         if m))


def _pandas_detect(adapter, annotation, cls_name: str, kind: str):
    text = _annotation_text(annotation)
    if text is not None:
        head = text.split("[", 1)[0].strip()
        if head in (f"pandas.{cls_name}", f"pandas.core.series.{cls_name}",
                    f"pandas.core.frame.{cls_name}"):
            return Detection(adapter.name, kind, f"annotation text: {text}")
        return None
    origin = typing.get_origin(annotation) or annotation
    if _root_module(origin) != "pandas" or not isinstance(origin, type):
        return None
    import pandas as pd
    if issubclass(origin, getattr(pd, cls_name)):
        return Detection(adapter.name, kind, f"annotation: {adapter.name}")
    return None


class PolarsSeriesAdapter:
    """`polars.Series`: a vector; a missing position is null."""
    name = "polars.Series"
    kinds = frozenset({"vec"})
    requires = ("polars",)

    def detect(self, annotation):
        return _polars_detect(self, annotation, "Series", "vec")

    def realise(self, abstract, options):
        import polars as pl
        if not isinstance(abstract, AbstractVec):
            raise TypeError("polars.Series carries a vector")
        return pl.Series(options.get("name", ""),
                         _polars_values(abstract, options), strict=False)

    def observe(self, obj):
        import polars as pl
        if isinstance(obj, pl.Series):
            return _vec_from_polars(obj)
        return NotMine


class PolarsDataFrameAdapter:
    """`polars.DataFrame`: a table, one column per abstract column;
    a missing position is null."""
    name = "polars.DataFrame"
    kinds = frozenset({"table"})
    requires = ("polars",)

    def detect(self, annotation):
        return _polars_detect(self, annotation, "DataFrame", "table")

    def realise(self, abstract, options):
        import polars as pl
        if not isinstance(abstract, AbstractTable):
            raise TypeError("polars.DataFrame carries a table")
        return pl.DataFrame({name: pl.Series(name,
                                             _polars_values(col, options),
                                             strict=False)
                             for name, col in abstract.columns.items()})

    def observe(self, obj):
        import polars as pl
        if isinstance(obj, pl.DataFrame):
            return AbstractTable({c: _vec_from_polars(obj[c])
                                  for c in obj.columns})
        return NotMine


def _polars_values(abstract: AbstractVec, options: "dict | None" = None
                   ) -> list:
    """A vector's values for a polars Series, a missing position held
    as `null` (the default) or `NaN`, which polars treats as an
    ordinary float and mathema reads as missing all the same."""
    fill = _spelling(options or {}, {"null": lambda: None,
                                     "nan": lambda: math.nan}, "null")
    values = _missing_to(abstract.values, abstract.missing, fill)
    if any(isinstance(v, float) for v in values):
        # one dtype for the column: an int among floats is a float
        values = [float(v) if isinstance(v, int) else v for v in values]
    return values


def _vec_from_polars(series) -> AbstractVec:
    raw = series.to_list()
    missing = frozenset(k for k, v in enumerate(raw)
                        if v is None or (isinstance(v, float) and v != v))
    values = tuple(math.nan if v is None else v for v in raw)
    return AbstractVec(values, missing)


def _polars_detect(adapter, annotation, cls_name: str, kind: str):
    text = _annotation_text(annotation)
    if text is not None:
        head = text.split("[", 1)[0].strip()
        if head in (f"polars.{cls_name}",
                    f"polars.series.series.{cls_name}",
                    f"polars.dataframe.frame.{cls_name}"):
            return Detection(adapter.name, kind, f"annotation text: {text}")
        return None
    if _root_module(annotation) != "polars" or not isinstance(annotation,
                                                              type):
        return None
    import polars as pl
    if issubclass(annotation, getattr(pl, cls_name)):
        return Detection(adapter.name, kind, f"annotation: {adapter.name}")
    return None


#: the built-in adapters, most specific first; `list` is the default a
#: parameter no adapter claims is sampled as
BUILTIN_ADAPTERS: tuple = (
    PandasSeriesAdapter(), PandasDataFrameAdapter(),
    PolarsSeriesAdapter(), PolarsDataFrameAdapter(),
    NumpyAdapter(), ListAdapter(),
)
