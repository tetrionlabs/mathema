# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bare tolerance declared on `<=`, `>=` or `!=` belongs to the
computation line only, as on `==`: the mathematics line decides the
relation exactly, so an exact gap smaller than the tolerance falsifies
an ordering, and two sides that differ exactly by less than it are
still different. The computation line compares the floats within the
declared tolerance."""
from mathema.conjecture import check_conjectures, claim


def just_above(x: float) -> float:
    return x + 1e-10


def just_below(x: float) -> float:
    return x - 1e-10


def swept_hair(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + 1e-12


def _v(fn, law, route, tolerance):
    (p,) = check_conjectures(fn, [claim(law, route=route,
                                        tolerance=tolerance)])
    return p


def test_an_exact_gap_inside_the_tolerance_falsifies_less_or_equal():
    # exactly f(x) - x = 1/10**10 > 0 at every x, inside 1e-9
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "best", 1e-9)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta


def test_an_exact_gap_inside_the_tolerance_falsifies_greater_or_equal():
    # exactly f(x) - x = -1/10**10 < 0 at every x
    p = _v(just_below, "for x in [0, 1], f(x) >= x", "best", 1e-9)
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_sides_differing_exactly_inside_the_tolerance_are_different():
    # in float64 f(1) - 1 is 1.000088900582341e-12, past the declared
    # 1.00005e-12, so the computation line holds; exactly f(1) - 1 is
    # 1/10**12, inside the tolerance and still not 0, so the mathematics
    # line holds too
    p = _v(swept_hair, "for x in {1}, f(x) != x", "best", 1.00005e-12)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)


def test_the_computation_line_keeps_the_declared_tolerance_on_an_ordering():
    p = _v(just_above, "for x in [1, 2], f(x) <= x", "probe", 1e-9)
    assert p.verdict == "holds", (p.verdict, p.counterexample)
