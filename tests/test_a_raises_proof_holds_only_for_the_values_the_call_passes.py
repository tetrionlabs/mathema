# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive binds a claim's domain to the function's own parameters, so a
`raises(...)` proof stands only when the call passes each parameter the
value the domain gives it. A call that passes a variable of the claim
anywhere but as itself in its own place (`f(-x)`, `f(x + 10)`,
`f(y, x)`), or a literal where the claim's domain binds that parameter
to other values (`for x in [-5, -1]`, `f(1)`), is not proven by derive.
A call of literals alone keeps the domain inferred from its literals."""
import pytest

from mathema.conjecture import check_conjectures, claim


def r01(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def r02(x: float, y: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x + y


def ground(price: float, code: float) -> float:
    if code == 0:
        raise ValueError("no code")
    return price / code


@pytest.mark.parametrize("fn,text", [
    (r01, "for x in [-5, -1], raises(f(-x), ValueError)"),
    (r01, "for x in [-5, -1], raises(f(1), ValueError)"),
    (r01, "for x in [-5, -1], raises(f(x + 10), ValueError)"),
    (r02, "for x in [-5, -1], y in [0, 1], raises(f(y, x), ValueError)"),
], ids=["negated", "constant", "shifted", "swapped"])
def test_derive_does_not_prove_a_raise_at_a_call_that_departs_from_the_domain(fn, text):
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def test_a_call_of_literals_alone_is_proven_over_the_point_it_names():
    (row,) = check_conjectures(ground, [claim("raises(f(50, 0), ValueError)", route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
