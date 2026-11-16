# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `let` forms and the binding spellings, each pinned to the reading
it has today: a variable domain, a function, a pin, the operational
infinity, the type clause, and the holes. Each is a parametrised row of
`(text, ascii rendering, unicode rendering)`.
"""
import pytest

from mathema.conjecture import InvalidConjecture, claim
from mathema.domain import parse_binding, render_domain
from mathema.spec import render_claim_text


@pytest.mark.parametrize("text,ascii_text,unicode_text", [
    ("let c be 2.0, f(c) >= 0", "let c be 2, f(c) >= 0", "let c be 2, f(c) ≥ 0"),
    ("let k be 3, for x in [0, 1], f(x) + k >= 0",
     "let k be 3, for x in [0.0, 1.0] : float|absent|missing, k + f(x) >= 0",
     "let k be 3, ∀ x ∈ [0.0, 1.0] ⊂ ℝ ∪ {absent, ∅}, k + f(x) ≥ 0"),
    ("let c be [-1e6, 1e6], for x in [0, 10], f(x) + c >= 0",
     "let c be [-1000000.0, 1000000.0], for x in [0.0, 10.0] : float|absent|missing, c + f(x) >= 0",
     "let c be [-1000000.0, 1000000.0], ∀ x ∈ [0.0, 10.0] ⊂ ℝ ∪ {absent, ∅}, c + f(x) ≥ 0"),
    ("let g = math.sqrt, for x in (0, 100], g(x) >= 0",
     "let g = math.sqrt, for x in (0.0, 100.0] : float|absent|missing, g(x) >= 0",
     "let g = math.sqrt, ∀ x ∈ (0.0, 100.0] ⊂ ℝ ∪ {absent, ∅}, g(x) ≥ 0"),
    ("let |inf| be 1e6, for x in [0, oo), f(x) >= 0",
     "let |inf| be 1e+06, for x in [0.0, inf) : float|absent|missing, f(x) >= 0",
     "let |∞| be 1e+06, ∀ x ∈ [0.0, ∞) ⊂ ℝ ∪ {absent, ∅}, f(x) ≥ 0"),
])
def test_a_let_form_renders_as_it_does_today(text, ascii_text, unicode_text):
    cj = claim(text)
    assert render_claim_text(cj, unicode=False) == ascii_text
    assert render_claim_text(cj, unicode=True) == unicode_text


def test_a_let_pin_reads_its_literal():
    cj = claim("let flag be True, f(flag) == 1")
    assert cj.free_vars == frozenset()
    assert render_claim_text(cj, unicode=False)


def test_let_f_is_refused_because_f_names_the_function():
    with pytest.raises(InvalidConjecture, match="always names the function"):
        claim("let f be 2, f(x) >= 0")


@pytest.mark.parametrize("text,said", [
    ("let |inf| be -1, for x in [0, oo], f(x) >= 0",
     "let |inf| be ...: the operational infinity must be a finite positive magnitude; got '-1'"),
    ("let |inf| be abc, for x in [0, oo], f(x) >= 0",
     "let |inf| be ... expects a positive magnitude (let |inf| be 1e6); got 'abc'"),
])
def test_a_bad_operational_infinity_is_refused_with_its_message(text, said):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == said


@pytest.mark.parametrize("binding,ascii_text,unicode_text", [
    ("x in [0, 1]", "[0.0, 1.0] : float|absent|missing", "[0.0, 1.0] ⊂ ℝ ∪ {absent, ∅}"),
    ("x in [0, 1] : float", "[0.0, 1.0] : float", "[0.0, 1.0] ⊂ ℝ"),
    ("x in [0, 1] : int", "[0, 1] : int", "[0, 1] ⊂ ℤ"),
    ("x in [0, 10] subset Z", "[0, 10] : int", "[0, 10] ⊂ ℤ"),
    ("x in [0, 10] subset R", "[0.0, 10.0] : float", "[0.0, 10.0] ⊂ ℝ"),
    ("x in [0, 1] : float|absent", "[0.0, 1.0] : float|absent", "[0.0, 1.0] ⊂ ℝ ∪ {absent}"),
    ("x in [0, 1] : float|missing", "[0.0, 1.0] : float|missing", "[0.0, 1.0] ⊂ ℝ ∪ {∅}"),
    ("x in [0, 1] : float|absent|missing", "[0.0, 1.0] : float|absent|missing",
     "[0.0, 1.0] ⊂ ℝ ∪ {absent, ∅}"),
    ("x in R", "R|absent|missing", "ℝ ∪ {absent, ∅}"),
    ("x in Z", "Z|absent|missing", "ℤ ∪ {absent, ∅}"),
    ("x in [0, oo)", "[0.0, inf) : float|absent|missing", "[0.0, inf) ⊂ ℝ ∪ {absent, ∅}"),
])
def test_a_binding_renders_as_it_does_today(binding, ascii_text, unicode_text):
    name, bound = parse_binding(binding)
    assert name == "x"
    assert render_domain(bound, ascii_mode=True) == ascii_text
    assert render_domain(bound, ascii_mode=False) == unicode_text
