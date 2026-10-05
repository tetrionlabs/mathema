# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`f =:= g`'s executed rung reads a value the way every executed path
does (P4): two sides at the same infinity are one extended-real point
and agree; a NaN from non-missing inputs is no value and agrees with
nothing, another NaN included; an infinity against a value, and
opposite infinities, disagree. A missing input is not compared."""
from mathema.conjecture import check_conjectures, claim


def huge(x: float) -> float:
    return sorted([x * 1e300 * 1e300])[0]


def huge_again(x: float) -> float:
    return max([x * 1e300 * 1e300])


def huge_negated(x: float) -> float:
    return min([-x * 1e300 * 1e300])


def plain(x: float) -> float:
    return min([x])


def cancelled(x: float) -> float:
    y = x * 1e300 * 1e300
    return sorted([y - y])[0]


def cancelled_again(x: float) -> float:
    y = x * 1e300 * 1e300
    return max([y - y])


def first(x: float) -> float:
    return sorted([x])[0]


def largest(x: float) -> float:
    return max([x])


def _eq(f, g, domain):
    (p,) = check_conjectures(f, [claim(f"for {domain}, f =:= g",
                                       funcs={"g": g})])
    return p


def test_the_same_infinity_on_both_sides_agrees():
    p = _eq(huge, huge_again, "x in [1, 2]")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.meta["mathema.equivalence.sampling"]["checked"] > 0


def test_opposite_infinities_disagree():
    p = _eq(huge, huge_negated, "x in [1, 2]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "inf vs -inf" in p.counterexample, p.counterexample


def test_an_infinity_against_a_value_disagrees():
    p = _eq(huge, plain, "x in [1, 2]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "inf vs " in p.counterexample, p.counterexample


def test_a_nan_from_values_agrees_with_nothing_not_even_a_nan():
    p = _eq(cancelled, cancelled_again, "x in [1, 2]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "nan vs nan" in p.counterexample, p.counterexample


def test_a_missing_input_is_still_not_compared():
    p = _eq(first, largest, "x in {nan, 1}")
    assert p.verdict == "holds", (p.verdict, p.note)


def nan_a(x: float) -> float:
    return float("nan")


def nan_b(x: float) -> float:
    import math
    return math.nan


def test_a_nan_agrees_with_nothing_whatever_its_spelling_or_object():
    # an all-nan function has no value at any point, so no rung proves it
    # equivalent to anything, itself included: the same body and another
    # spelling of nan get the same verdict, with an executed witness
    same = _eq(nan_a, nan_a, "x in [0, 1]")
    other = _eq(nan_a, nan_b, "x in [0, 1]")
    assert same.verdict == other.verdict == "falsified", (
        same.verdict, same.note, other.verdict)
    assert "nan vs nan" in same.counterexample, same.counterexample
