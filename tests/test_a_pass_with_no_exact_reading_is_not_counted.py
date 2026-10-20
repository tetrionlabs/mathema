# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A draw the computed values satisfy only within the default allowance,
for any relation and inside the allowance's absolute floor as well as
beyond it, is decided in exact arithmetic; where the body cannot be read
exactly (a float it reads from outside, a module constant) such a pass
is no evidence either way, so it is not counted, and a claim with no
other draw ends `unknown` with the reason. A declared tolerance makes
the pass count: the author asked for that allowance. An exhaustive
sweep follows the same rule at a point with no exact value whose
float64 miss is beyond float64's precision there."""
from mathema.conjecture import check_conjectures, claim

#: floats a body reads from outside: no exact reading
GAP = 1e-10
HAIR = 1e-12
OFFSET = 5e-10

_REASON = ("passed only within the tolerance and could not be evaluated in "
           "exact arithmetic, so they are not counted")


def above_by_global(x: float) -> float:
    return x + GAP


def off_by_a_hair(x: float) -> float:
    return x + HAIR


def offset_global(n: int) -> float:
    i = 0
    while i < 3:
        i += 1
    return n + OFFSET


def _v(fn, law, route="probe", **kw):
    (p,) = check_conjectures(fn, [claim(law, route=route, **kw)])
    return p


def test_an_ordering_pass_with_no_exact_reading_is_not_counted():
    # float64 x + 1e-10 exceeds x at every draw, inside the allowance
    p = _v(above_by_global, "for x in [1, 2], f(x) <= x")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert _REASON in p.note, p.note


def test_a_pass_inside_the_floor_with_no_exact_reading_is_not_counted():
    # float64 x + 1e-12 differs from x by about 1e-12, inside 1e-9
    p = _v(off_by_a_hair, "for x in [1, 2], f(x) == x")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert _REASON in p.note, p.note


def test_a_declared_tolerance_makes_such_a_pass_count():
    p = _v(above_by_global, "for x in [1, 2], f(x) <= x", tolerance=1e-9)
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_sweep_point_beyond_float64_precision_with_no_exact_value_is_not_counted():
    # f(0) is 5e-10 against 0, beyond float64's precision at 0, inside
    # the allowance's floor, and OFFSET has no exact reading
    p = _v(offset_global, "for n in {0, 1, 2, 3}, f(n) == n", route="best")
    assert p.verdict == "unknown", (p.verdict, p.route, p.note)
