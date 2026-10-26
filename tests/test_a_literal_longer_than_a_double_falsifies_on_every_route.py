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
