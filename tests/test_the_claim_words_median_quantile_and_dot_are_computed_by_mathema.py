# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim words `median`, `quantile` and `dot` are computed by
mathema itself, never by numpy's own median, quantile or dot.

A row stating `numpy.median` as `median(a)` is checked by comparing
numpy against the word, so the word must mean what it says on its
own: the middle of the sorted vector (the mean of the two middle
elements for an even length), the linearly interpolated quantile
(Hyndman and Fan's type 7, the default of numpy, pandas and R) in
exact arithmetic, and the inner product summed without intermediate
rounding. A broken numpy cannot make such a row hold.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mathema._linalg_eval import FUNCTIONS


@pytest.fixture()
def broken_numpy(monkeypatch):
    def wrong(*args, **kwargs):
        return 12345.0
    for name in ("median", "quantile", "percentile", "dot", "nanmedian"):
        monkeypatch.setattr(np, name, wrong)


def test_median_is_the_middle_of_the_sorted_vector(broken_numpy):
    assert FUNCTIONS["median"]([3.0, 1.0, 2.0]) == 2.0
    assert FUNCTIONS["median"]([5.0, 1.0, 1.0, 3.0]) == 2.0


def test_median_of_two_huge_elements_does_not_overflow(broken_numpy):
    assert FUNCTIONS["median"]([1.7e308, 1.7e308]) == 1.7e308


def test_median_along_an_axis_is_one_median_per_column(broken_numpy):
    out = FUNCTIONS["median"](np.array([[1.0, 4.0], [3.0, 2.0], [2.0, 9.0]]),
                              axis=0)
    assert list(out) == [2.0, 4.0]


def test_quantile_interpolates_linearly_in_exact_arithmetic(broken_numpy):
    xs = [5.0, 1.0, 1.0, 3.0]
    assert FUNCTIONS["quantile"](xs, 0.0) == 1.0
    assert FUNCTIONS["quantile"](xs, 0.25) == 1.0
    assert FUNCTIONS["quantile"](xs, 0.5) == 2.0
    assert FUNCTIONS["quantile"](xs, 0.7) == 3.1999999999999997
    assert FUNCTIONS["quantile"](xs, 1.0) == 5.0


def test_quantile_of_several_levels_is_one_quantile_per_level(broken_numpy):
    assert list(FUNCTIONS["quantile"]([5.0, 1.0, 1.0, 3.0], [0.5, 1.0])) \
        == [2.0, 5.0]


def test_a_level_outside_zero_to_one_has_no_quantile(broken_numpy):
    with pytest.raises(ValueError):
        FUNCTIONS["quantile"]([1.0, 2.0], 1.5)


def test_dot_sums_the_products_without_intermediate_rounding(broken_numpy):
    assert FUNCTIONS["dot"]([1e16, 1.0, -1e16], [1.0, 1.0, 1.0]) == 1.0
    assert FUNCTIONS["dot"]([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == 32.0


def test_dot_of_matrices_is_the_matrix_product(broken_numpy):
    out = FUNCTIONS["dot"](np.array([[1.0, 2.0], [3.0, 4.0]]),
                           np.array([[5.0, 6.0], [7.0, 8.0]]))
    assert out.tolist() == [[19.0, 22.0], [43.0, 50.0]]
    assert FUNCTIONS["dot"](np.array([[1.0, 2.0], [3.0, 4.0]]),
                            [1.0, 1.0]).tolist() == [3.0, 7.0]


def test_a_missing_element_leaves_median_and_quantile_without_a_value(
        broken_numpy):
    assert math.isnan(FUNCTIONS["median"]([1.0, float("nan"), 2.0]))
    assert math.isnan(FUNCTIONS["quantile"]([1.0, float("nan")], 0.5))
