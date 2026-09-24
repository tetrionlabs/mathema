# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `falsified` verdict carries an executed witness: a counterexample
that reproduces against the real function. A symbolic disproof nothing
can reproduce is `unknown`, flagged uncorroborated."""
import ast
import re
from math import pi, sin

import pytest

from mathema.conjecture import check_conjectures, claim


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def not_heat_sol(t, x):
    return x**2 + 3*t


def _point(text: str) -> dict:
    """The `name=value` pairs of a rendered counterexample, a list
    value kept whole."""
    return {m.group(1): ast.literal_eval(m.group(2))
            for m in re.finditer(r"(\w+)=(\[[^\]]*\]|[^,]+)", text)}


@pytest.mark.needs_full_proof_budget
def test_a_sequence_fold_disproof_records_a_witness_that_reproduces():
    [p] = check_conjectures(ema, [claim("f(x, alpha) == x[-1]",
                                        route="derive")])
    assert p.verdict == "falsified"
    assert p.counterexample
    assert (p.meta or {}).get("mathema.corroboration") == "reproduced"
    point = _point(p.counterexample)
    assert isinstance(point["x"], list)
    assert ema(point["x"], point["alpha"]) != point["x"][-1]


@pytest.mark.needs_full_proof_budget
def test_a_true_sequence_fold_claim_is_still_proven():
    [p] = check_conjectures(ema, [claim("f(x, 1.0) == x[-1]",
                                        route="derive")])
    assert p.verdict == "proven"


@pytest.mark.needs_full_proof_budget
def test_a_calculus_disproof_with_no_executable_witness_is_unknown():
    [p] = check_conjectures(not_heat_sol, [
        claim("d(f(t,x),t) == d(f(t,x),x,x)", route="derive")])
    assert p.verdict == "unknown"
    assert p.counterexample is None
    assert (p.meta or {}).get("mathema.corroboration") == "uncorroborated"
    assert "no executed witness" in p.note


@pytest.mark.needs_full_proof_budget
def test_a_true_calculus_claim_is_still_proven():
    def heat_sol(t, x):
        return x**2 + 2*t
    [p] = check_conjectures(heat_sol, [
        claim("d(f(t,x),t) == d(f(t,x),x,x)", route="derive")])
    assert p.verdict == "proven"


def projectile_range(v0, theta, g):
    return v0**2 * sin(2*theta) / g


def slope_over_gap(x, y):
    return y / (x - 1)


@pytest.mark.needs_full_proof_budget
def test_a_raise_witness_sits_at_the_claims_evaluation_point():
    [p] = check_conjectures(projectile_range, [
        claim("d(f(v0, theta, g), theta)@{theta=pi/4} == 0",
              route="derive")])
    assert p.verdict == "falsified"
    assert "theta = 1" not in (p.counterexample or "")
    assert "g = 0" in p.counterexample
    with pytest.raises(ZeroDivisionError):
        projectile_range(1, pi / 4, 0)


@pytest.mark.needs_full_proof_budget
def test_a_raise_away_from_the_evaluation_point_does_not_falsify():
    [p] = check_conjectures(slope_over_gap, [
        claim("d(f(x, y), y)@{x=2} == 1", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.counterexample, p.sketch)
