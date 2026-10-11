# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exact identity whose two sides grow large is never falsified:
`(exp(r) - 1)**2` and `4*exp(r)*sinh(r/2)**2` are the same function,
but at r near 15 both are about 1e13, where a double rounds their
difference to about 1e-3. Derive's numeric search for a counterexample
evaluates the difference at the drawn point's exact value, so rounding
never stands in for a nonzero difference."""
import math

import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._proof_support import _corroborate_disproof


def grown_square(r: float) -> float:
    return (math.exp(r) - 1)**2


def occupancy_ratio(r: float) -> float:
    return r**2 * math.exp(r) / (math.exp(r) - 1)**2


def _identity_difference():
    r = sympy.Symbol("r", real=True)
    return r, (sympy.exp(r) - 1)**2 - 4*sympy.exp(r)*sympy.sinh(r/2)**2


@pytest.mark.parametrize("domain", [{"r": (0.0, 20.0)}, {}])
def test_the_numeric_search_finds_no_counterexample_to_an_identity(domain):
    r, diff = _identity_difference()
    assert _corroborate_disproof(diff, domain, {"r": r}) is None


def test_a_real_difference_is_still_found():
    r, diff = _identity_difference()
    point = _corroborate_disproof(diff + sympy.Rational(1, 1000),
                                  {"r": (0.0, 20.0)}, {"r": r})
    assert point is not None


@pytest.mark.parametrize("fn,law", [
    (grown_square, "for r in (0, 20], f(r) == 4*exp(r)*sinh(r/2)**2"),
    (occupancy_ratio, "for r in (0, 20], (exp(r) - 1)**2 == "
                      "4*exp(r)*sinh(r/2)**2"),
    (occupancy_ratio, "for r in (0, 20], f(r) == "
                      "r**2*exp(r)/(4*exp(r)*sinh(r/2)**2)"),
])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_the_identity_is_proven_or_holds(fn, law, route):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
