# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exhaustive sweep that cannot decide a point exactly is proven
within_float64 only when, at every such point, the float64 computation
satisfies the relation to within float64's own precision there: a miss
of at most 2^10 unit roundoffs (u = 2^-53) relative to the value
compared against (the inputs' largest magnitude when that value is 0),
the conditioning bound at a condition number of 1. A larger miss inside
the allowance's absolute floor is evidence, `holds` on
`derive:brute_force`, never a proof; a miss that only the relative part
of the allowance admits, at a point with no exact reading, is not
counted, and such a sweep decides nothing (`unknown`), as on the probe
route; a miss past the allowance falsifies as before. The same holds for a ground claim at its own call.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
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
def test_a_miss_beyond_float64_precision_holds_and_is_not_proven(fn, law):
    p = _check(fn, law)
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
    p = _check(offset_global, "for n in {1, 2, 3}, f(n) == n")
    # 1 + 5e-10 misses 1 by 5e-10 in float64; 2^10 * 2^-53 * 1 = 1.1e-13
    assert "at n = 1 the float64 computation misses the relation by 5e-10" \
        in p.sketch, p.sketch
    assert "beyond float64's precision there (1.1e-13)" in p.sketch, p.sketch
