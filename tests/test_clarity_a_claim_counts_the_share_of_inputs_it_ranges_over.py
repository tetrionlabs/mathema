# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim credits what it says about a function in proportion to the
share of the function's inputs it ranges over, counted in the values
each parameter's type holds: float64 doubles for a float, integers for
an int, members for a finite set. Claims over different parts of one
parameter's domain add up."""
from typing import Literal

import pytest

from mathema._clarity_reach import Universe, share
from mathema.badges import _clarity_profile, _reductions, clarity_score

_INF = float("inf")
_FLOAT, _INT = Universe("float"), Universe("int")


def _span(lo, hi, integer=False):
    return ("intervals", ((lo, hi),), integer)


@pytest.mark.parametrize("region, universe, expected", [
    (_span(0.0, 1.0), _FLOAT, 0.2499),          # doubles crowd towards zero
    (_span(0.0, 100.0), _FLOAT, 0.2515),
    (_span(0.0, _INF), _FLOAT, 0.5),
    (("points", frozenset({0.0, 1.0, 2.0})), _FLOAT, 0.0),
    (_span(0.0, 100.0, True), _INT, 0.0),       # a bounded stretch of Z
    (_span(0.0, _INF, True), _INT, 0.5),
    (_span(0.0, 50.0, True), Universe("int", ranges=((0.0, 100.0),)), 51 / 101),
    (("points", frozenset({"a", "b"})),
     Universe("finite", members=frozenset({"a", "b", "c"})), 2 / 3),
    (("whole",), Universe("other"), 1.0),
    (("points", frozenset({"a"})), Universe("other"), 0.0),
])
def test_the_share_is_counted_in_the_values_the_type_holds(region, universe,
                                                           expected):
    assert share([region], universe) == pytest.approx(expected, abs=1e-4)


def fahrenheit(c: float) -> float:
    """A Celsius temperature in Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


def _identity(binding=""):
    return [{"name": "conversion", "statement": f"{binding}f(c) == 1.8*c + 32",
             "verdict": "proven", "route": "derive"}]


def test_a_few_points_say_less_than_a_range_and_a_range_less_than_everything():
    def score(rows):
        return clarity_score(fahrenheit, verified_claims=rows,
                             library_keys=frozenset())
    points = score(_identity("for c in {-40.0, 0.0, 100.0}, "))
    ranged = score(_identity("for c in [0, 100], "))
    whole = score(_identity())
    assert score([]) <= points < ranged < whole


def test_a_claim_s_share_scales_every_dimension_it_credits():
    profile = _clarity_profile(fahrenheit, library_keys=frozenset())
    r = _reductions(_identity("for c in [0, 100], "), profile.pure, profile)
    assert r["identity"] == r["extent"] == r["shape"] == pytest.approx(
        0.2515, abs=1e-4)


def side_word(side: Literal["buy", "sell", "hold", "skip"]) -> str:
    """The side in capitals."""
    return side.upper()


def test_claims_over_halves_of_a_finite_domain_add_up():
    def row(members):
        return {"name": "upper", "statement":
                f"for side in {members}, f(side) == side.upper()",
                "verdict": "proven", "route": "derive:brute_force"}
    profile = _clarity_profile(side_word, library_keys=frozenset())
    one = _reductions([row('{"buy", "sell"}')], profile.pure, profile)
    both = _reductions([row('{"buy", "sell"}'), row('{"hold", "skip"}')],
                       profile.pure, profile)
    assert one["identity"] == pytest.approx(0.5)
    assert both["identity"] == pytest.approx(1.0)
    assert both["domain_soft:side"] == pytest.approx(1.0)
