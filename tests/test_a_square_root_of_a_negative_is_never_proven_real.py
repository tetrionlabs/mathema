# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A square root the claim evaluates has no real value where its base
is negative. `0 <= (sqrt(x) - 1)^2` over `[-1, -0.5]` compares against
a number that is not real anywhere in the domain, so the solver must
not prove it by treating the root as any real it likes there."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic import _smt


def zero(x: float) -> float:
    return 0.0


pytestmark = pytest.mark.skipif(not _smt.available(),
                                reason="needs the optional z3 dependency")


@pytest.mark.parametrize("law", [
    "for x in [-1, -0.5], f(x) <= (sqrt(x) - 1)^2",
    "for x in [-1, 1], f(x) <= (sqrt(x) - 1)^2",
])
def test_a_claim_side_root_of_a_negative_base_is_falsified(law):
    (p,) = check_conjectures(zero, [claim(law)], extensive=True)
    assert p.verdict == "falsified"
    head, detail = p.counterexample.split(":", 1)
    assert float(head.strip("()").split("=")[-1]) < 0
    assert "the claim's own side has no real value here (sqrt(" in detail


def test_the_solver_does_not_prove_over_an_undefined_root():
    x = sympy.Symbol("x", real=True)
    box = {"x": Interval(-1.0, -0.5, True, True)}
    result = _smt.nlsat_decide((sympy.sqrt(x) - 1) ** 2, ">=", box, {"x": x})
    assert result is None or result.status != "proven"


def test_a_cube_root_of_a_negative_base_is_not_real_either():
    x = sympy.Symbol("x", real=True)
    box = {"x": Interval(-1.0, 1.0, True, True)}
    result = _smt.nlsat_decide(x ** sympy.Rational(1, 3) - 1, "<=", box, {"x": x})
    assert result is None or result.status != "proven"


def test_a_root_only_on_the_branch_where_its_base_is_nonnegative_still_proves():
    x = sympy.Symbol("x", real=True)
    box = {"x": Interval(-1.0, 1.0, True, True)}
    expr = sympy.Piecewise((sympy.sqrt(x), x >= 0), (-x, True))
    assert _smt.nlsat_decide(expr, ">=", box, {"x": x}).status == "proven"
