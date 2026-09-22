# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Math constants on the probe route: a bare `pi`/`e` (not a parameter)
evaluates to its real value, matching the derive route, previously it
was sampled as a random free variable, which falsified true claims. A
parameter named `e`/`pi` still wins (precedence identical to derive)."""
import math

from mathema.conjecture import claim, check_conjectures


def circle_area(r):
    return math.pi * r * r


def returns_e(x):
    return math.e


def apoapsis(a, e):          # e is a real parameter (eccentricity)
    return a * (1 + e)


def _verdict(fn, law, route="probe"):
    return check_conjectures(fn, [claim(law, route=route)])[0]


def test_bare_pi_is_the_constant_not_a_free_variable():
    # regression: this falsified with a sampled pi=-1.21 before the fix
    assert _verdict(circle_area,
                    "for r in [1, 2], f(r) == pi*r^2").verdict == "holds"


def test_bare_e_is_eulers_number_on_probe():
    assert _verdict(returns_e, "for x in [1, 5], f(x) == e").verdict == "holds"


def test_probe_and_derive_agree_on_a_bare_constant():
    # agreement means both routes SUPPORT the claim, each at its own
    # ceiling: derive proves exactly, probe's ceiling is holds,
    # asserted per route, so a route silently flipping is caught
    assert _verdict(circle_area, "for r in [1, 2], f(r) == pi*r^2",
                    route="derive").verdict == "proven"
    assert _verdict(circle_area, "for r in [1, 2], f(r) == pi*r^2",
                    route="probe").verdict == "holds"


def test_a_parameter_named_e_still_wins_over_the_constant():
    # precedence: a real parameter shadows the constant; each route
    # supports the claim at its own ceiling
    expected = {"derive": "proven", "probe": "holds"}
    for route, want in expected.items():
        assert _verdict(apoapsis, "for a in [1,10], e in [0,0.9], "
                        "f(a,e) == a*(1+e)", route=route).verdict == want


def test_exp_of_one_is_the_collision_free_canonical_euler():
    # exp is reserved, never a parameter, so exp(1) is unambiguous;
    # each route supports the claim at its own ceiling
    expected = {"derive": "proven", "probe": "holds"}
    for route, want in expected.items():
        assert _verdict(returns_e, "for x in [1,5], f(x) == exp(1)",
                        route=route).verdict == want


def test_a_parameter_shadowing_a_constant_carries_a_warning():
    (p,) = check_conjectures(apoapsis, [claim(
        "for a in [1,10], e in [0,0.9], f(a,e) == a*(1+e)", route="probe")])
    assert p.verdict == "holds"
    assert "read as the parameter" in p.note
    assert "exp(1)" in p.note
