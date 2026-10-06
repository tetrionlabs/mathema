# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim compares a function's result with a claim word's exact
value beyond float range, exactly.

Over `[1e307, 1.7e308]^n` the exact `sum(a)` can exceed the largest
float; the claim word keeps it exact. A function that caps its float
sum at the largest float is then below the exact sum (`f(a) <= sum(a)`
holds), not above it, and not approximately equal to it: each relation
is decided by exact comparison, with no conversion to float that could
overflow. A function that overflows to inf is falsified with the gap
in view, also along an axis and under a square root.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import math  # noqa: E402
import sys  # noqa: E402

import numpy as np  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402

_BIG = sys.float_info.max
_OVER = "for a in [1e307, 1.7e308]^n \\ {∅}, assuming dim(a) >= 2, "


def capped_sum(a: np.ndarray) -> float:
    """The float sum, capped at the largest float instead of inf."""
    s = 0.0
    for v in a:
        s = s + float(v)
    return _BIG if math.isinf(s) and s > 0 else s


def column_sums(a: np.ndarray) -> np.ndarray:
    """The float sum of each column."""
    return np.sum(a, axis=0)


def root_of_sum(a: np.ndarray) -> float:
    """The square root of the float sum."""
    s = 0.0
    for v in a:
        s = s + float(v)
    return math.sqrt(s)


def _verdict(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


@pytest.mark.parametrize("relation, verdict", [
    ("<=", "holds"), (">=", "falsified"), ("~=", "falsified")])
def test_a_capped_sum_is_compared_exactly_with_the_exact_sum(relation,
                                                              verdict):
    p = _verdict(capped_sum, _OVER + f"f(a) {relation} sum(a)")
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)


def test_an_overflow_along_an_axis_is_falsified():
    p = _verdict(column_sums, "for a in [1e307, 1.7e308]^(m,n) \\ {∅}, "
                 "assuming dim(a) >= 2, f(a) ~= sum(a, axis=0)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_an_overflow_under_a_square_root_is_falsified():
    p = _verdict(root_of_sum, _OVER + "f(a) ~= sqrt(sum(a))")
    assert p.verdict == "falsified", (p.verdict, p.note)
