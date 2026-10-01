# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A strict polynomial inequality over a closed interval fails wherever
the polynomial reaches the bound, endpoints included. Exact root
isolation must check the strict sign and the roots, never prove
`p > c` from the sign of `p - c` being negative, nor `p < 0` while
`p` vanishes inside the interval."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic._extensive import _sturm_decide


def hump(x: float) -> float:
    return x - x * x


def negated_square(x: float) -> float:
    return -(x ** 3 - 3 * x + 1) ** 2


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law)], extensive=True)
    return p


@pytest.mark.needs_full_proof_budget
def test_a_strict_lower_bound_above_the_maximum_is_not_proven():
    # x - x^2 is at most 1/4 on [0.2, 0.8], so `> 0.3` is false
    # everywhere.
    p = _one(hump, "for x in [0.2, 0.8], f(x) > 0.3")
    assert p.verdict != "proven"
    q = _one(hump, "for x in [0.2, 0.8], 0.3 < f(x)")
    assert q.verdict != "proven"


@pytest.mark.needs_full_proof_budget
def test_a_strict_upper_bound_above_the_maximum_is_still_proven():
    p = _one(hump, "for x in [0.2, 0.8], f(x) < 0.3")
    assert p.verdict == "proven"


@pytest.mark.needs_full_proof_budget
def test_a_strict_sign_fails_at_a_root_inside_the_interval():
    # x^3 - 3x + 1 has a real root near 0.347 in [0, 1], where the
    # negated square is zero, not negative.
    p = _one(negated_square, "for x in [0, 1], f(x) < 0")
    assert p.verdict != "proven"
    assert _one(negated_square, "for x in [0, 1], f(x) <= 0").verdict == "proven"


def test_root_isolation_decides_strict_relations_by_sign_and_roots():
    x = sympy.Symbol("x", real=True)
    dom = {"x": Interval(0.2, 0.8, True, True)}
    diff = x - x ** 2 - sympy.Rational(3, 10)
    gt = _sturm_decide(diff, ">", dom, {"x": x})
    assert gt is None or gt.status == "disproven"
    lt = _sturm_decide(diff, "<", dom, {"x": x})
    assert lt is not None and lt.status == "proven"
    sq = -(x ** 3 - 3 * x + 1) ** 2
    root_dom = {"x": Interval(0.0, 1.0, True, True)}
    strict = _sturm_decide(sq, "<", root_dom, {"x": x})
    assert strict is None or strict.status == "disproven"
    assert _sturm_decide(sq, "<=", root_dom, {"x": x}).status == "proven"


def test_a_root_at_a_closed_endpoint_breaks_a_strict_relation():
    x = sympy.Symbol("x", real=True)
    # x on [0, 1] is zero at the closed endpoint 0, so `x > 0` fails
    # there; on (0, 1] it holds.
    closed = _sturm_decide(x, ">", {"x": Interval(0.0, 1.0, True, True)}, {"x": x})
    assert closed is None or closed.status == "disproven"
    if closed is not None:
        assert closed.witness == {"x": 0}
