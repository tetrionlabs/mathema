# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A point where the float run of f overflows, or turns an overflow into
a nan, is no witness that f has no value there: x * 1e308 is a finite
number at every real x, and 1e308 * x - 1e308 * x is 0. An executed
witness for `is_defined` reads the call's infinity or nan through the
same evidence the region probe uses (an overflow error, numpy's
overflow flag, the body read exactly), and an infinity counts as the
body's own only when the body read exactly at that point returns one it
writes on the path the call takes."""
import math
import warnings

import pytest

np = pytest.importorskip("numpy")

from mathema.claim_families import _exact_reading, _nonfinite_cause  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402

SCALE = np.float64(1e308)


def scaled(x: float) -> float:
    i = 0
    while i < 1:
        i += 1
    return float(x * SCALE)


def scaled_with_unreached_infinity(x: float) -> float:
    i = 0
    while i < 1:
        i += 1
    if x < -1e300:
        return -math.inf
    return float(x * SCALE)


def written_past_one(x: float) -> float:
    return x if x <= 0 else math.inf


def difference_of_equal_products(x: float) -> float:
    big = x * 1e308
    return big - big


def numpy_difference_of_equal_products(x: float) -> float:
    big = np.float64(x) * np.float64(1e308)
    return float(big - big)


def _one(fn, text):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        (p,) = check_conjectures(fn, [claim(text)])
    return p


@pytest.mark.parametrize("fn", [scaled, scaled_with_unreached_infinity])
def test_an_overflowing_product_is_defined_with_the_overflow_reported(fn):
    p = _one(fn, "for x in [0, 10], is_defined(f)")
    assert p.verdict == "holds", (p.verdict, p.route, p.counterexample, p.note)
    assert "overflow" in (p.note or ""), p.note


@pytest.mark.parametrize("fn", [scaled, scaled_with_unreached_infinity])
def test_the_negation_is_not_proven_from_an_overflow(fn):
    p = _one(fn, "for x in [0, 10], not is_defined(f)")
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample, p.note)


@pytest.mark.parametrize("fn", [difference_of_equal_products,
                                numpy_difference_of_equal_products])
@pytest.mark.parametrize("text", ["for x in [0, 3], is_defined(f)",
                                  "is_defined(f)"])
def test_a_nan_from_an_overflow_is_not_a_missing_value(fn, text):
    p = _one(fn, text)
    assert p.verdict in ("holds", "proven"), (
        p.verdict, p.route, p.counterexample, p.note)


def test_an_infinity_on_a_branch_not_taken_is_not_the_body_s_own():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert _exact_reading(scaled_with_unreached_infinity, (2.0,), {}) is None
        assert _nonfinite_cause(scaled_with_unreached_infinity, math.inf, None,
                                (2.0,), {}) == "overflow"


def test_an_infinity_on_the_branch_taken_is_the_body_s_own():
    assert _exact_reading(written_past_one, (1.0,), {}) == "no value"
    p = _one(written_past_one, "for x in [-1, 1], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.counterexample, p.note)
