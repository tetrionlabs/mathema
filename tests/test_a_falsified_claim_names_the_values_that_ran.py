# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A falsified claim always carries the executed witness it was decided
on, written as the values the code ran with: a claim whose bound
variable never reaches its own calls is witnessed by those calls, and a
bool argument prints as False or True on every route."""
import re

import pytest

from mathema.claims import check_conjectures, claim


def plain_abs(x):
    return abs(x)


def dispatch_on_flags(x: float, x_discrete: bool, y_discrete: bool) -> float:
    if x_discrete and y_discrete:
        return 1.0
    if x_discrete and not y_discrete:
        return 2.0
    if y_discrete and not x_discrete:
        return 3.0
    return x


_ROUTES = [{}, {"route": "derive"}, {"route": "probe"}]


@pytest.mark.parametrize("text, call, sides", [
    ("for x in [1, 5], f(-3) == -3", "f(-3)", "3 vs -3"),
    ("for x in [1, 5], f(2) < 0", "f(2)", "2 vs 0"),
    ("for x in [1, 5], f(-1) + f(1) == 0", "f(-1), f(1)", "2 vs 0"),
])
@pytest.mark.parametrize("route", [{}, {"route": "derive"}])
def test_a_claim_whose_variable_reaches_no_call_is_witnessed_by_its_calls(
        text, call, sides, route):
    (p,) = check_conjectures(plain_abs, [claim(text, **route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample == f"{call}: {sides}", p.counterexample


@pytest.mark.parametrize("route", _ROUTES)
def test_a_bool_argument_is_written_as_a_bool_on_every_route(route):
    (p,) = check_conjectures(dispatch_on_flags,
                             [claim("f(x, x_discrete, y_discrete) >= 0", **route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    for name in ("x_discrete", "y_discrete"):
        shown = re.search(rf"\b{name} = ([^,:]+)", p.counterexample or "")
        assert shown is not None, p.counterexample
        assert shown.group(1) in ("False", "True"), p.counterexample
    # the only failing points are the ones with both flags off
    assert "x_discrete = False, y_discrete = False" in p.counterexample


def identity(x):
    return x


@pytest.mark.parametrize("route", [{}, {"route": "derive"}])
def test_an_exact_witness_with_no_coordinate_is_written_as_its_call(route):
    # 1e-20 + 1 rounds to 1 in float64 and is 1 + 10**-20 exactly
    (p,) = check_conjectures(identity,
                             [claim("for x in [1, 5], f(1e-20) + 1 == 1", **route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("f(1e-20): 1 vs 1, false here in "
                                       "exact arithmetic"), p.counterexample
    assert p.meta["mathema.exact_witness"]["at"] == "f(1e-20)"
