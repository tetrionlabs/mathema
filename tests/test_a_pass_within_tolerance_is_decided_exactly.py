# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A draw that passes only within the tolerance (its absolute floor,
the relative part, or an array draw's round-off) is decided in exact
arithmetic at that point:
false there falsifies, true there holds with the gap printed, and a
draw that cannot be evaluated exactly is inconclusive and not counted
(ruling of 2026-10-01: the mathematics is exact, tolerance belongs to
the computation; option O1 of the tolerance review)."""
import math

from mathema.conjecture import check_conjectures, claim


def nudged(x: float) -> float:
    return x + x / 10**9


def tenths(x: float) -> float:
    return sum([x / 10] * 10)


def round_trip(x: float) -> float:
    return math.exp(math.log(x))


#: a float the body reads from outside, which has no exact reading
_ONE = 1.0


def round_trip_by_global(x: float) -> float:
    return math.exp(math.log(x) * _ONE)


def test_a_relative_pass_false_in_exact_arithmetic_falsifies():
    (p,) = check_conjectures(nudged, [claim(
        "for x in [1000, 1000000], f(x) == x", route="probe")])
    assert p.verdict == "falsified"
    assert "false here in exact arithmetic" in p.counterexample


def test_a_relative_pass_true_in_exact_arithmetic_holds_with_its_gap():
    (p,) = check_conjectures(tenths, [claim(
        "for x in [1e8, 1e9], f(x) == x", route="probe")])
    assert p.verdict == "holds", p.counterexample
    assert "holds there in exact arithmetic" in p.note


def test_a_relative_pass_that_cannot_be_evaluated_exactly_is_not_counted():
    (p,) = check_conjectures(round_trip_by_global, [claim(
        "for x in [1e8, 1e9], f(x) == x", route="probe")])
    assert p.verdict != "falsified"
    assert "could not be evaluated in exact arithmetic" in p.note


def test_a_relative_pass_of_a_round_trip_holds_in_exact_arithmetic():
    # read exactly, exp(log(x)) is x
    (p,) = check_conjectures(round_trip, [claim(
        "for x in [1e8, 1e9], f(x) == x", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "holds there in exact arithmetic" in p.note, p.note


def a_hair_over_one(x: float) -> float:
    return min(1.0, x) + 1e-12


def test_a_chained_link_passing_within_the_floor_is_decided_exactly():
    # the upper link passes in float64 only within the tolerance's
    # absolute floor (1e-12 over 1); exactly f(2) = 1 + 1/10**12 > 1
    (p,) = check_conjectures(a_hair_over_one, [claim(
        "for x in [0.5, 2], 0 <= f(x) <= 1", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "link 2: f(x) <= 1" in p.counterexample, p.counterexample
    assert "false here in exact arithmetic" in p.counterexample, \
        p.counterexample


def one_by_rounding(x: float) -> float:
    # (0.1 + 0.2) / 0.3 is 1.0000000000000002 in float64 and exactly 1
    return min(1.0, x) * (0.1 + 0.2) / 0.3


def test_a_chained_claim_keeps_the_gap_its_link_passed_within():
    # the upper link passes only within the tolerance and holds exactly;
    # the chain says so
    (p,) = check_conjectures(one_by_rounding, [claim(
        "for x in [0.5, 2], 0 <= f(x) <= 1", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "fails by 2.22e-16 at x = " in p.note, p.note
    assert "within the default tolerance (1.01e-07)" in p.note, p.note
