# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Running extrema, least and greatest elements, elementwise vector
arithmetic and table columns: read on the probe, lowered on derive.

`cummax(a)` and `cummin(a)` are the running maximum and minimum of a
vector, as `numpy.maximum.accumulate` computes them. On the derive
route a running maximum has no closed form, so `cummax(a)` lowers to
a fresh sequence `m` known through its bounds: `m[i] >= a[i]`, and
`m[i]` is one of `a[0..i]`, so it lies within `a`'s element bounds;
for a positive `a`, `0 < a[i] / m[i] <= 1`. `min(v)` and `max(v)`
lower to a number below (above) every element of `v` that is one of
them, and the least element is at most the mean and the greatest at
least it. Each positive case here stands beside a negative control
that the derive route does not prove and sampling falsifies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mathema.claims import check_conjectures, claim


def running_peak(a: pd.Series):
    return a.cummax()


def running_trough(a: pd.Series):
    return a.cummin()


def peak_np(a: np.ndarray):
    return np.maximum.accumulate(a)


def least(xs: pd.Series):
    return float(xs.min())


def greatest(xs: pd.Series):
    return float(xs.max())


def column_total(df: pd.DataFrame):
    return float(df["w"].sum())


def ratio_total(df: pd.DataFrame):
    return float((df.w / df.r).sum())


def _one(fn, law, route="best", extensive=False):
    (p,) = check_conjectures(fn, [claim(law, route=route)],
                             extensive=extensive)
    return p


@pytest.mark.parametrize("fn, true, false", [
    (running_peak, "for a in R^n, f(a) ~= cummax(a)",
     "for a in R^n, f(a) ~= cummin(a)"),
    (running_trough, "for a in R^n, f(a) ~= cummin(a)",
     "for a in R^n, f(a) ~= cummax(a)"),
    (peak_np, "for a in R^n, max(f(a)) == max(a)",
     "for a in R^n, min(f(a)) == min(a)"),
    (peak_np, "for a in R^n, f(a)[-1] == max(a)",
     "for a in R^n, f(a)[-1] == a[-1]"),
])
def test_running_extrema_read_on_the_probe(fn, true, false):
    p = _one(fn, true, route="probe")
    assert p.verdict == "holds", (true, p.verdict, p.note, p.counterexample)
    p = _one(fn, false, route="probe")
    assert p.verdict == "falsified", (false, p.verdict, p.note)


def _proven(fn, law):
    p = _one(fn, law)
    assert (p.verdict, p.route) == ("proven", "derive"), \
        (law, p.verdict, p.note, p.sketch)
    return p


def _not_proven_and_false(fn, law):
    p = _one(fn, law, route="derive")
    assert p.verdict != "proven", (law, p.verdict, p.sketch)
    p = _one(fn, law, extensive=True)
    assert p.verdict == "falsified", (law, p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, true, false", [
    # a running maximum is at least the element it runs to
    (running_peak, "for a in R^n, min(f(a) - a) >= 0",
     "for a in R^n, min(a - f(a)) >= 0"),
    (running_trough, "for a in R^n, max(f(a) - a) <= 0",
     "for a in R^n, max(a - f(a)) <= 0"),
    # it lies within the bounds of the elements it runs over
    (running_peak, "for a in [1, 100]^n, min(f(a)) >= 1",
     "for a in [1, 100]^n, min(f(a)) >= 2"),
    # for a positive vector, 0 < a[i] / cummax(a)[i] <= 1
    (running_peak, "for a in [1, 100]^n, max(a / f(a)) <= 1",
     "for a in [1, 100]^n, max(a / f(a)) < 1"),
    (running_peak, "for a in [1, 100]^n, min(a / f(a) - 1) > -1",
     "for a in [1, 100]^n, min(a / f(a) - 1) > -0.5"),
    (running_trough, "for a in [1, 100]^n, min(a / f(a)) >= 1",
     "for a in [1, 100]^n, min(a / f(a)) > 1"),
])
def test_running_extrema_lower_through_their_bounds(fn, true, false):
    p = _proven(fn, true)
    assert p.meta["mathema.definitions"], p.meta
    _not_proven_and_false(fn, false)


def test_the_ratio_bound_needs_a_positive_vector():
    p = _one(running_peak, "for a in [-1, -0.5]^n, max(a / f(a)) <= 1",
             route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(running_peak, "for a in [-1, -0.5]^n, max(a / f(a)) <= 1",
             extensive=True)
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, true, false", [
    (least, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in [0, 1]^n, f(xs) > 0"),
    (least, "for xs in [0, 1]^n, f(xs) <= 1",
     "for xs in [0, 1]^n, f(xs) <= 0.5"),
    (least, "for xs in R^n, f(xs) <= mean(xs)",
     "for xs in R^n, f(xs) >= mean(xs)"),
    (greatest, "for xs in R^n, f(xs) >= mean(xs)",
     "for xs in R^n, f(xs) <= mean(xs)"),
    (greatest, "for xs in [-3, 2]^n, 2 * f(xs) + 1 <= 5",
     "for xs in [-3, 2]^n, 2 * f(xs) + 1 <= 4"),
])
def test_least_and_greatest_elements_lower_through_their_bounds(fn, true,
                                                               false):
    _proven(fn, true)
    _not_proven_and_false(fn, false)


@pytest.mark.needs_full_proof_budget
def test_a_table_column_reads_as_a_vector_on_derive():
    p = _proven(column_total, "for df in R^n, f(df) ~= sum(df.w)")
    assert [u["key"] for u in p.meta["mathema.definitions"]] == \
        ["pandas.Series.sum"]
    _not_proven_and_false(column_total, "for df in R^n, f(df) ~= sum(df.r)")


@pytest.mark.needs_full_proof_budget
def test_elementwise_division_of_two_columns():
    _proven(ratio_total, "for df in [1, 2]^n, f(df) ~= sum(df.w / df.r)")
    # a column's own binding bounds that column
    _proven(ratio_total, "for df.w in R^n, df.r in [1, 2]^n, "
                         "f(df) ~= sum(df.w / df.r)")
    _not_proven_and_false(ratio_total,
                          "for df in [1, 2]^n, f(df) ~= sum(df.r / df.w)")


def test_a_table_is_drawn_inside_the_claims_bounds():
    p = _one(column_total, "for df in [0, 1]^n, 0 <= f(df) <= dim(df.w)",
             route="probe")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
