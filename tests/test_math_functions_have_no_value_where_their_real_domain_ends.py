# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A math function called outside its real domain raises or has no
value there (gamma at a non-positive integer, atanh at |x| >= 1, a zero
base to a negative power, a fractional power of a negative base). A
value claim over a domain holding such a point is never proven, and a
bare `is_defined(f)` is falsified with the executed point."""
import math
import re

import pytest

from mathema.conjecture import check_conjectures, claim


def gamma_of(x: float) -> float:
    return math.gamma(x)


def lgamma_of(x: float) -> float:
    return math.lgamma(x)


def inverse_square(x: float) -> float:
    return x ** -2


def reciprocal_power(x: float) -> float:
    return x ** -1.0


def factorial_of(x: float) -> float:
    return math.factorial(x)


def tangent(x: float) -> float:
    return math.tan(x)


def atanh_of(x: float) -> float:
    return math.atanh(x)


def acosh_of(x: float) -> float:
    return math.acosh(x)


def log1p_of(x: float) -> float:
    return math.log1p(x)


def fmod_by(x: float) -> float:
    return math.fmod(1.0, x)


def remainder_by(x: float) -> float:
    return math.remainder(1.0, x)


def pow_half(x: float) -> float:
    return math.pow(x, 0.5)


def pow_reciprocal(x: float) -> float:
    return math.pow(x, -1)


def square_root_power(x: float) -> float:
    return x ** 0.5


def cube_root_power(x: float) -> float:
    return x ** (1 / 3)


def divmod_quotient(x: float) -> float:
    return divmod(1.0, x)[0]


def log_base(x: float) -> float:
    return math.log(2.0, x)


def zero_divisor(x: float) -> float:
    return x / (x - x)


def power_of(x: float, y: float) -> float:
    return x ** y


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (gamma_of, "for x in [-2, 2], f(x) == gamma(x)"),
    (gamma_of, "for x in [-0.5, 0.5], f(x) * x == gamma(x + 1)"),
    (lgamma_of, "for x in [-1.5, -0.5], f(x) == f(x)"),
    (inverse_square, "for x in [-2, 2], f(x) >= 0"),
    (inverse_square, "for x in [-2, 2], f(x) * x**2 == 1"),
    (reciprocal_power, "for x in [-2, 2], f(x) == -f(-x)"),
    (reciprocal_power, "for x in [0, 2], f(x) >= 0"),
    (factorial_of, "for x in [0, 3], f(x) == gamma(x + 1)"),
    (power_of, "for x in [0, 2], y in [-1, 1], f(x, y) >= 0"),
])
def test_a_value_claim_over_a_point_that_raises_is_falsified(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert p.counterexample


@pytest.mark.needs_full_proof_budget
def test_a_value_claim_over_a_pole_of_tan_is_not_proven():
    # the float call never raises next to pi/2, so the pole is a gap in
    # the mathematics that execution cannot exhibit
    (p,) = check_conjectures(tangent, [
        claim("for x in [-2, 2], f(x) == -f(-x)", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (gamma_of, "for x in [0.5, 2], f(x) == gamma(x)"),
    (gamma_of, "for x in [-0.75, -0.25], f(x) == gamma(x)"),
    (inverse_square, "for x in [1, 2], f(x) * x**2 == 1"),
    (tangent, "for x in [-1, 1], f(x) == -f(-x)"),
    (power_of, "for x in [1, 2], y in [-1, 1], f(x, y) > 0"),
])
def test_the_same_claim_away_from_those_points_is_still_proven(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn", [
    gamma_of, lgamma_of, inverse_square, reciprocal_power, factorial_of,
    atanh_of, acosh_of, log1p_of, fmod_by, remainder_by, pow_half,
    pow_reciprocal, square_root_power, cube_root_power, divmod_quotient,
    log_base, zero_divisor,
])
def test_bare_is_defined_is_falsified_at_an_executed_point(fn):
    (p,) = check_conjectures(fn, [
        claim("for x in [-2, 2], is_defined(f)", route="derive")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.sketch)
    found = re.search(r"\bx\s*=\s*([-+0-9.e]+)", p.counterexample or "")
    assert found, p.counterexample
    point = float(found.group(1))
    try:
        value = fn(point)
    except Exception:
        return
    assert isinstance(value, complex) or not math.isfinite(value)
