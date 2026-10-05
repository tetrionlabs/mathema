# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`missing` in a membership bound names the hole class, resolved per
slot type: a polars Series holds its holes as null and nan, a pandas
Series as nan, None and NA, a numpy array as nan. So a reduction that
answers an empty Series with its own null (`None`) is in `{missing}`,
while a function on plain numbers that returns None is not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl

from mathema.claims import check_conjectures, claim
from mathema.conjecture import _resolve_func_ref


def _verdict(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_a_polars_null_for_an_empty_series_is_missing():
    p = _verdict(_resolve_func_ref("polars.Series.mean"), "f([]) in {missing}")
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


def test_a_polars_null_from_a_function_on_a_series_is_missing():
    def mean_pl(xs: pl.Series) -> float:
        return xs.mean()
    p = _verdict(mean_pl, "f([]) in {missing}")
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


def test_pandas_holes_are_missing():
    def mean_pd(xs: pd.Series) -> float:
        return xs.mean()

    def na_pd(xs: pd.Series):
        return pd.NA

    def none_pd(xs: pd.Series):
        return None
    for fn in (mean_pd, na_pd, none_pd):
        p = _verdict(fn, "f([]) in {missing}")
        assert p.verdict in ("holds", "proven"), (fn.__name__, p.verdict,
                                                  p.counterexample)


def test_a_numpy_nan_is_missing_and_a_plain_none_is_not():
    def mean_np(xs: np.ndarray) -> float:
        return float(np.mean(xs)) if len(xs) else float("nan")

    def none_plain(x: float):
        return None
    assert _verdict(mean_np, "f([]) in {missing}").verdict in ("holds",
                                                                "proven")
    p = _verdict(none_plain, "f(1.0) in {missing}")
    assert p.verdict == "falsified", (p.verdict, p.counterexample)


def test_the_witness_of_a_literal_empty_call_is_the_empty_input():
    def mean_np_plain(xs: np.ndarray) -> float:
        return 1.0
    p = _verdict(mean_np_plain, "f([]) in {missing}")
    assert p.verdict == "falsified", (p.verdict, p.counterexample)
    assert p.counterexample.startswith("xs = []"), p.counterexample
