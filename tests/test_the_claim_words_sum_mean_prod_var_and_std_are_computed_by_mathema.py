# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim words `sum`, `mean`, `prod`, `var` and `std` are computed
by mathema itself, never by numpy's own functions of those names.

A row stating `numpy.sum` as `sum(a)` is checked by comparing numpy
against the word, so the word must mean what it says on its own: the
sum added without intermediate rounding, the mean as that sum over the
length, the product of the elements in order, and the variance (and
its square root, the standard deviation) as the mean squared deviation
from the mean, computed exactly, with `ddof` taken from the length in
the divisor. A broken numpy cannot make such a row hold.
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
    for name in ("sum", "mean", "prod", "var", "std", "nansum", "nanmean",
                 "add", "multiply"):
        monkeypatch.setattr(np, name, wrong)


def test_sum_adds_without_intermediate_rounding(broken_numpy):
    assert FUNCTIONS["sum"](np.array([1e16, 1.0, -1e16])) == 1.0
    assert FUNCTIONS["sum"](np.array([0.1, 0.2, 0.3])) == 0.6


def test_sum_along_an_axis_is_one_sum_per_column(broken_numpy):
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert list(FUNCTIONS["sum"](a, axis=0)) == [4.0, 6.0]
    assert list(FUNCTIONS["sum"](a, axis=1)) == [3.0, 7.0]


def test_mean_is_the_exact_sum_over_the_length(broken_numpy):
    assert FUNCTIONS["mean"](np.array([1e16, 1.0, -1e16, 2.0])) == 0.75
    assert list(FUNCTIONS["mean"](np.array([[1.0, 2.0], [3.0, 6.0]]),
                                  axis=0)) == [2.0, 4.0]


def test_prod_multiplies_the_elements(broken_numpy):
    assert FUNCTIONS["prod"](np.array([2.0, 3.0, 4.0])) == 24.0
    assert list(FUNCTIONS["prod"](np.array([[1.0, 2.0], [3.0, 4.0]]),
                                  axis=0)) == [3.0, 8.0]


def test_var_and_std_take_ddof_in_the_divisor(broken_numpy):
    xs = np.array([1.0, 2.0, 4.0])
    assert FUNCTIONS["var"](xs) == pytest.approx(14.0 / 9.0, rel=1e-15)
    assert FUNCTIONS["var"](xs, ddof=1) == pytest.approx(7.0 / 3.0,
                                                         rel=1e-15)
    assert FUNCTIONS["std"](xs, ddof=1) == pytest.approx(
        math.sqrt(7.0 / 3.0), rel=1e-15)


def test_var_survives_a_large_offset(broken_numpy):
    xs = np.array([1e9 + 4.0, 1e9 + 7.0, 1e9 + 13.0, 1e9 + 16.0])
    assert FUNCTIONS["var"](xs, ddof=1) == 30.0


def test_var_along_an_axis_is_one_variance_per_column(broken_numpy):
    a = np.array([[1.0, 5.0], [3.0, 5.0]])
    assert list(FUNCTIONS["var"](a, axis=0)) == [1.0, 0.0]


def test_too_few_elements_for_the_ddof_have_no_variance(broken_numpy):
    assert math.isnan(FUNCTIONS["var"](np.array([3.0]), ddof=1))
    assert math.isnan(FUNCTIONS["std"](np.array([3.0]), ddof=1))


def test_a_reduction_reads_the_value_slots(broken_numpy):
    xs = np.array([1.0, float("nan"), 2.0])
    for word, value in (("sum", 3.0), ("mean", 1.5), ("prod", 2.0), ("var", 0.25),
                        ("std", 0.5)):
        assert FUNCTIONS[word](xs) == value, word
    # over no value slot: the identity where there is one, else no value
    holes = np.array([float("nan")])
    assert FUNCTIONS["sum"](holes) == 0.0 and FUNCTIONS["prod"](holes) == 1.0
    assert math.isnan(FUNCTIONS["mean"](holes))
