# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A square root's base is nonnegative only on the branch that
evaluates it. A function that takes `sqrt(x - y)` when `x - y >= 0`
and `x - y` otherwise is negative at `(-1, 1)`, so `f >= 0` must not
be proven by treating `x - y >= 0` as true everywhere."""
import math

import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic import _smt


def root_or_gap(x: float, y: float) -> float:
    if x - y >= 0:
        return math.sqrt(x - y)
    return x - y


def root_or_reversed_gap(x: float, y: float) -> float:
    if x - y >= 0:
        return math.sqrt(x - y)
    return y - x


pytestmark = pytest.mark.skipif(not _smt.available(),
                                reason="needs the optional z3 dependency")


def test_the_other_branch_of_a_square_root_is_still_checked():
    (p,) = check_conjectures(
        root_or_gap, [claim("for x in [-1, 1], y in [-1, 1], f(x, y) >= 0")],
        extensive=True)
    assert p.verdict == "falsified"
    assert p.counterexample == "x=-0.5, y=0"
    assert root_or_gap(-1.0, 1.0) == -2.0


@pytest.mark.needs_full_proof_budget
def test_a_branch_safe_square_root_claim_is_still_proven():
    (p,) = check_conjectures(
        root_or_reversed_gap,
        [claim("for x in [-1, 1], y in [-1, 1], f(x, y) >= 0")],
        extensive=True)
    assert p.verdict == "proven"


def test_the_solver_finds_the_point_on_the_branch_without_the_root():
    x, y = sympy.symbols("x y", real=True)
    gap = x - y
    expr = sympy.Piecewise((sympy.sqrt(gap), gap >= 0), (gap, True))
    box = {"x": Interval(-1.0, 1.0, True, True),
           "y": Interval(-1.0, 1.0, True, True)}
    result = _smt.nlsat_decide(expr, ">=", box, {"x": x, "y": y})
    assert result.status == "disproven"
    assert result.counterexample == "x = -1/2, y = 0"
