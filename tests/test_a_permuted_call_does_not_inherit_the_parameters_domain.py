# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A call that passes a parameter in another parameter's position does
not carry the first position's domain. With x in [0, 1] and y in
[-1, 0], `f(y, x)` evaluates f's first argument at a negative number,
so `abs(x)` there is -y, not y."""
from mathema.conjecture import check_conjectures, claim


def h(x: float, y: float) -> float:
    return abs(x) + y


def first(a: float, b: float) -> float:
    return abs(a)


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_a_swapped_call_is_not_proven_symmetric():
    # h(0.5, -0.5) = 0 and h(-0.5, 0.5) = 1
    p = _one(h, "for x in [0, 1], y in [-1, 0], f(x, y) == f(y, x)")
    assert p.verdict != "proven"


def test_a_swapped_call_is_not_proven_negative():
    p = _one(first, "for a in [0, 1], b in [-1, -0.5], f(b, a) < 0")
    assert p.verdict != "proven"
    q = _one(first, "for a in [0, 1], b in [-1, -0.5], f(b, a) == b")
    assert q.verdict != "proven"


def test_the_same_call_in_its_own_order_still_proves():
    assert _one(first, "for a in [0, 1], b in [-1, -0.5], f(a, b) == a").verdict == "proven"
