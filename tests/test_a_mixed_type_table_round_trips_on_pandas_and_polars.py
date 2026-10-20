# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A table's columns keep their types on the way to the function and
back.

A drawn table is named columns of numbers, integers, strings or
booleans, some with holes. pandas and polars each realise every column
with the type it was drawn as (a string column with a hole is still a
string column, a boolean column still boolean), and a returned table
is read back with the same names and types. The neutral operations in
`mathema.runtime_types` (a column by name, the row count, the column
names and their types) read any table an adapter observes, so core
never reads pandas or polars itself.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("pandas")
pytest.importorskip("polars")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import (AbstractTable, AbstractVec,  # noqa: E402
                                   Detection, column, column_names,
                                   column_types, observe, plain, realise,
                                   row_count)

_PANDAS = Detection("pandas.DataFrame", "table", "annotation: pandas.DataFrame")
_POLARS = Detection("polars.DataFrame", "table", "annotation: polars.DataFrame")

_DRAWN = {"x": [1.5, math.nan, -2.0],
          "i": [1, 2, 3],
          "k": ["u", None, "v"],
          "b": [True, False, True]}

_TYPES = {"x": "float", "i": "int", "k": "str", "b": "bool"}


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) \
            and math.isnan(a) and math.isnan(b):
        return True
    return a == b


@pytest.mark.parametrize("detection", [_PANDAS, _POLARS],
                         ids=["pandas", "polars"])
def test_a_drawn_mixed_table_round_trips(detection):
    frame = realise(_DRAWN, detection)
    assert type(frame).__module__.split(".")[0] == \
        detection.adapter.split(".")[0]
    assert row_count(frame) == 3
    assert column_names(frame) == ("x", "i", "k", "b")
    assert column_types(frame) == _TYPES
    back = plain(observe(frame))
    for name, drawn in _DRAWN.items():
        got = back[name]
        assert len(got) == len(drawn)
        for g, d in zip(got, drawn):
            if d is None:
                assert g is None or (isinstance(g, float) and math.isnan(g))
            else:
                assert _same(g, d) and type(g) is type(d), (name, g, d)
    k = column(frame, "k")
    assert k.missing == frozenset({1})
    assert [v for i, v in enumerate(k.values) if i not in k.missing] == ["u", "v"]


def test_pandas_realises_each_column_as_its_type():
    frame = realise(_DRAWN, _PANDAS)
    assert frame["x"].dtype.kind == "f"
    assert frame["i"].dtype.kind == "i"
    assert frame["b"].dtype.kind == "b"
    assert frame["k"].tolist()[0] == "u"
    assert frame["k"].dtype == pd.Series(["s"]).dtype \
        or frame["k"].dtype == object


def test_polars_realises_each_column_as_its_type():
    frame = realise(_DRAWN, _POLARS)
    assert frame.schema == {"x": pl.Float64, "i": pl.Int64,
                            "k": pl.String, "b": pl.Boolean}
    assert frame["k"].to_list() == ["u", None, "v"]


@pytest.mark.parametrize("detection", [_PANDAS, _POLARS],
                         ids=["pandas", "polars"])
def test_a_column_of_holes_only_keeps_its_drawn_type(detection):
    drawn = AbstractTable({"k": AbstractVec((math.nan,), frozenset({0}),
                                            element="str")})
    frame = realise(drawn, detection)
    assert column_types(frame) == {"k": "str"}


@pytest.mark.parametrize("detection", [_PANDAS, _POLARS],
                         ids=["pandas", "polars"])
def test_a_polars_nan_hole_in_a_string_column_is_never_the_text_nan(detection):
    frame = realise({"k": ["u", math.nan]}, detection)
    assert column_types(frame) == {"k": "str"}
    assert column(frame, "k").missing == frozenset({1})


def test_a_missing_column_is_named_with_the_columns_there_are():
    with pytest.raises(KeyError, match="'z'.*x, i, k, b"):
        column(realise(_DRAWN, _PANDAS), "z")


def pandas_tagged(a: pd.DataFrame):
    out = a.copy()
    out["tag"] = a["k"].str.upper()
    out["n"] = a["i"] + a["b"].astype(int)
    return out


def polars_tagged(a: pl.DataFrame):
    return a.with_columns(tag=a["k"].str.to_uppercase(),
                          n=a["i"] + a["b"].cast(pl.Int64))


_TYPED = ('for a.k in {"u", "v"}^n \\ {missing}, a.b in {True, False}^n '
          '\\ {missing}, a.i in [0, 10]^n subset Z, a.x in [0, 1]^n '
          '\\ {missing}, ')


@pytest.mark.parametrize("fn", [pandas_tagged, polars_tagged],
                         ids=["pandas", "polars"])
@pytest.mark.parametrize("text", ['f(a)["x"] == a.x',
                                  'f(a)["k"] == a.k',
                                  'f(a)["b"] == a.b',
                                  'f(a)["i"] == a.i',
                                  'f(a)["n"] == a.i + a.b'])
def test_a_typed_table_claim_holds_on_its_own_types(fn, text):
    (p,) = check_conjectures(fn, [claim(_TYPED + text)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


@pytest.mark.parametrize("fn", [pandas_tagged, polars_tagged],
                         ids=["pandas", "polars"])
def test_a_false_typed_table_claim_is_falsified_with_a_witness(fn):
    (p,) = check_conjectures(fn, [claim(_TYPED + 'f(a)["n"] == a.i')])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample, p.note


def pandas_letters(s: pd.Series):
    return float(s.str.len().sum())


def polars_letters(s: pl.Series):
    return float(s.str.len_chars().sum())


@pytest.mark.parametrize("fn", [pandas_letters, polars_letters],
                         ids=["pandas", "polars"])
def test_a_vector_of_strings_is_realised_as_a_string_series(fn):
    (p,) = check_conjectures(
        fn, [claim('for s in {"uu", "v"}^n \\ {missing}, f(s) >= dim(s)')])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)
