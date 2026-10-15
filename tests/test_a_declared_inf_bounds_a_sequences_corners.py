# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`let |inf| be B` bounds the computation along every unbounded
direction, a sequence's elements included: the computation line's
magnitude corners for a list (the cancelling pairs, the range's ends)
run to B and no further, as a scalar's corners do. A declared finite
end is the claim's own and stays."""
from mathema.analysis import analyze_source
from mathema.conjecture import claim
from mathema.gates import _point_evaluator
from mathema.records import operational_range


def running_total(xs: list, y0: float) -> float:
    total = y0
    for v in xs:
        total = v + total
    return total


def _largest_corner(statement: str) -> float:
    cj = claim(statement)
    deps = _point_evaluator(cj, running_total, analyze_source(running_total),
                            cj.domain or {}, {}, cap=operational_range(cj),
                            sequences=True)
    return max(abs(v) for corner in deps["corners"]
               for value in corner.values()
               for v in (value if isinstance(value, list) else [value]))


def test_an_unbound_list_meets_its_corners_inside_the_declared_inf():
    assert _largest_corner("let |inf| be 1e21, f(xs, y0) == f(xs, 0) + y0") \
        <= 1e21


def test_a_list_over_the_whole_line_meets_its_corners_inside_it():
    assert _largest_corner("let |inf| be 1e21, for xs in R^n, y0 in R, "
                           "f(xs, y0) == f(xs, 0) + y0") <= 1e21


def test_a_declared_finite_end_is_kept():
    assert _largest_corner("let |inf| be 1e21, for xs in [-1e30, 1e30]^n, "
                           "y0 in [-1, 1], f(xs, y0) == f(xs, 0) + y0") == 1e30


def test_without_a_declared_inf_the_corners_reach_the_largest_double():
    import sys
    assert _largest_corner("f(xs, y0) == f(xs, 0) + y0") \
        == sys.float_info.max


def _admits(statement: str, point: dict) -> bool:
    cj = claim(statement)
    deps = _point_evaluator(cj, running_total, analyze_source(running_total),
                            cj.domain or {}, {}, cap=operational_range(cj),
                            sequences=True)
    return deps["admits"](point)


def test_a_draw_past_the_declared_inf_is_not_executed():
    point = {"xs": [1e300, -1e300, 2.0], "y0": 1.0}
    assert not _admits("let |inf| be 1e21, f(xs, y0) == f(xs, 0) + y0", point)
    assert _admits("let |inf| be 1e21, f(xs, y0) == f(xs, 0) + y0",
                   {"xs": [1e21, -1e21, 2.0], "y0": 1.0})
    assert _admits("f(xs, y0) == f(xs, 0) + y0", point)
    # a declared finite end is the claim's own
    assert _admits("let |inf| be 1e21, for xs in [-1e300, 1e300]^n, "
                   "f(xs, y0) == f(xs, 0) + y0", point)
