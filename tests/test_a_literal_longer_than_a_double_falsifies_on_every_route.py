# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim side holding a literal longer than a double
(`0.99999999999999999999`) is the number written. A draw whose float
evaluation passes only because the parse rounded that literal to a
double is decided exactly, so a claim false at an executed point is
falsified whatever route it declares: `f(x) <= 0.99999999999999999999`
on [0, 1] fails at x = 1, where f returns exactly 1."""
import pytest

from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
def test_a_long_literal_is_falsified_at_an_executed_point(route):
    (p,) = check_conjectures(ident, [claim(
        "for x in [0, 1], f(x) <= 0.99999999999999999999", route=route)])
    assert p.verdict == "falsified", (route, p.verdict, p.note)
    assert p.counterexample.startswith("x = 1"), p.counterexample


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
def test_a_long_literal_the_claim_meets_holds_or_is_proven(route):
    # every x in [0, 1] is below 1.0000000000000000001
    (p,) = check_conjectures(ident, [claim(
        "for x in [0, 1], f(x) <= 1.0000000000000000001", route=route)])
    assert p.verdict in ("proven", "holds"), (route, p.verdict, p.note)


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
@pytest.mark.parametrize("law", [
    # 1 < 1 + 10**-19, though the double of the literal is 1.0
    "for x in [0, 1], f(x) < 1.0000000000000000001",
    # 1 != 1 - 10**-20, though the double of the literal is 1.0
    "for x in [1, 1], f(x) != 0.99999999999999999999",
])
def test_a_fail_resting_on_the_rounding_of_a_long_literal_is_no_witness(
        route, law):
    (p,) = check_conjectures(ident, [claim(law, route=route)])
    assert p.verdict in ("proven", "holds"), (route, p.verdict,
                                              p.counterexample)


def by_text(x: float) -> float:
    # float(str(x)) has no exact reading
    return float(str(x)) * 10


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
def test_a_fail_far_from_the_long_literal_is_decided_as_the_float_says(route):
    # f(1) = 10, far past 0.99999999999999999999 at any neighbouring
    # double of the literal: falsified with no exact reading needed
    (p,) = check_conjectures(by_text, [claim(
        "for x in [0, 1], f(x) <= 0.99999999999999999999", route=route)])
    assert p.verdict == "falsified", (route, p.verdict, p.note)
