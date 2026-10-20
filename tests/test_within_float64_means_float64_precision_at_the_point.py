# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exhaustive sweep that cannot decide a point exactly is proven
within_float64 only when, at every such point, the float64 computation
satisfies the relation to within float64's own precision there: a miss
of at most 8 unit roundoffs (u = 2^-53) of the value compared against,
plus the function's relative condition number times the magnitude of
the value it returned at the point, where both can be read: a relative
input error u moves the result by about kappa u relative to the result,
so near a root the spread shrinks with the result. Where they cannot be
read, nothing is added, so a body that never computes with a large
input gets no credit for it. A larger miss rests on the default allowance alone and,
at a point with no exact reading, is not counted, so such a sweep
decides nothing (`unknown`), as on the probe route; inside a declared
tolerance it is evidence, `holds` on `derive:brute_force`, never a
proof; a miss past the allowance falsifies as before. The same holds for a ground claim at its own call.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim

#: floats a body reads from outside: no exact reading
NUDGE = 2e-9
OFFSET = 5e-10
TENTH = 0.1
HALF = 0.5


def _spin():
    i = 0
    while i < 3:
        i += 1


def drift_global(x: float) -> float:
    _spin()
    return x + NUDGE


def offset_global(n: int) -> float:
    _spin()
    return n + OFFSET


def constant_global(xs: list) -> float:
    _spin()
    return OFFSET


def one_and_a_nudge(xs: list) -> float:
    _spin()
    return 1 + NUDGE


def tiny_global(x: float) -> float:
    # never computes with x
    _spin()
    return OFFSET


def minus_tiny_global(x: float) -> float:
    _spin()
    return -OFFSET


def below_global(x: float) -> float:
    _spin()
    return x - NUDGE


def tenth_cancelled(x: float) -> float:
    _spin()
    return (x + TENTH) - x - TENTH


def near_a_root(x: float) -> float:
    # exp(10) - exp(10) cancels to 0; the 5e-10 is the miss
    return math.exp(x) - math.exp(10.0) + 5e-10


#: an opaque function the claim binds: a table of values
_TABLE = {10: 0.0}


def tabled(x):
    return _TABLE.get(int(x), 0.0)


def tenths_global(x: float) -> float:
    # 3 * 0.1 * 10 is 3.0000000000000004 in float64: one rounding off
    _spin()
    return x * TENTH * 10


def halved_global(x: float) -> float:
    _spin()
    return x * HALF


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    # f(1) is 1.000000002 in float64: a relative miss of 2e-9, past the
    # allowance's absolute 1e-9
    (drift_global, "for x in {1, 2}, f(x) == x"),
    # |f(1) - 1| is 2e-9 in float64, past ε = 1e-9
    (drift_global, "for x in {1, 2}, f(x) ~= x"),
])
def test_a_miss_only_the_relative_allowance_admits_is_not_counted(fn, law):
    p = _check(fn, law)
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)
    assert "could not be evaluated in exact arithmetic" in (p.note or ""), \
        p.note


def test_a_ground_call_passing_only_the_relative_allowance_is_not_counted():
    # the call gives 1.000000002 in float64 against 1: past the absolute
    # 1e-9, inside only the relative part, and no exact reading
    p = _check(one_and_a_nudge, "f([]) == 1")
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.parametrize("fn,law", [
    # f(0) is 5e-10 in float64 against 0, at inputs of magnitude 0
    (offset_global, "for n in {0, 1, 2, 3}, f(n) == n"),
    (constant_global, "f([]) == 0"),
])
def test_a_miss_beyond_float64_precision_is_not_counted(fn, law):
    p = _check(fn, law)
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.parametrize("fn,law", [
    (offset_global, "for n in {0, 1, 2, 3}, f(n) == n"),
    (constant_global, "f([]) == 0"),
])
def test_a_miss_beyond_float64_inside_a_declared_tolerance_holds(fn, law):
    (p,) = check_conjectures(fn, [claim(law, tolerance=1e-9)])
    assert p.verdict == "holds", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.sweep_inexact" in p.meta, p.meta
    assert "beyond float64's precision" in p.sketch, p.sketch


@pytest.mark.parametrize("fn,law", [
    (tenths_global, "for x in {1, 3, 7}, f(x) == x"),
    (halved_global, "for x in {1, 3, 7}, f(x) == x / 2"),
    # |f(n) - n| is 5e-10 in float64, inside ε = 1e-9
    (offset_global, "for n in {0, 1, 2, 3}, f(n) ~= n"),
])
def test_a_miss_within_float64_precision_is_proven_within_float64(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert "within float64's precision" in p.sketch, p.sketch


def test_the_sketch_names_the_point_and_its_precision():
    (p,) = check_conjectures(offset_global, [claim(
        "for n in {1, 2, 3}, f(n) == n", tolerance=1e-9)])
    # 1 + 5e-10 misses 1 by 5e-10 in float64; 8 * 2^-53 * 1 = 8.9e-16
    assert "at n = 1 the float64 computation misses the relation by 5e-10" \
        in p.sketch, p.sketch
    assert ("beyond float64's precision there (8.9e-16, 8 unit roundoffs "
            "of 1)") in p.sketch, p.sketch


@pytest.mark.parametrize("fn,law", [
    # 5e-10 against 0: the body never computes with x = 10^6, so the
    # input's magnitude lends no precision; float64's precision at a
    # value of 0 is 0
    (tiny_global, "for x in {1000000}, f(x) == 0"),
    (minus_tiny_global, "for x in {1000000}, f(x) >= 0"),
    # 10^6 - 2e-9 misses x by 2e-9, about 17 units in the last place of
    # 10^6, past 8 unit roundoffs of 10^6 (8.9e-10)
    (below_global, "for x in {1000000}, f(x) >= x"),
    # (10^6 + 0.1) - 10^6 - 0.1 is 2.3e-11 in float64 against 0, and the
    # condition number that would credit the inputs' magnitude cannot
    # be read from this body
    (tenth_cancelled, "for x in {1000000}, f(x) == 0"),
])
def test_a_miss_the_values_compared_do_not_explain_is_not_proven(fn, law):
    # beyond float64's precision, inside only the default allowance, no
    # exact reading: not counted
    p = _check(fn, law)
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.parametrize("law", ["for x in {10}, f(x) == g(x)",
                                 "for x in {10}, f(x) <= g(x)"])
def test_a_condition_number_scales_the_value_not_the_inputs(law):
    # near the root the relative condition number is about 4e14, but
    # float64's precision there is 8 u * |f(10)| * (1 + kappa), about
    # 1.8e-11 for |f(10)| = 5e-10, far below the 5e-10 miss: no proof
    (p,) = check_conjectures(near_a_root, [claim(law, funcs={"g": tabled})])
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


def test_the_record_carries_float64_precision_at_the_point():
    # tenths_global: float64 7 * 0.1 * 10 is 7.000000000000001, the
    # largest miss (8.88e-16) against 8 * 2^-53 * 7 = 6.2e-15 at x = 7
    p = _check(tenths_global, "for x in {1, 3, 7}, f(x) == x")
    precision = p.meta["mathema.sweep_precision"]["precision"]
    assert precision["factor"] == 8, precision
    assert precision["magnitude"] == 7.0, precision
    assert abs(precision["bound"] - 8 * 2.0 ** -53 * 7) < 1e-30, precision
    assert precision["kappa"] is None and precision["returned"] is None, \
        precision
