# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim words `cumsum`, `cumprod`, `cummax` and `cummin` are
computed by mathema itself, never by numpy's own.

Entry `i` of `cumsum(a)` is the exact sum of elements `0..i` rounded
once, of `cumprod(a)` the exact product, and of `cummax(a)` and
`cummin(a)` the greatest and least of them by exact comparison. Each
entry has the value the mathematics gives it: a missing element leaves
it and every later entry without a value (nan), opposite infinities
added or an infinity times zero have none, and complex numbers have no
running extremum. A broken numpy cannot make a running row hold.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import math  # noqa: E402

import numpy as np  # noqa: E402

from mathema._linalg_eval import FUNCTIONS  # noqa: E402

INF = math.inf


@pytest.fixture()
def broken_numpy(monkeypatch):
    def wrong(*args, **kwargs):
        return np.full(3, 12345.0)
    for name in ("cumsum", "cumprod"):
        monkeypatch.setattr(np, name, wrong)

    class Broken:
        @staticmethod
        def accumulate(*args, **kwargs):
            return np.full(3, 12345.0)
    monkeypatch.setattr(np, "maximum", Broken)
    monkeypatch.setattr(np, "minimum", Broken)


def _list(values):
    return [float(v) if not isinstance(v, complex) else v for v in values]


def _same(got, expected):
    got = list(got)
    assert len(got) == len(expected), (got, expected)
    for g, e in zip(got, expected):
        if isinstance(e, float) and math.isnan(e):
            assert math.isnan(g), (got, expected)
        else:
            assert g == e, (got, expected)


def test_cumsum_is_the_exact_running_sum(broken_numpy):
    _same(FUNCTIONS["cumsum"](np.array([1e16, 1.0, 1.0, -1e16])),
          [1e16, float(10 ** 16 + 1), float(10 ** 16 + 2), 2.0])
    _same(FUNCTIONS["cumsum"](np.array([0.1, 0.2, 0.3])),
          [0.1, 0.30000000000000004, 0.6])


def test_cumprod_is_the_exact_running_product(broken_numpy):
    _same(FUNCTIONS["cumprod"](np.array([1e200, 1e200, 1e-200])),
          [1e200, FUNCTIONS["prod"](np.array([1e200, 1e200])), 1e200])


def test_running_extrema_compare_exactly(broken_numpy):
    _same(FUNCTIONS["cummax"](np.array([2.0, 1.0, 3.0, -1.0])),
          [2.0, 2.0, 3.0, 3.0])
    _same(FUNCTIONS["cummin"](np.array([2.0, 1.0, 3.0, -1.0])),
          [2.0, 1.0, 1.0, -1.0])


def test_the_running_words_read_a_matrix_along_an_axis(broken_numpy):
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert FUNCTIONS["cumsum"](a, axis=0).tolist() == [[1.0, 2.0],
                                                       [4.0, 6.0]]
    assert FUNCTIONS["cummax"](a, axis=1).tolist() == [[1.0, 2.0],
                                                       [3.0, 4.0]]
    _same(FUNCTIONS["cumsum"](a), [1.0, 3.0, 6.0, 10.0])


def test_a_running_word_reads_the_value_slots_and_keeps_the_hole_in_place(
        broken_numpy):
    xs = np.array([1.0, math.nan, 2.0])
    for word, out in (("cumsum", [1.0, math.nan, 3.0]), ("cumprod", [1.0, math.nan, 2.0]),
                      ("cummax", [1.0, math.nan, 2.0]), ("cummin", [1.0, math.nan, 1.0])):
        _same(FUNCTIONS[word](xs), out)


def test_infinities_give_the_mathematical_entries(broken_numpy):
    _same(FUNCTIONS["cumsum"](np.array([1.0, INF, -INF])),
          [1.0, INF, math.nan])
    _same(FUNCTIONS["cumprod"](np.array([INF, 0.0, 2.0])),
          [INF, math.nan, math.nan])
    _same(FUNCTIONS["cummax"](np.array([-INF, 1.0, INF])),
          [-INF, 1.0, INF])


def test_complex_numbers_have_no_running_extremum(broken_numpy):
    xs = np.array([1 + 1j, 2 + 0j])
    for word in ("cummax", "cummin"):
        _same(FUNCTIONS[word](xs), [math.nan, math.nan])
    _same(FUNCTIONS["cumsum"](xs), [1 + 1j, 3 + 1j])
