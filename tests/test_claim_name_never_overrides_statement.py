# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's statement decides what it asserts. A name that happens to
match a registered family (`monotonic_increasing[x]`, `convex[x]`,
`is_pole_safe[x]`, ...) reaches that family only when the statement is
the one the family adjudicates; any other statement is judged as
written."""
import pytest

from mathema.conjecture import check_conjectures, claim


def opaque_identity(x: float) -> float:
    return sorted([x, x])[0]


def reciprocal(x: float) -> float:
    return 1.0 / x


@pytest.mark.parametrize("name", ["monotonic_increasing[x]",
                                  "monotonic_decreasing[x]", "affine[x]",
                                  "convex[x]", "concave[x]"])
@pytest.mark.parametrize("route", ["best", "probe"])
def test_a_family_name_on_an_ordinary_bound_is_judged_as_the_bound(name, route):
    r = check_conjectures(opaque_identity, [
        claim("for x in [0, 1], f(x) <= -5", name=name, route=route)])[0]
    assert r.verdict == "falsified", (r.verdict, r.route, r.note)
    assert r.route != "probe:algorithmic"


def test_a_safety_name_on_an_ordinary_bound_is_judged_as_the_bound():
    # 1/x on [1, 2] has its pole outside the domain, so is_pole_safe
    # would prove; the statement itself is false everywhere there
    r = check_conjectures(reciprocal, [
        claim("for x in [1, 2], f(x) >= 5", name="is_pole_safe[x]",
              route="best")])[0]
    assert r.verdict == "falsified", (r.verdict, r.route, r.sketch)
    assert r.route != "examine"


@pytest.mark.parametrize("name", ["is_deterministic", "is_state_safe",
                                  "is_numerically_stable"])
def test_a_code_property_name_on_an_ordinary_bound_is_judged_as_the_bound(name):
    r = check_conjectures(opaque_identity, [
        claim("for x in [0, 1], f(x) <= -5", name=name, route="best")])[0]
    assert r.verdict == "falsified", (r.verdict, r.route, r.sketch)
    assert r.route != "examine"


def test_the_family_statement_still_reaches_its_family():
    r = check_conjectures(opaque_identity, [
        claim("for x in [0, 1], d(f(x), x) >= 0",
              name="monotonic_increasing[x]", route="best")])[0]
    assert r.verdict == "holds", (r.verdict, r.route, r.note)
    assert r.route == "probe:algorithmic"
