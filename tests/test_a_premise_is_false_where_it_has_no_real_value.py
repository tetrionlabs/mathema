# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise is false wherever it has no real value. `assuming
sqrt(x) > 1/2` admits only x > 1/4, so a point with negative x, where
the premise's root is not real, lies outside the premise's region and
is never a witness against the claim."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic import _smt


def ident(x: float) -> float:
    return x


pytestmark = pytest.mark.skipif(not _smt.available(),
                                reason="needs the optional z3 dependency")


def test_a_root_in_the_premise_does_not_produce_a_witness():
    x = sympy.Symbol("x", real=True)
    box = {"x": Interval(-1.0, 1.0, True, True)}
    premise = sympy.sqrt(x) > sympy.Rational(1, 2)
    result = _smt.nlsat_decide(x, ">", box, {"x": x}, bound_context=premise)
    assert result is not None and result.status == "proven"


@pytest.mark.needs_full_proof_budget
def test_a_claim_under_a_root_premise_is_proven():
    (p,) = check_conjectures(
        ident, [claim("assuming sqrt(x) > 0.5, for x in [-1, 1], f(x) > 0")],
        extensive=True)
    assert p.verdict == "proven"
    assert "UNCORROBORATED" not in (p.note or "")


def gap(x: float) -> float:
    return x - 0.5


def test_a_claim_false_inside_a_root_premise_is_still_falsified():
    (p,) = check_conjectures(
        gap, [claim("assuming sqrt(x) > 0.5, for x in [-1, 1], f(x) > 0")],
        extensive=True)
    assert p.verdict == "falsified"
    assert p.counterexample == "x=0.5"
