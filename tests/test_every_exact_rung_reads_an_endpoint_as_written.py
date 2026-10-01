# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every exact step of a proof reads a domain endpoint as the number
written: `0.3` is 3/10, never the double just below it, and never a
nearby closed form (`0.3333333334` is not 1/3, `1.4142135624` is not
sqrt 2). A root is compared with an endpoint exactly, and a tiny
nonzero value keeps its sign."""
import math

import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic._proof_support import _exact, _verified_sign


def ident(x: float) -> float:
    return x


def lin(x: float, y: float) -> float:
    return x + y


def pole(x: float) -> float:
    return (x * x - 2) / (x * x - 2)


def g(x: float) -> float:
    return x * (x - 1 / 3)


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.parametrize("fn, law", [
    (ident, "for x in [0, 0.3], f(x) <= 0.3 - 10**-20"),
    (lin, "for x in [0, 0.3], y in [0, 0.3], f(x, y) <= 0.6 - 10**-20"),
    (ident, "for x in [0, 0.3], f(x) == min(x, 0.3 - 10**-20)"),
    (pole, "for x in [0, 1.4142135623730951), f(x) == 1"),
    (g, "for x in [0, 0.3333333334], f(x) <= 0"),
])
def test_a_claim_false_at_the_written_endpoint_is_not_proven(fn, law):
    assert _one(fn, law).verdict != "proven"


def test_an_endpoint_is_never_snapped_to_a_nearby_closed_form():
    assert _exact(0.3333333334) == sympy.Rational("0.3333333334")
    assert _exact(1.4142135624) == sympy.Rational("1.4142135624")
    assert _exact(0.3) == sympy.Rational(3, 10)


def test_a_value_below_the_double_range_keeps_its_sign():
    tiny = sympy.Integer(10) ** -400
    assert _verified_sign(sympy.log(1 + tiny) - tiny) in (-1, None)
    assert _verified_sign(sympy.exp(tiny) - 1 - tiny) in (1, None)
    assert _verified_sign(sympy.cos(tiny) - 1) in (-1, None)


def test_a_root_equal_to_an_open_endpoint_as_a_double_is_outside():
    from mathema.domain import exact_membership
    hi = 1.4142135623730951
    assert math.sqrt(2) == hi
    assert exact_membership(sympy.sqrt(2), Interval(0.0, hi, True, False)) is True
    assert exact_membership(sympy.sqrt(2), Interval(0.0, 1.414213562373095, True, True)) is False


def test_a_claim_short_by_a_value_below_the_double_range_is_not_proven():
    # log(1 + 10**-400) - 10**-400 is about -5e-801, so the claim fails
    # at x = 0
    p = _one(ident, "for x in [0, 1], f(x) + log(1 + 10**-400) - 10**-400 >= 0")
    assert p.verdict != "proven"
