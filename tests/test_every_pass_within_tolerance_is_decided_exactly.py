# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On the probe route a draw of `==`, `<=` or `>=` that the computed
sides satisfy only within the default allowance, inside its absolute
floor (1e-9) as much as through its relative part, is decided in exact
arithmetic where the sides can be read: false there falsifies with that
point as the witness, true there holds with the float gap printed."""
from mathema.conjecture import check_conjectures, claim


def a_hair_over_one(x: float) -> float:
    return min(1.0, x) + 1e-12


def a_hair_under_zero(x: float) -> float:
    return max(0.0, x) - 1e-12


def a_hair_off(x: float) -> float:
    return x + 1e-12


def one_by_rounding(x: float) -> float:
    # (0.1 + 0.2) / 0.3 is 1.0000000000000002 in float64 and exactly 1
    return min(1.0, x) * (0.1 + 0.2) / 0.3


def _probe(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


def test_an_ordering_pass_inside_the_floor_false_exactly_falsifies():
    # exactly f(x) = 1 + 1/10**12 > 1 wherever x >= 1
    p = _probe(a_hair_over_one, "for x in [0.5, 2], 0 <= f(x) <= 1")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("link 2: f(x) <= 1: x = "), \
        p.counterexample
    assert "false here in exact arithmetic" in p.counterexample, p.counterexample


def test_a_greater_or_equal_pass_inside_the_floor_false_exactly_falsifies():
    # exactly f(x) = -1/10**12 < 0 wherever x <= 0
    p = _probe(a_hair_under_zero, "for x in [-1, 1], f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "false here in exact arithmetic" in p.counterexample, p.counterexample
    (x,) = p.meta["mathema.counterexample_args"]
    assert -1 <= x <= 0


def test_an_equality_pass_inside_the_floor_false_exactly_falsifies():
    # exactly f(x) - x = 1/10**12, nonzero at every x
    p = _probe(a_hair_off, "for x in [0.5, 2], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "false here in exact arithmetic" in p.counterexample, p.counterexample


def test_an_ordering_pass_inside_the_floor_true_exactly_holds_with_its_gap():
    # the float result 1.0000000000000002 fails f(x) <= 1 by 2.22e-16,
    # and exactly f(x) = min(1, x) <= 1
    p = _probe(one_by_rounding, "for x in [0.5, 2], 0 <= f(x) <= 1")
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "fails by 2.22e-16 at x = " in p.note, p.note
    assert "within the default tolerance (1.01e-07)" in p.note, p.note
