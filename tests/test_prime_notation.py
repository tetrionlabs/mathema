# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Prime notation (`f'(x)`) differentiates with respect to the call's
single free variable. A primed call with no single free variable to
infer is refused by `claim()` with an `InvalidConjecture` naming the
explicit `d(...)` spelling, never a raw Python `SyntaxError`."""
import math

import pytest

from mathema import check_conjectures, claim
from mathema.conjecture import InvalidConjecture


def cube(x: float) -> float:
    return x ** 3


def projectile_range(v0: float, theta: float, g: float) -> float:
    return v0 ** 2 * math.sin(2 * theta) / g


def test_single_parameter_prime_claim_still_adjudicates():
    (p,) = check_conjectures(cube, [claim("f'(x) at {x=1} == 3")])
    assert p.verdict in ("proven", "holds")


def test_prime_on_a_multi_parameter_call_is_a_named_claim_error():
    with pytest.raises(InvalidConjecture) as info:
        claim("f'(v0, theta, g) at {theta=pi/4} == 0")
    message = str(info.value)
    assert "f'(v0, theta, g)" in message
    assert "d(f(v0, theta, g), <var>)" in message


def test_prime_on_a_literal_argument_is_a_named_claim_error():
    with pytest.raises(InvalidConjecture) as info:
        claim("f'(3) == 27")
    assert "d(f(3), <var>)" in str(info.value)


def test_second_order_prime_on_a_multi_parameter_call_names_the_order():
    with pytest.raises(InvalidConjecture) as info:
        claim("f''(x, y) == 0")
    assert "d(f(x, y), <var>, <var>)" in str(info.value)


def test_explicit_derivative_spelling_of_the_same_claim_parses():
    (p,) = check_conjectures(projectile_range, [
        claim("d(f(v0, theta, g), theta)@{theta=pi/4} == 0")])
    assert p.statement
