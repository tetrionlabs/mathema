# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`probe:semi_analytical` says a critical point found analytically was
among the inputs the probe ran. A critical point outside the claim's
domain is never drawn, so a probe whose every critical point lies
outside reports the plain sampling route, and clarity grades the row as
random sampling rather than as the semi-analytical probe."""
from mathema.badges import _HOLDS_STRENGTH, _strength
from mathema.conjecture import check_conjectures, claim


def revenue(price: float) -> float:
    return price * (100 - price)


def present_value(rate: float) -> float:
    total = 0.0
    for t in range(1, 4):
        total += 100 / (1 + rate) ** t
    return total


def _row(fn, law, extensive=False):
    (p,) = check_conjectures(fn, [claim(law, route="probe")],
                             extensive=extensive)
    return p


def test_a_critical_point_inside_the_domain_earns_the_subroute():
    p = _row(revenue, "for price in [0, 100], f(price) <= 2500")
    assert p.verdict == "holds"
    assert p.route == "probe:semi_analytical"
    assert _strength(p.verdict, p.route, p.n) \
        == _HOLDS_STRENGTH["probe:semi_analytical"]


def test_a_critical_point_outside_the_domain_leaves_the_plain_route():
    p = _row(revenue, "for price in [60, 100], f(price) <= 2500")
    assert p.verdict == "holds"
    assert p.route == "probe"
    assert _strength(p.verdict, p.route, p.n) \
        == _HOLDS_STRENGTH["probe"] * (1 - 3 / p.n)


def test_a_pole_outside_the_domain_is_not_semi_analytical_evidence():
    p = _row(present_value, "for rate in [-0.5, 0.5], f(rate) > 0",
             extensive=True)
    assert p.verdict == "holds"
    assert p.route == "probe"
    assert _strength(p.verdict, p.route, p.n) \
        < _HOLDS_STRENGTH["probe:semi_analytical"]
