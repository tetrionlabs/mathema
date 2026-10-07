# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A scalar function in claim text reads an exact value beyond float
range.

`sum(x ** 2)` over large elements is an exact rational beyond float
range (the claim words keep such a value exact). `sqrt` and the
logarithms in the same claim compute from that exact value, so
`sqrt(sum(x ** 2))` is the true Euclidean length rather than an error,
and the claim is decided.
"""
from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import math  # noqa: E402
from fractions import Fraction  # noqa: E402

import numpy as np  # noqa: E402

from mathema._linalg_eval import FUNCTIONS  # noqa: E402
from mathema.conjecture import _SAFE_FUNCS  # noqa: E402


def test_sqrt_of_an_exact_value_beyond_float_range():
    square = Fraction(2e200) ** 2
    root = _SAFE_FUNCS["sqrt"](square)
    assert root == 2e200


def test_sqrt_of_a_sum_beyond_float_range_is_its_true_length():
    total = FUNCTIONS["sum"](np.array([1.7e308, 1.7e308]))
    assert isinstance(total, Fraction)
    root = _SAFE_FUNCS["sqrt"](total)
    assert math.isclose(float(root), math.sqrt(2) * math.sqrt(1.7e308),
                        rel_tol=1e-15)


def test_a_logarithm_of_an_exact_value_beyond_float_range():
    total = FUNCTIONS["sum"](np.array([1.7e308, 1.7e308]))
    assert math.isclose(_SAFE_FUNCS["log"](total),
                        math.log(2) + math.log(1.7e308), rel_tol=1e-15)
    assert math.isclose(_SAFE_FUNCS["log10"](total),
                        math.log10(2) + math.log10(1.7e308), rel_tol=1e-15)
    assert math.isclose(_SAFE_FUNCS["log2"](total),
                        1 + math.log2(1.7e308), rel_tol=1e-15)
