# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bare infinity in a claim is the constant, on both routes.

`oo`, `inf`, `infinity` and `∞` all name infinity, and `-oo` its
negative. The probe binds each to the float infinity, so `f(x) < oo` is
a claim about a finite value being finite rather than about a sampled
number; the free-variable collector never reads one as a name; and the
canonical text spells every one of them `inf` (unicode `∞`), the way
the domain already writes an infinite bound.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim
from mathema.conjecture import _validate
from mathema.spec import canonical_claim_text, render_claim_text

SPELLINGS = ["oo", "inf", "infinity", "∞"]


def plus_one(x: float) -> float:
    return x + 1.0


def _adjudicate(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


@pytest.mark.parametrize("spelling", SPELLINGS + ["-oo", "-inf"])
def test_a_bare_infinity_is_never_a_free_variable(spelling):
    cj = claim(f"for x in [1, 2], f(x) < {spelling}")
    _code, aux = _validate(cj.rhs, {"x"}, set())
    assert aux == set(), aux


def test_a_genuine_free_name_is_still_collected():
    # the control on the collector: a name that is not infinity is a
    # free variable, as before
    cj = claim("for x in [1, 2], f(x) < c")
    _code, aux = _validate(cj.rhs, {"x"}, set())
    assert aux == {"c"}


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_a_finite_value_is_below_infinity_on_the_probe(spelling):
    p = _adjudicate(plus_one, f"for x in [1, 2], f(x) < {spelling}", route="probe")
    assert (p.verdict, p.route) == ("holds", "probe"), (p.verdict, p.note)


def test_a_finite_value_is_above_minus_infinity_on_the_probe():
    p = _adjudicate(plus_one, "for x in [1, 2], f(x) > -oo", route="probe")
    assert (p.verdict, p.route) == ("holds", "probe"), (p.verdict, p.note)


@pytest.mark.parametrize("law", [
    "for x in [1, 2], f(x) > oo",
    "for x in [1, 2], f(x) < -oo",
    "for x in [1, 2], f(x) == inf",
])
def test_a_finite_value_is_not_infinite(law):
    # the control: infinity is bound to the float infinity, so these are
    # false at every point and a witness says so
    p = _adjudicate(plus_one, law, route="probe")
    assert (p.verdict, p.route) == ("falsified", "probe"), (p.verdict, p.note)
    assert p.counterexample, p.note


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_every_spelling_reaches_one_verdict_on_the_best_route(spelling):
    # the derive route declines a comparison against an infinite side
    # and says so, and the probe settles it
    p = _adjudicate(plus_one, f"for x in [1, 2], f(x) < {spelling}")
    assert (p.verdict, p.route) == ("holds", "probe"), (p.verdict, p.note)
    assert "an infinite side" in (p.note or ""), p.note


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_the_canonical_text_spells_infinity_inf(spelling):
    cj = claim(f"for x in [1, 2], f(x) < {spelling}")
    assert canonical_claim_text(cj) == "for x in [1.0, 2.0]:float|missing, f(x) < inf"
    assert render_claim_text(cj, unicode=True) == "∀ x ∈ [1.0, 2.0] ⊂ ℝ ∪ {∅}, f(x) < ∞"


def test_minus_infinity_spells_minus_inf():
    cj = claim("for x in [1, 2], f(x) > -oo")
    assert canonical_claim_text(cj) == "for x in [1.0, 2.0]:float|missing, f(x) > -inf"
    assert render_claim_text(cj, unicode=True) == "∀ x ∈ [1.0, 2.0] ⊂ ℝ ∪ {∅}, f(x) > -∞"


@pytest.mark.parametrize("law, ascii_form", [
    ("lim(f(x), x, oo) == 0", "lim(f(x), x, inf) = 0"),
    ("lim(f(x), x -> -oo) == 0", "lim(f(x), x, -inf) = 0"),
    ("∫(d(f(x), x), x, -oo, oo) == 1", "integrate(d(f(x), x), x, -inf, inf) = 1"),
    ("for x in [0, oo), f(x) < oo", "for x in [0.0, inf):float|missing, f(x) < inf"),
])
def test_a_law_and_its_domain_spell_infinity_alike(law, ascii_form):
    cj = claim(law)
    assert canonical_claim_text(cj) == ascii_form
    # render, parse, render is a fixed point in both modes
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        again = claim(shown)
        assert render_claim_text(again, unicode=unicode) == shown
        assert canonical_claim_text(again) == ascii_form


def test_a_parameter_named_oo_still_shadows_the_constant():
    cj = claim("for oo in [0, 100], f(oo) >= 0")
    shown = render_claim_text(cj, unicode=True)
    assert "∞" not in shown and "inf" not in shown, shown
