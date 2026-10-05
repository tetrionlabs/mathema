# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim word `norm` keeps its exact value: the Euclidean norm is
the square root of the exact sum of squares, so its square is that sum
exactly, even where the sum lies beyond float range. `dot(x, x) ==
norm(x)**2` at `x = [1e300, -1e300]` compares `2e600` with `2e600`
rather than overflowing."""
from fractions import Fraction

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

from mathema._linalg_eval import FUNCTIONS, as_array  # noqa: E402

CORNER = [1e300, -1e300]


def identity(x: list[float]) -> list[float]:
    return x


@pytest.mark.parametrize("src", ["norm(x)**2", "norm(x, 2)**2",
                                 "norm(x, ord=2) ** 2"])
def test_the_square_of_a_norm_is_the_exact_sum_of_squares(src):
    x = as_array(CORNER)
    value = eval(src, {**FUNCTIONS, "x": x})  # noqa: S307
    assert value == FUNCTIONS["dot"](x, x) == Fraction(2) * Fraction(1e300) ** 2


def test_a_norm_still_reads_as_the_float_nearest_it():
    norm = FUNCTIONS["norm"](as_array([3.0, 4.0]))
    assert norm == 5.0 and float(norm) == 5.0
    assert FUNCTIONS["norm"](as_array(CORNER)) == float(2 ** 0.5 * 1e300)


def test_a_frobenius_norm_squared_is_the_exact_sum_of_squares():
    A = as_array([[1e300, 0.0], [0.0, -1e300]])
    assert FUNCTIONS["norm"](A) ** 2 == 2 * Fraction(1e300) ** 2


def test_the_squared_length_identity_holds_at_the_magnitude_corner():
    (p,) = check_conjectures(identity, [claim(
        "for x in R^n, dot(f(x), f(x)) == norm(f(x))**2")])
    assert p.verdict == "holds", (p.verdict, p.note)
