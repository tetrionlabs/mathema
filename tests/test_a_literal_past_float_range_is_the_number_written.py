# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A literal past float64's range (`1e400`) is the number as written, not
an infinity: the probe decides each draw against it exactly, so a claim
no finite value can meet is falsified at its first draw, and one every
value meets holds."""
import pytest

from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


def constant(n: int) -> int:
    return 10 ** 400


@pytest.mark.parametrize("law", ["for x in [0, 1], f(x) >= 1e400",
                                 "for x in [0, 1], f(x) == 1e400"])
@pytest.mark.parametrize("route", ["probe", "best", "derive"])
def test_a_value_short_of_the_literal_falsifies(law, route):
    (p,) = check_conjectures(ident, [claim(law, route=route)])
    assert p.verdict == "falsified", (route, p.verdict, p.note)
    assert p.counterexample


def test_a_value_below_the_literal_holds_on_the_probe():
    (p,) = check_conjectures(ident, [claim("for x in [0, 1], f(x) <= 1e400",
                                           route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_the_literal_equals_the_integer_it_writes():
    # 1e400 is 10**400 exactly
    (p,) = check_conjectures(constant, [claim("f(2) == 1e400", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
