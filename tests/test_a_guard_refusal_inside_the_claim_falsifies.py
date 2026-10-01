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


@enforce_domain(domain={"alpha": (0, 1)})
def blend_toward_one(x: float, alpha: float) -> float:
    return alpha * x + (1 - alpha) * 1.0


@pytest.mark.parametrize("adjudicate", ["check", "check_conjectures"])
def test_a_parameter_the_claim_leaves_unbound_ranges_over_the_guard(adjudicate):
    statement = "for x in [1, 10], f(x, alpha) <= x"
    if adjudicate == "check":
        p = {q.name: q for q in check(blend_toward_one, claims=[
            claim(statement, name="row")]).probes}["row"]
    else:
        (p,) = check_conjectures(blend_toward_one, [claim(statement)])
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)


@enforce_domain(domain={"x": (0, 1)})
def guarded_identity(x: float) -> float:
    return x


@enforce_domain(domain={"x": (0, 1), "y": (0, 1)})
def guarded_product(x: float, y: float) -> float:
    return x * y


@pytest.mark.parametrize("fn, statement", [
    (guarded_identity, "for x in [0, 1], f(2 * x) <= 0.6"),
    (guarded_identity, "for x in [0, 0.5], f(2 * x) <= 0.6"),
    (guarded_product, "for x in [0, 1], y in [0, 1], f(x + y, y) <= 0.5"),
    (guarded_product, "for x in [0, 0.5], y in [0, 0.5], f(x + y, y) <= 0.1"),
])
def test_a_false_claim_over_a_guarded_function_is_never_proven(fn, statement):
    for route in ("best", "derive"):
        (p,) = check_conjectures(fn, [claim(statement, route=route)])
        assert p.verdict != "proven", (statement, route, p.sketch)
    (p,) = check_conjectures(fn, [claim(statement)])
    assert p.verdict == "falsified", (statement, p.verdict, p.note)
