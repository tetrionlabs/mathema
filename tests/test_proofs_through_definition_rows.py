# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Proofs about numpy, pandas and polars code, through definition rows.

The derive route reads `returns.mean() / returns.std(ddof=1) *
np.sqrt(252)` by rewriting each library call with its definition row
(`pandas.Series.std` is `std(a, ddof=1)`), then decides the claim as
mathematics: a vector claim as sums over a sequence of symbolic
length, so a proof holds for every length; a matrix claim in the
matrix algebra. The record names every row a proof used. Each proof
here stands beside a false sibling that must not prove.

Where the rewritten body has no value inside the claim's domain (a
standard deviation of zero in a denominator, a sample statistic of a
single element), the claim is false there: executed at such a point,
the function returns no value, and the claim is falsified with that
witness. A premise that excludes the region
(`assuming std(returns, ddof=1) > 0`) makes it provable.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("polars")

import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from mathema.claims import check_conjectures, claim  # noqa: E402


def sharpe(returns: pd.Series):
    return returns.mean() / returns.std(ddof=1) * np.sqrt(252)


def sharpe_numpy(returns: np.ndarray):
    return np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252)


def sharpe_polars(returns: pl.Series):
    return returns.mean() / returns.std() * math.sqrt(252)


def volatility(returns: pd.Series):
    periods = 252
    return returns.std() * np.sqrt(periods)


def transpose(A: np.ndarray):
    return A.T


inverse = lambda A: np.linalg.inv(A)  # noqa: E731


def smoothed(returns: pd.Series):
    return returns.ewm(span=3).mean().iloc[-1]


_LEVERAGE = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, "
             "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
             "f(s(returns, c)) ~= f(returns)")
_SHIFT = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.shift_seq, "
          "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
          "f(s(returns, c)) ~= f(returns)")


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


@pytest.mark.parametrize("fn, rows", [
    (sharpe, ["pandas.Series.mean definition",
              "pandas.Series.std definition"]),
    (sharpe_numpy, ["numpy.mean definition", "numpy.std definition@ddof=1"]),
    (sharpe_polars, ["polars.Series.mean definition",
                     "polars.Series.std definition"]),
])
def test_a_sharpe_ratio_is_leverage_invariant_for_every_length(fn, rows):
    p = _one(fn, _LEVERAGE)
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    assert p.route == "derive"
    used = p.meta["mathema.definitions"]
    assert [f"{u['key']} {u['row']}" for u in used] == rows
    assert all(u["status"] == "bundled" for u in used), used
    assert all(u["source"].startswith("mathema/compendium/") for u in used)
    assert "every length" in p.sketch
    # the false sibling: a Sharpe ratio is not shift invariant
    p = _one(fn, _SHIFT, route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(fn, _SHIFT)
    assert p.verdict == "falsified", (p.verdict, p.note)


def sharpe_power(returns: pd.Series):
    return returns.mean() / returns.std(ddof=1) * 252 ** 0.5


@pytest.mark.needs_full_proof_budget
def test_an_annualised_sharpe_written_with_a_power_proves_as_with_sqrt():
    p = _one(sharpe_power, _LEVERAGE)
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    assert p.route == "derive"
    p = _one(sharpe_power, _SHIFT, route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_a_sharpe_ratio_has_no_value_where_the_returns_do_not_vary():
    law = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, "
           "let c be [0.1, 10], f(s(returns, c)) ~= f(returns)")
    p = _one(sharpe, law, route="derive")
    assert p.verdict == "falsified", (p.verdict, p.note, p.sketch)
    assert p.counterexample.startswith("returns = [0.0]"), p.counterexample
    assert "returns NaN" in p.counterexample, p.counterexample
    assert "std(returns, ddof=1) == 0" in p.sketch, p.sketch


def test_negation_and_reversal_read_on_the_vector_itself():
    base = ("for returns in [-0.1, 0.1]^n, "
            "assuming std(returns, ddof=1) > 0, ")
    p = _one(sharpe, base + "f(-returns) ~= -f(returns)", route="derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _one(sharpe, base + "f(returns[::-1]) ~= f(returns)", route="derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _one(sharpe, base + "f(-returns) ~= f(returns)", route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(sharpe, base + "f(-returns) ~= f(returns)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_volatility_is_shift_invariant_and_scales_but_is_not_leverage_invariant():
    base = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.{t}, "
            "let c be [0.1, 10], assuming dim(returns) >= 2, ")
    p = _one(volatility, base.format(t="shift_seq")
             + "f(s(returns, c)) ~= f(returns)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    p = _one(volatility, base.format(t="scale_seq")
             + "f(s(returns, c)) ~= c * f(returns)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    leverage = base.format(t="scale_seq") + "f(s(returns, c)) ~= f(returns)"
    p = _one(volatility, leverage, route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(volatility, leverage)
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_sample_statistic_of_one_element_has_no_value():
    law = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.shift_seq, "
           "let c be [0.1, 10], f(s(returns, c)) ~= f(returns)")
    p = _one(volatility, law, route="derive")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "dim(returns) < 2" in p.sketch, p.sketch


def test_transpose_is_an_involution_through_the_attribute_row():
    p = _one(transpose, "for A in R^(n,n), f(f(A)) == A")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert [u["key"] for u in p.meta["mathema.definitions"]] == \
        ["numpy.ndarray.T"]
    p = _one(transpose, "for A in R^(n,n), f(A) == A", route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(transpose, "for A in R^(n,n), f(A) == A")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_inverse_of_a_nonsingular_matrix_through_numpy_linalg_inv():
    p = _one(inverse, "for A in R^(n,n), assuming det(A) != 0, "
                      "f(A) @ A == I(n)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert [u["key"] for u in p.meta["mathema.definitions"]] == \
        ["numpy.linalg.inv"]
    p = _one(inverse, "for A in R^(n,n), f(A) @ A == I(n)", route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    assert "det(A) != 0" in p.note, p.note
    p = _one(inverse, "for A in R^(n,n), assuming det(A) != 0, "
                      "f(A) @ A == A", route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_a_call_with_no_definition_row_names_its_key():
    p = _one(smoothed, "for returns in [-0.1, 0.1]^n, "
                       "f(returns) <= max(returns)", route="derive")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "pandas.Series.ewm has no definition row" in p.note, p.note
