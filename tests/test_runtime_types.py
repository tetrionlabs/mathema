# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Runtime types: a parameter annotated `np.ndarray`, `pd.Series`,
`pd.DataFrame`, `pl.Series` or `pl.DataFrame` (or marked
`Vec(..., runtime=...)`) is sampled as one.

The runtime type is read from the signature only, a marker first, then
the live annotation, then the annotation's text, and for code that
cannot be annotated a claims-file entry's `runtime_types:`; a
docstring never decides it. Each built-in adapter realises an abstract
vector, matrix or table with its missing positions in the library's
own spelling, and observes what a function returns back into one.
"""
from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pandas as pd
import polars as pl
import pytest

from mathema import runtime_types as rt
from mathema.runtime_types import (AbstractMat, AbstractTable, AbstractVec,
                                   NotMine)
from mathema.types import Mat, Vec


def _first(fn, declared=None):
    found = rt.detect_parameters(fn, declared)
    return {p: ds[0].adapter for p, ds in found.items()}


# --- detection precedence --------------------------------------------

def test_a_live_annotation_names_the_runtime_type():
    def f(a: np.ndarray, b: npt.NDArray[np.float64], c: pd.Series,
          d: pd.DataFrame, e: pl.Series, g: pl.DataFrame, h: list,
          k: float, m):
        return a
    assert _first(f) == {"a": "numpy.ndarray", "b": "numpy.ndarray",
                         "c": "pandas.Series", "d": "pandas.DataFrame",
                         "e": "polars.Series", "g": "polars.DataFrame",
                         "h": "list"}
    found = rt.detect_parameters(f)
    assert found["c"][0].evidence == "annotation: pandas.Series"
    assert found["c"][0].kind == "vec"
    assert found["d"][0].kind == "table"


def test_a_union_gives_one_detection_per_member_and_the_first_is_sampled():
    def f(r: pd.Series | pd.DataFrame):
        return r
    (found,) = rt.detect_parameters(f).values()
    assert [d.adapter for d in found] == ["pandas.Series", "pandas.DataFrame"]


def test_a_marker_outranks_the_annotation():
    def f(xs: Vec("n", runtime="pandas.Series"),
          a: Mat("n", "n", runtime="numpy.ndarray")):
        return xs
    found = rt.detect_parameters(f)
    assert found["xs"][0].adapter == "pandas.Series"
    assert found["xs"][0].evidence == "marker: pandas.Series"
    assert found["a"][0].kind == "mat"


def test_annotation_text_is_read_when_the_hints_do_not_resolve():
    def f(xs: "pd.Series", ys: "Undefined", zs: "np.ndarray"):  # noqa: F821
        return xs
    f.__globals__.pop("Undefined", None)
    found = _first(f)
    assert found == {"xs": "pandas.Series", "zs": "numpy.ndarray"}


def test_text_that_resolves_nowhere_is_read_through_the_usual_aliases():
    ns: dict = {}
    exec("def f(xs: 'pd.Series', ys: 'Missing'): return xs", ns)
    found = rt.detect_parameters(ns["f"])
    assert found["xs"][0].adapter == "pandas.Series"
    assert found["xs"][0].evidence == "annotation text: pandas.Series"


def test_the_claims_file_names_a_runtime_type_only_where_the_signature_is_silent():
    def f(xs, ys: np.ndarray):
        return xs
    found = rt.detect_parameters(
        f, {"xs": "pandas.Series", "ys": "polars.Series"})
    assert found["xs"][0].adapter == "pandas.Series"
    assert found["xs"][0].evidence == "claims file: pandas.Series"
    assert found["ys"][0].adapter == "numpy.ndarray"


def test_a_docstring_never_names_a_runtime_type():
    def f(returns):
        """returns (pd.Series): daily returns."""
        return returns
    assert rt.detect_parameters(f) == {}


# --- realise and observe, every built-in ------------------------------

_VEC = AbstractVec((1.5, math.nan, -2.0), frozenset({1}))
_MAT = AbstractMat(((1.0, 2.0), (3.0, 4.0)))
_TABLE = AbstractTable({"r": _VEC, "s": AbstractVec((0.0, 1.0, 2.0))})


def _same_vec(a, b):
    assert a.missing == b.missing
    for k, (x, y) in enumerate(zip(a.values, b.values)):
        if k not in a.missing:
            assert x == y


@pytest.mark.parametrize("name, native_missing", [
    ("list", lambda v: v is None),
    ("numpy.ndarray", lambda v: math.isnan(v)),
    ("pandas.Series", lambda v: math.isnan(v)),
    ("polars.Series", lambda v: v is None),
])
def test_a_vector_round_trips_with_its_missing_position(name, native_missing):
    found = rt.adapter(name)
    obj = found.realise(_VEC, {})
    as_list = obj.to_list() if name == "polars.Series" else list(obj)
    assert native_missing(as_list[1])
    _same_vec(found.observe(obj), _VEC)


def test_a_series_carries_a_business_day_index():
    s = rt.adapter("pandas.Series").realise(_VEC, {})
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index[0] == pd.Timestamp("2020-01-01")
    assert s.index.freqstr == "B"


@pytest.mark.parametrize("name", ["list", "numpy.ndarray"])
def test_a_matrix_round_trips(name):
    found = rt.adapter(name)
    assert found.observe(found.realise(_MAT, {})) == _MAT


@pytest.mark.parametrize("name", ["pandas.DataFrame", "polars.DataFrame"])
def test_a_table_round_trips_with_its_missing_position(name):
    found = rt.adapter(name)
    back = found.observe(found.realise(_TABLE, {}))
    assert list(back.columns) == ["r", "s"]
    _same_vec(back.columns["r"], _TABLE.columns["r"])
    _same_vec(back.columns["s"], _TABLE.columns["s"])


def test_observe_turns_numpy_scalars_and_zero_d_arrays_into_numbers():
    for value in (np.float64(2.5), np.float32(2.5), np.array(2.5)):
        seen = rt.observe(value)
        assert type(seen) is float and seen == 2.5
    assert type(rt.observe(np.int64(3))) is int


def test_observe_reads_arrays_and_series_as_vectors_and_frames_as_tables():
    assert isinstance(rt.observe(np.array([1.0, np.nan])), AbstractVec)
    assert rt.observe(np.array([1.0, np.nan])).missing == frozenset({1})
    assert isinstance(rt.observe(np.ones((2, 2))), AbstractMat)
    assert rt.observe(pd.Series([1.0, None])).missing == frozenset({1})
    assert isinstance(rt.observe(pd.DataFrame({"a": [1.0]})), AbstractTable)
    assert rt.observe(pl.Series([1.0, None])).missing == frozenset({1})
    assert isinstance(rt.observe(pl.DataFrame({"a": [1.0]})), AbstractTable)


def test_observe_leaves_what_no_adapter_recognises():
    assert rt.observe(3.0) == 3.0
    assert rt.observe("text") == "text"
    assert rt.adapter("numpy.ndarray").observe([1.0]) is NotMine


def test_a_plain_drawn_list_realises_as_the_runtime_type():
    d = rt.Detection("numpy.ndarray", "vec", "annotation: numpy.ndarray")
    out = rt.realise([1.0, None, 3.0], d)
    assert isinstance(out, np.ndarray) and math.isnan(out[1])
    assert rt.realise(4.0, d) == 4.0


# --- the registry ----------------------------------------------------

def test_an_entry_point_adapter_joins_and_a_built_in_wins_a_name_clash(
        monkeypatch):
    class Extra:
        name = "example.Vector"
        kinds = frozenset({"vec"})
        requires: tuple = ()

        def detect(self, annotation):
            return None

        def realise(self, abstract, options):
            return tuple(abstract.values)

        def observe(self, obj):
            return NotMine

    class Clash(Extra):
        name = "numpy.ndarray"

    class _EP:
        def __init__(self, obj, name):
            self.obj, self.name, self.value = obj, name, f"x:{name}"

        def load(self):
            return self.obj

    class _Broken(_EP):
        def load(self):
            raise ImportError("gone")

    monkeypatch.setattr(rt, "entry_points", lambda **_: [
        _EP(Extra, "extra"), _EP(Clash(), "clash"), _Broken(None, "bad")])
    rt._discovered.cache_clear()
    try:
        with pytest.warns(UserWarning):
            names = list(rt.adapters())
        assert "example.Vector" in names
        assert names[-1] == "list"
        assert not isinstance(rt.adapter("numpy.ndarray"), Clash)
    finally:
        rt._discovered.cache_clear()


# --- missing is one concept, whatever a library spells it --------------

@pytest.mark.parametrize("name, spelling, native", [
    ("list", "none", lambda v: v is None),
    ("list", "nan", lambda v: isinstance(v, float) and math.isnan(v)),
    ("numpy.ndarray", "nan", lambda v: math.isnan(v)),
    ("pandas.Series", "nan",
     lambda v: isinstance(v, float) and math.isnan(v)),
    ("pandas.Series", "none", lambda v: v is None),
    ("pandas.Series", "na", lambda v: v is pd.NA),
    ("polars.Series", "null", lambda v: v is None),
    ("polars.Series", "nan",
     lambda v: isinstance(v, float) and math.isnan(v)),
])
def test_every_spelling_of_missing_round_trips(name, spelling, native):
    found = rt.adapter(name)
    obj = found.realise(_VEC, {"missing": spelling})
    as_list = (obj.to_list() if name == "polars.Series"
               else obj.tolist() if name == "numpy.ndarray"
               else list(obj))
    assert native(as_list[1]), as_list
    _same_vec(found.observe(obj), _VEC)


@pytest.mark.parametrize("name, spelling", [
    ("pandas.DataFrame", "na"), ("pandas.DataFrame", "none"),
    ("polars.DataFrame", "nan"), ("polars.DataFrame", "null"),
])
def test_every_spelling_of_missing_round_trips_in_a_table(name, spelling):
    found = rt.adapter(name)
    back = found.observe(found.realise(_TABLE, {"missing": spelling}))
    _same_vec(back.columns["r"], _TABLE.columns["r"])


def test_a_polars_nan_is_observed_as_missing():
    seen = rt.observe(pl.Series("x", [1.0, float("nan"), None]))
    assert seen.missing == frozenset({1, 2}), seen


def test_a_pandas_na_is_observed_as_missing():
    seen = rt.observe(pd.Series([1.0, pd.NA, None], dtype="Float64"))
    assert seen.missing == frozenset({1, 2}), seen


def test_a_polars_series_with_no_value_is_still_a_float_column():
    from mathema.runtime_types import adapter
    from mathema.runtime_types._abstract import AbstractVec
    series = adapter("polars.Series").realise(
        AbstractVec((math.nan,), frozenset({0})), {})
    assert series.dtype == pl.Float64, series.dtype
    assert series.abs().to_list() == [None]
