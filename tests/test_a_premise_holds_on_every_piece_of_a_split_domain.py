# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive proves a branched function piece by piece, splitting the
domain at the guard's boundaries. The claim's premise holds on every
piece as it does on the whole domain: `assuming is_defined(f)` leaves
out the points where f raises, and an ordinary premise (`assuming x >=
5`) leaves out the points it rules out, so a piece where f raises, or a
point the premise excludes, is never a counterexample. Derive and the
probe then agree."""
import sys

import pytest

from mathema.conjecture import check_conjectures, claim


def guarded(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x + 1


def exits_below(x: float) -> float:
    if x < 0:
        sys.exit(2)
    return x + 1


def two_guards(x: float) -> float:
    if x < -3:
        raise ValueError("low")
    if x > 3:
        raise ValueError("high")
    return x


def two_guards_and_y(x: float, y: float) -> float:
    if x < -3:
        raise ValueError("low")
    if x > 3:
        raise ValueError("high")
    return x + y


def abs_split(x: float) -> float:
    if x < 2:
        return 2 - x
    return x - 2


def _x(p) -> float:
    from fractions import Fraction
    return float(Fraction(p.counterexample.split("x = ", 1)[1]
                          .split(":")[0].split(",")[0].split()[0]))


def _row(fn, text, route):
    return check_conjectures(fn, [claim(text, route=route)])[0]


@pytest.mark.parametrize("fn", [guarded, exits_below],
                         ids=lambda f: f.__name__)
@pytest.mark.parametrize("text", [
    "assuming is_defined(f), for x in [-10, 10], f(x) >= 1",
    "assuming is_defined(f), for x in [-10, 10], f(x) >= 0",
])
def test_the_definedness_premise_leaves_out_the_raising_piece(fn, text):
    derived = _row(fn, text, "derive")
    probed = _row(fn, text, "probe")
    assert derived.verdict == "proven", (derived.verdict, derived.sketch)
    assert probed.verdict == "holds", (probed.verdict, probed.counterexample)


def test_an_ordinary_premise_holds_on_every_piece():
    p = _row(guarded, "assuming x >= 5, for x in [-10, 10], f(x) >= 6",
             "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_without_the_premise_the_raising_piece_still_falsifies():
    p = _row(guarded, "for x in [-10, 10], f(x) >= 1", "derive")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "raises ValueError" in p.sketch


def test_a_premise_does_not_hide_a_point_it_admits():
    p = _row(guarded, "assuming is_defined(f), for x in [-10, 10], f(x) >= 2",
             "derive")
    assert p.verdict == "falsified", (p.verdict, p.sketch)


@pytest.mark.parametrize("route", ["best", "derive"])
def test_a_witness_lies_inside_the_definedness_premise(route):
    p = _row(two_guards,
             "assuming is_defined(f), for x in [-10, 10], f(x) <= 2", route)
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert 2 < _x(p) <= 3, p.counterexample


# on best each piece is proven under the premise x * x >= 9 by the
# extensive ladder's nlsat rung, which needs z3 (mathema[smt])
@pytest.mark.parametrize("route", [pytest.param("best", marks=pytest.mark.needs_smt),
                                   "derive"])
def test_a_piece_a_nonlinear_premise_rules_out_is_left_out(route):
    # x * x >= 9 admits x <= -3 and x >= 3; the split's piece x = 2 is
    # outside it, where f(2) = 0
    p = _row(abs_split, "assuming x * x >= 9, for x in [-10, 10], f(x) >= 1",
             route)
    if route == "best":
        assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    else:
        # the fast attempt does not split this claim; derive leaves it
        # open, never false
        assert p.verdict in ("proven", "unknown"), (p.verdict, p.sketch, p.note)
    assert "bug" not in (p.note or ""), p.note
    q = _row(abs_split, "assuming x * x >= 9, for x in [0, 10], f(x) >= 2",
             route)
    assert q.verdict == "falsified", (q.verdict, q.sketch)
    assert _x(q) ** 2 >= 9 and _x(q) - 2 < 2, q.counterexample
    assert "[2.0, 2.0]" not in (q.sketch or ""), q.sketch


@pytest.mark.xfail(strict=True, reason=(
    "[derive-gap] the fast derive attempt lacks the piecewise split under "
    "a nonlinear premise: each piece (x <= -3, x >= 3) needs the extensive "
    "rungs, which only route best runs"))
def test_a_nonlinear_premise_split_is_proven_on_derive():
    # |x - 2| >= 1 wherever x * x >= 9: x <= -3 gives |x - 2| >= 5, and
    # x >= 3 gives |x - 2| = x - 2 >= 1
    p = _row(abs_split, "assuming x * x >= 9, for x in [-10, 10], f(x) >= 1",
             "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


def test_a_two_parameter_witness_lies_inside_the_definedness_premise():
    import re
    p = _row(two_guards_and_y,
             "assuming is_defined(f), for x in [-10, 10], for y in [-1, 1], "
             "f(x, y) <= 3", "best")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    x = float(re.search(r"x = ([-0-9.e/]+)", p.counterexample).group(1))
    y = float(re.search(r"y = ([-0-9.e/]+)", p.counterexample).group(1))
    assert -3 <= x <= 3 and x + y > 3, p.counterexample
