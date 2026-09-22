# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The public forms API: alternative closed forms of arbitrary code
and the extensible substitution library, the same registries the
extensive proof ladder draws on."""
import math

import pytest
import sympy

from mathema.forms import (
    Substitution, closed_forms, register_substitution, substituted_forms,
)
from mathema.symbolic import _forms as forms_registry


def quartic(x: float) -> float:
    return x ** 4 - 2.0 * x ** 2 + 1.5


def logpoly(x: float) -> float:
    return math.log(x) ** 2 - 2.0 * math.log(x) + 1.5


def summing(xs: list) -> float:
    total = 0.0
    for v in xs:
        total = total + v
    return total


def test_closed_forms_lead_with_the_lift_and_deduplicate():
    forms = closed_forms(quartic)
    assert forms[0].name == "as written"
    names = [f.name for f in forms]
    assert len(names) == len(set(names))
    reprs = {sympy.srepr(f.expr) for f in forms}
    assert len(reprs) == len(forms)


def test_closed_forms_name_the_blocker_for_an_unliftable_body():
    with pytest.raises(ValueError, match="no closed form"):
        closed_forms(summing)


def test_substituted_forms_offer_the_log_substitution_with_its_condition():
    subs = substituted_forms(logpoly)
    assert any(s.name == "t = log(x)" and s.requires == "x > 0" for s in subs)
    (log_form,) = [s for s in subs if s.name == "t = log(x)"]
    t = log_form.var
    assert sympy.simplify(
        log_form.expr - (t ** 2 - 2 * t + sympy.Rational(3, 2))) == 0


def test_registered_substitution_becomes_available_and_rejects_duplicates():
    cube = Substitution(
        name="t = x**3", requires="always",
        forward=lambda v: v ** 3,
        inverse=lambda t: sympy.cbrt(t),
        detect=lambda e, x: any(x in p.base.free_symbols and p.exp == 3
                                for p in e.atoms(sympy.Pow)),
        applicable=lambda lo, hi: True)
    register_substitution(cube)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register_substitution(cube)

        def cubic(x: float) -> float:
            return x ** 3 + 1.0

        assert any(s.name == "t = x**3" for s in substituted_forms(cubic))
    finally:
        forms_registry._SUBSTITUTIONS.remove(cube)
