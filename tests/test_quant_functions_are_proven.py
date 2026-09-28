# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Quant functions of the kind a returns-analytics library is made of,
proven on the derive route through definition rows.

`tests/fixtures/quant/quantlib.py` holds the functions: a mean, a
Sharpe ratio, volatility, the maximum drawdown of a price path and a
weighted return of a two-column table. Each claim here is one a user
of such a library would write, and each is proven for every length
of the input, through the pandas or numpy definition rows the body
calls (named in the record). Every proof stands beside a false
sibling that the derive route does not prove, and that sampling
falsifies with a witness.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim
from tests.fixtures.quant import quantlib as q


def _one(fn, law, route="best", extensive=False):
    (p,) = check_conjectures(fn, [claim(law, route=route)],
                             extensive=extensive)
    return p


def _rows(p) -> list:
    return [f"{u['key']} {u['row']}"
            for u in p.meta.get("mathema.definitions") or []]


def _is_false(fn, law):
    p = _one(fn, law, route="derive")
    assert p.verdict != "proven", (law, p.verdict, p.sketch)
    p = _one(fn, law, extensive=True)
    assert p.verdict == "falsified", (law, p.verdict, p.note)
    assert p.counterexample, (law, p.note)


@pytest.mark.parametrize("fn, rows", [
    (q.mean_pd, ["pandas.Series.mean definition"]),
    (q.mean_np, ["numpy.mean definition"]),
])
def test_a_mean_lies_between_the_least_and_the_greatest_element(fn, rows):
    p = _one(fn, "for xs in R^n, min(xs) <= f(xs) <= max(xs)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert _rows(p) == rows, p.meta
    _is_false(fn, "for xs in R^n, f(xs) < min(xs)")
    _is_false(fn, "for xs in R^n, f(xs) > max(xs)")


@pytest.mark.parametrize("law", [
    "for prices in [1, 100]^n, f(prices) <= 0",
    "for prices in [1, 100]^n, f(prices) >= -1",
])
def test_a_maximum_drawdown_lies_between_minus_one_and_zero(law):
    p = _one(q.max_drawdown, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert _rows(p) == ["pandas.Series.cummax definition",
                        "pandas.Series.min definition"], p.meta
    assert "every length" in p.sketch, p.sketch


@pytest.mark.parametrize("law", [
    # false where the prices never fall (a constant path)
    "for prices in [1, 100]^n, f(prices) < 0",
    "for prices in [1, 100]^n, f(prices) >= -0.5",
])
def test_a_maximum_drawdown_is_not_always_negative_nor_above_a_half(law):
    _is_false(q.max_drawdown, law)


def test_a_weighted_return_is_the_dot_product_of_its_columns():
    p = _one(q.weighted_return, "for df in [0, 1]^n, f(df) ~= dot(df.w, df.r)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert _rows(p) == ["pandas.Series.sum definition"], p.meta
    _is_false(q.weighted_return,
              "for df in [0, 1]^n, f(df) ~= dot(df.w, df.w)")


def test_a_weighted_return_reads_a_column_by_item_as_by_attribute():
    p = _one(q.weighted_return,
             'for df in [0, 1]^n, f(df) ~= dot(df["r"], df["w"])')
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)


_LEVERAGE = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, "
             "let c be [0.1, 10], assuming std(returns, ddof=1) > 0, "
             "f(s(returns, c)) ~= f(returns)")


def test_sharpe_and_volatility_stay_proven():
    p = _one(q.sharpe, _LEVERAGE)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    p = _one(q.volatility,
             "for returns in [-0.1, 0.1]^n, let s = mathema.f.shift_seq, "
             "let c be [0.1, 10], assuming dim(returns) >= 2, "
             "f(s(returns, c)) ~= f(returns)")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
