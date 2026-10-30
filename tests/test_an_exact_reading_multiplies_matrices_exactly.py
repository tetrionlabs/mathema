# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body follows numpy's array construction and
matrix products on exact numbers: `numpy.asarray`, `numpy.array`,
`numpy.dot`, `numpy.matmul` and `@` over arrays of exact numbers are the
same products and sums in exact arithmetic. A body wrapped by
`enforce_dimensions` is read as its dimension checks around the body."""
from fractions import Fraction

import pytest

np = pytest.importorskip("numpy")

from mathema import enforce_dimensions  # noqa: E402
from mathema._exact_body import NotExact, exact_callee  # noqa: E402
from mathema.claim_families import _exact_reading  # noqa: E402
from mathema.types import Mat, Vec  # noqa: E402

LARGEST = 1.7976931348623157e308


def quadratic_form(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def by_dot(a: Mat("n", "n"), b: Mat("n", "n")) -> float:
    return float(np.dot(np.array(a), np.array(b))[0][0])


def by_matmul(a: Mat("n", "n"), x: Vec("n")) -> float:
    return float(np.matmul(np.asarray(a), np.asarray(x))[1])


@enforce_dimensions()
def guarded_form(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def sorted_entries(weights: Vec("n")) -> float:
    return float(np.sort(np.asarray(weights))[0])


def largest_entry(weights: Vec("n")) -> float:
    return float(np.asarray(weights).max())


def test_a_quadratic_form_is_read_exactly():
    exact = exact_callee(quadratic_form)([Fraction(3, 2), 2],
                                         [[1, Fraction(1, 2)],
                                          [Fraction(1, 2), 2]])
    assert exact == Fraction(53, 4)


def test_dot_and_matmul_are_read_exactly():
    third = Fraction(1, 3)
    assert exact_callee(by_dot)([[third, 1], [0, 1]],
                                [[3, 0], [1, 1]]) == 2
    assert exact_callee(by_matmul)([[1, 0], [third, third]],
                                   [3, 6]) == 3


def test_an_overflowing_quadratic_form_reads_as_an_overflow():
    weights = [LARGEST, LARGEST]
    cov = [[LARGEST, LARGEST], [LARGEST, LARGEST]]
    for fn in (quadratic_form, guarded_form):
        assert _exact_reading(fn, (weights, cov), {}) == "overflow", fn


def test_a_dimension_check_still_raises_in_the_reading():
    with pytest.raises(ValueError):
        exact_callee(guarded_form)([1, 2], [[1]])


def test_a_function_or_method_on_an_exact_array_is_declined():
    for fn in (sorted_entries, largest_entry):
        with pytest.raises(NotExact):
            exact_callee(fn)([Fraction(1, 3), 2])
