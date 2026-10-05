# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim reads a pandas or polars Series, a DataFrame's column and a
numpy array alike.

The same claim text holds for a function over `np.ndarray`,
`pd.Series`, `pl.Series`, and for one reading a column of a
`pd.DataFrame` or `pl.DataFrame`: the claim draws a vector (or a table
of vectors), each call realises it as the function's runtime type, and
what comes back (a Series, a DataFrame, an array) is read back and
compared element by element. A column is addressed as `df.returns` or
`df["returns"]`, and a vector parameter works in every vector
construct: `norm`, `dot`, `mean`, `returns * c`, `returns + c`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from mathema.claims import check_conjectures, claim


def scale_numpy(returns: np.ndarray, c: float):
    return returns * c


def scale_pandas(returns: pd.Series, c: float):
    return returns * c


def scale_polars(returns: pl.Series, c: float):
    return returns * c


def scale_list(returns: list, c: float):
    return [c * r for r in returns]


def column_pandas(df: pd.DataFrame, c: float):
    return df["returns"] * c


def column_polars(df: pl.DataFrame, c: float):
    return df["returns"] * c


def attribute_pandas(df: pd.DataFrame, c: float):
    return df.returns * c


def copy_pandas(df: pd.DataFrame):
    return df.copy()


def copy_polars(df: pl.DataFrame):
    return df.clone()


def shift_pandas(df: pd.DataFrame):
    return df + 1


def shift_polars(df: pl.DataFrame):
    return df + 1


def double_pandas(df: pd.DataFrame):
    return df * 2


def double_polars(df: pl.DataFrame):
    return df * 2


_VECTOR_FUNCTIONS = [scale_numpy, scale_pandas, scale_polars, scale_list]
_TABLE_FUNCTIONS = [column_pandas, column_polars, attribute_pandas]

_VECTOR_CLAIMS = [
    ("for returns in R^n, c in [-2, 2], f(returns, c) == c * returns",
     "for returns in R^n, c in [-2, 2], f(returns, c) == returns + c"),
    ("for returns in R^n, c in [-2, 2], "
     "norm(f(returns, c)) ~= abs(c) * norm(returns)",
     "for returns in R^n, c in [-2, 2], "
     "norm(f(returns, c)) ~= c * norm(returns)"),
    ("for returns in R^n, c in [-2, 2], "
     "mean(f(returns, c)) ~= c * mean(returns)",
     "for returns in R^n, c in [-2, 2], "
     "mean(f(returns, c)) ~= mean(returns) + c"),
    ("for returns in R^n, c in [-2, 2], "
     "dot(f(returns, c), returns) ~= c * norm(returns)**2",
     "for returns in R^n, c in [-2, 2], "
     "dot(f(returns, c), returns) ~= norm(returns)**2"),
    ("for returns in R^n, c in [-2, 2], "
     "f(returns + c, c) ~= c * returns + c * c",
     "for returns in R^n, c in [-2, 2], "
     "f(returns + c, c) ~= c * returns + c"),
]


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def _holds(p):
    return p.verdict in ("proven", "holds")


@pytest.mark.parametrize("fn", _VECTOR_FUNCTIONS)
@pytest.mark.parametrize("true, false", _VECTOR_CLAIMS)
def test_one_claim_text_on_every_vector_runtime_type(fn, true, false):
    # the claim's own side stays exact past the float limit (norm(...)**2
    # is the exact sum of squares, 61bfd67), so a corner draw decides
    p = _one(fn, true)
    assert _holds(p), (fn.__name__, true, p.verdict, p.note,
                       p.counterexample)
    p = _one(fn, false)
    assert p.verdict == "falsified", (fn.__name__, false, p.verdict, p.note)


_TABLE_CLAIMS = [
    ("for c in [-2, 2], f(df, c) == c * df.returns",
     "for c in [-2, 2], f(df, c) == df.returns + c"),
    ('for c in [-2, 2], f(df, c) == c * df["returns"]',
     'for c in [-2, 2], f(df, c) == df["returns"] + c'),
    ("for c in [-2, 2], norm(f(df, c)) ~= abs(c) * norm(df.returns)",
     "for c in [-2, 2], norm(f(df, c)) ~= norm(df.returns)"),
    ("for c in [-2, 2], mean(f(df, c)) ~= c * mean(df.returns)",
     "for c in [-2, 2], mean(f(df, c)) ~= mean(df.returns)"),
]


@pytest.mark.parametrize("fn", _TABLE_FUNCTIONS)
@pytest.mark.parametrize("true, false", _TABLE_CLAIMS)
def test_a_column_reads_as_a_vector_on_every_table_type(fn, true, false):
    p = _one(fn, true)
    assert _holds(p), (fn.__name__, true, p.verdict, p.note,
                       p.counterexample)
    p = _one(fn, false)
    assert p.verdict == "falsified", (fn.__name__, false, p.verdict, p.note)


@pytest.mark.parametrize("same, shifted, doubled", [
    (copy_pandas, shift_pandas, double_pandas),
    (copy_polars, shift_polars, double_polars),
])
def test_a_returned_dataframe_compares_element_by_element(same, shifted,
                                                          doubled):
    assert _holds(_one(same, "f(df) == df"))
    p = _one(shifted, "f(df) == df")
    assert p.verdict == "falsified", (p.verdict, p.note)
    p = _one(doubled, 'f(df)["a"] == 2 * df["a"]')
    assert _holds(p), (p.verdict, p.note, p.counterexample)
    p = _one(doubled, 'f(df)["a"] == df["a"]')
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("law", [
    "for c in [-2, 2], f(df, c) == c * df.returns",
    'for c in [-2, 2], f(df, c) == c * df["returns"]',
])
def test_the_scalar_derive_route_never_reads_a_column(law):
    p = _one(column_pandas, law, "derive")
    assert p.verdict == "unknown", (p.verdict, p.note)


def test_the_sampling_note_says_a_table_was_drawn():
    p = _one(column_pandas, "for c in [-2, 2], f(df, c) == c * df.returns",
             "probe")
    assert "df~Table(" in p.meta["mathema.sampling"], p.meta
