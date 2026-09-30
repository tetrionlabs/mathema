# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's domain is its own binding, and a raise anywhere in it
falsifies, a guard refusing an argument included, whether the claim
passes the parameter as it is or transforms it (`f(2 * x)`). The derive
route reads the guard as the function's domain, so a claim over inputs
the function refuses is never proven; the probe falsifies it with the
guard's refusal as the witness. A claim whose arguments stay inside the
guard still proves."""
import math

import pytest

from mathema import check, enforce_domain
from mathema.conjecture import check_conjectures, claim


@enforce_domain(domain={"x": (0, 1)})
def unit_root(x: float) -> float:
    return math.sqrt(x)


def _through_check(statement, route="best"):
    rows = {p.name: p for p in check(unit_root, claims=[
        claim(statement, name="row", route=route)]).probes}
    return rows["row"]


def _through_conjectures(statement, route="best"):
    (p,) = check_conjectures(unit_root, [claim(statement, route=route)])
    return p


@pytest.mark.parametrize("adjudicate", [_through_check, _through_conjectures])
@pytest.mark.parametrize("statement", [
    "for x in [-1, 1], f(x) >= 0",       # the binding is wider than the guard
    "for x in [2, 3], f(x) >= 0",        # wholly outside it
    "for x in [0, 1], f(2 * x) >= 0",    # the argument leaves it above 0.5
    "for x in [0, 1], f(x + 2) >= 0",    # the argument never enters it
])
def test_a_guard_refusal_in_the_claims_domain_falsifies(adjudicate, statement):
    p = adjudicate(statement)
    assert p.verdict == "falsified", (statement, p.verdict, p.route, p.note)
    assert "DomainError" in str(p.counterexample), p.counterexample


@pytest.mark.parametrize("adjudicate", [_through_check, _through_conjectures])
@pytest.mark.parametrize("statement", [
    "for x in [2, 3], f(x) >= 0",
    "for x in [0, 1], f(2 * x) >= 0",
])
def test_derive_does_not_prove_over_inputs_the_guard_refuses(adjudicate,
                                                              statement):
    p = adjudicate(statement, route="derive")
    assert p.verdict != "proven", (statement, p.verdict, p.sketch)


@pytest.mark.parametrize("adjudicate", [_through_check, _through_conjectures])
@pytest.mark.parametrize("statement", [
    "for x in [0, 1], f(x) >= 0",
    "for x in [0, 0.25], f(2 * x) >= 0",
    "for x in [0, 0.5], f(x + 0.5) <= 1",
])
def test_a_claim_whose_arguments_stay_inside_the_guard_proves(adjudicate,
                                                               statement):
    p = adjudicate(statement)
    assert (p.verdict, p.route) == ("proven", "derive"), (statement, p.verdict,
                                                          p.note)
