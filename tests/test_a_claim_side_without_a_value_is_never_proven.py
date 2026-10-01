# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose own expression has no real value somewhere in its
domain (`x/x` at 0, `exp(log(x))` below 0, `1/x**2` at 0) is never
proven there, however sympy rewrites it: the regions are read from the
claim as written, before anything evaluates. The same holds for a pole
an interval hull reports as an infinite end over a bounded box, and for
a division the nonlinear solver would read as total."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


def one(x: float) -> float:
    return 1.0


def cube(x: float) -> float:
    return x ** 3


def less_one(x: float) -> float:
    return x - 1


def square(x: float) -> float:
    return x * x


def reciprocal_times(x: float) -> float:
    return x ** -1 * x


def shifted_reciprocal_square(x: float) -> float:
    return (x - 1) ** -2 * (x - 1) ** 2


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (ident, "for x in [-1, 1], exp(log(f(x))) == x"),
    (ident, "for x in [-1, 1], f(x) == exp(log(x))"),
    (ident, "for x in [-1, 1], x**2/x == f(x)"),
    (one, "for x in [-1, 1], f(x) == x/x"),
    (one, "for x in [-1, 1], f(x) == x*(1/x)"),
    (ident, "for x in [-1, 1], f(x) == sqrt(x)**2"),
    (ident, "for x in [-1, 1], f(x) == x**(1/2)*x**(1/2)"),
    (cube, "for x in [-1, 1], (f(x) + x**2)/x**2 >= 0"),
    (square, "for x in [-1, 1], f(x) + 1/x**2 >= 0"),
    (less_one, "for x in [0, 2], f(x) / f(x) == 1"),
])
def test_a_claim_side_with_no_value_in_the_domain_is_not_proven(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="derive")])
    assert p.verdict != "proven", (text, p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (one, "for x in [0.5, 1], f(x) == x/x"),
    (ident, "for x in [0.5, 2], f(x) == exp(log(x))"),
    (square, "for x in [0.5, 1], f(x) + 1/x**2 >= 0"),
])
def test_the_same_claim_where_every_side_has_a_value_is_proven(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="derive")])
    assert p.verdict == "proven", (text, p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (reciprocal_times, "for x in [-1, 1], f(x) == 1"),
    (shifted_reciprocal_square, "for x in [0, 2], f(x) == 1"),
])
def test_a_negative_power_of_zero_in_the_body_falsifies(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="derive")])
    assert p.verdict == "falsified", (text, p.verdict, p.sketch)


def test_an_infinite_hull_over_a_bounded_box_bounds_nothing():
    from mathema.symbolic._proof_support import _interval_bounds
    x = sympy.Symbol("x", real=True)
    assert _interval_bounds(1 / x**2 + x**2, {"x": (-1, 1)}, {"x": x}) is None
    hull = _interval_bounds(1 / x**2 + x**2, {"x": (0.5, 1)}, {"x": x})
    assert hull is not None and hull.max.is_finite


def test_the_nonlinear_solver_does_not_read_a_division_as_total():
    pytest.importorskip("z3")
    from mathema.symbolic._smt import nlsat_decide
    x = sympy.Symbol("x", real=True)
    # one where x != -1, no value at x = -1
    diff = (x + 1) ** 2 / (x ** 2 + 2 * x + 1) - 1
    result = nlsat_decide(diff, "<=", {"x": (-2, 0)}, {"x": x})
    assert result is None or result.status != "proven"
    result = nlsat_decide(diff, "<=", {"x": (0, 1)}, {"x": x})
    assert result is not None and result.status == "proven"
