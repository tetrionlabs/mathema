# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A miss found by sampling derive's own reconstructed formula
(probe:lifted_numeric) falsifies the claim, on every route, only when the
code, run at that point, fails the relation exactly. A point the code
cannot be run at for the claim (a derivative or an integral, which only
the reconstruction reads) is no witness, and the claim stays unknown
with the reason."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def heat_index_like(t, h):
    return (-8.78 + 1.61 * t + 2.34 * h - 0.146 * t * h
            + 0.012 * t * t * math.exp(h / 80) / (1 + 0.01 * t * h))


def carrier(a):
    return a


_DERIVATIVE = "for t in [80,110], h in [40,100], d(f(t,h), h) >= -10"
_INTEGRAL = "for a in [0.5, 2], integrate(exp(-x**2 + sin(x)), x, 0, a) >= 10"


def test_a_reconstruction_miss_the_code_cannot_run_is_no_witness_on_derive():
    # d(f, h) = 2.34 - 0.146 t + ... is below -10 for t near 110, but
    # only the reconstruction reads the derivative
    (p,) = check_conjectures(heat_index_like, [claim(_DERIVATIVE, route="derive")])
    assert (p.verdict, p.route) == ("unknown", "derive"), (p.verdict, p.route,
                                                           p.note)
    assert "derive's reconstruction" in p.note
    assert "is no witness" in p.note
    assert p.counterexample is None


@pytest.mark.parametrize("route", ["best", "derive"])
def test_a_reconstruction_miss_of_an_integral_is_no_witness_on_any_route(route):
    # the integrand exp(-x**2 + sin(x)) is at most e, so the integral over
    # [0, a] with a <= 2 is at most 2e < 10: false, but only the
    # reconstruction's quadrature evaluates it
    (p,) = check_conjectures(carrier, [claim(_INTEGRAL, route=route)])
    assert (p.verdict, p.route) == ("unknown", "derive"), (p.verdict, p.route,
                                                           p.note)
    assert "is no witness" in p.note
