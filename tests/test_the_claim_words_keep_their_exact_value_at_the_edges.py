# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim words `sum`, `mean`, `prod`, `var`, `std`, `median`,
`quantile` and `dot` give the mathematical value at the edges of float
arithmetic.

Each is computed exactly and rounded once. A value beyond float range
stays exact (a `Fraction`) instead of becoming an infinity, so a
function that overflows to inf is judged against the true value and
the claim falsifies, rather than holding as inf against inf. Where the
mathematics has no value (opposite infinities added, an infinity times
zero, the order of complex numbers, a missing element) the word gives
nan; where it has an infinite value (an infinity added to finite
numbers, the interpolation between -inf and a number) it gives that
infinity. Integers are read exactly and a quantile level as written.
"""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

from mathema._linalg_eval import FUNCTIONS

INF = math.inf


def _a(*xs):
    return np.array(xs, dtype=float)


@pytest.mark.parametrize("word, args, exact", [
    ("sum", (_a(1e308, 1e308, -1e308),), 1e308),
    ("mean", (_a(1e308, 1e308),), 1e308),
    ("prod", (_a(1e200, 1e200, 1e-200),), 1e200),
    ("dot", (_a(1e308, 1e308, -1e308), _a(1.0, 1.0, 1.0)), 1e308),
    ("std", (_a(1e308, -1e308),), 1e308),
])
def test_an_intermediate_overflow_does_not_reach_the_value(word, args, exact):
    assert FUNCTIONS[word](*args) == exact


@pytest.mark.parametrize("word, args, exact", [
    ("sum", (_a(1.7e308, 1.7e308),), Fraction(1.7e308) * 2),
    ("mean", (_a(1.7e308, 1.7e308, 1.7e308),), Fraction(1.7e308)),
    ("prod", (_a(1e200, 1e200),), Fraction(1e200) ** 2),
    ("var", (_a(1e308, -1e308),), Fraction(1e308) ** 2),
    ("dot", (_a(1e200), _a(1e200)), Fraction(1e200) ** 2),
])
def test_a_value_beyond_float_range_stays_exact(word, args, exact):
    value = FUNCTIONS[word](*args)
    if exact > Fraction(1.7976931348623157e308):
        assert isinstance(value, Fraction) and value == exact, value
    else:
        assert value == float(exact)


def test_a_float_infinity_is_judged_against_the_exact_value():
    exact = FUNCTIONS["sum"](_a(1.7e308, 1.7e308))
    assert not math.isclose(INF, exact) if isinstance(exact, float) \
        else INF != exact


def test_mean_is_rounded_once():
    assert FUNCTIONS["mean"](_a(0.1, 0.2, 0.3)) == float(
        (Fraction(0.1) + Fraction(0.2) + Fraction(0.3)) / 3)
    one = 1 + 6e-16
    assert FUNCTIONS["mean"](_a(one, 0, 0, 0, 0, 0, 0)) == float(
        Fraction(one) / 7)


@pytest.mark.parametrize("word, args, expected", [
    ("sum", (_a(INF, 1.0),), INF),
    ("sum", (_a(INF, -INF),), None),
    ("mean", (_a(-INF, 1.0),), -INF),
    ("prod", (_a(INF, -2.0),), -INF),
    ("prod", (_a(INF, 0.0),), None),
    ("var", (_a(INF, 1.0),), None),
    ("std", (_a(INF, 1.0),), None),
    ("dot", (_a(INF, -INF), _a(1.0, 1.0)), None),
    ("dot", (_a(INF, 1.0), _a(0.0, 1.0)), None),
    ("dot", (_a(INF, 1.0), _a(2.0, 1.0)), INF),
    ("median", (_a(-INF, INF),), None),
    ("median", (_a(-INF, 1.0),), -INF),
    ("quantile", (_a(-INF, 0.0), 0.5), -INF),
    ("quantile", (_a(0.0, INF), 0.5), INF),
    ("quantile", (_a(-INF, INF), 0.5), None),
])
def test_an_infinity_gives_the_mathematical_value_or_none(word, args,
                                                          expected):
    value = FUNCTIONS[word](*args)
    if expected is None:
        assert math.isnan(value), value
    else:
        assert value == expected


@pytest.mark.parametrize("word", ["median", "quantile"])
def test_complex_numbers_have_no_order_statistic(word):
    xs = np.array([1 + 1j, 2 + 0j, 3 - 1j])
    args = (xs, 0.5) if word == "quantile" else (xs,)
    assert math.isnan(FUNCTIONS[word](*args))


def test_complex_sums_and_variances_are_exact():
    xs = np.array([1 + 1j, 2 + 0j, 3 - 1j, -2 + 0.5j])
    assert FUNCTIONS["sum"](xs) == 4 + 0.5j
    assert FUNCTIONS["mean"](xs) == 1 + 0.125j
    deviations = [abs(complex(x) - (1 + 0.125j)) ** 2 for x in xs]
    assert FUNCTIONS["var"](xs) == pytest.approx(sum(deviations) / 4,
                                                 rel=1e-15)


def test_integers_are_read_exactly():
    big = 2 ** 53 + 1
    assert FUNCTIONS["sum"](np.array([big, 0], dtype=object)) == float(big)
    assert FUNCTIONS["var"](np.array([big, 0], dtype=object)) == float(
        Fraction(big, 2) ** 2)
    assert FUNCTIONS["mean"]([big, big + 2]) == float(big + 1)


def test_a_quantile_level_is_read_as_written():
    assert FUNCTIONS["quantile"](_a(0.0, 1.0), 0.1) == 0.1
    assert FUNCTIONS["quantile"](_a(1.0, 1.0, 3.0, 5.0), 0.7) == 3.2


@pytest.mark.parametrize("word", ["sum", "mean", "prod", "var", "std",
                                  "median"])
def test_a_missing_element_leaves_no_value(word):
    assert math.isnan(FUNCTIONS[word](_a(1.0, math.nan, 2.0)))


def _total(a: np.ndarray) -> float:
    return float(np.sum(a))


def test_an_overflow_shows_on_the_computation_line():
    from mathema.conjecture import check_conjectures, claim
    probes = check_conjectures(_total, [claim(
        "for a in [1e307, 1.7e308]^n \\ {∅}, assuming dim(a) >= 2, "
        "f(a) ~= sum(a)")], float_companions=True)
    by_name = {p.name.split("[")[0] + ("[float]" if "[" in p.name else ""): p
               for p in probes}
    assert by_name["f_a_approx_sum_a"].verdict == "proven"
    companion = by_name["f_a_approx_sum_a[float]"]
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.note)
