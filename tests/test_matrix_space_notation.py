# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A matrix space is written `R^(m,n)` (rows, cols) and every accepted
spelling of it reads as that one claim. The unicode display uses
superscripts (`ℝᵐˣⁿ`, `ℝ²ˣ³`) wherever those read back as the same
claim, and the plain exponent (`ℝ^(x,n)`) where they would not: a
dimension named `x` is spelled like the superscript separator `ˣ`, and
some letters have no superscript glyph at all."""
import pytest

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text, render_claim_text
from tests.test_claim_text_soundness import _verdict, assert_round_trips


def corner(a: list) -> float:
    return a[0][0]


def first(v: list) -> float:
    return v[0]


def square(x: float) -> float:
    return x * x


def _law(space: str) -> str:
    return f"for a in {space}, f(a) == a[0][0]"


@pytest.mark.parametrize("space", [
    "R^(m,n)", "R^{m,n}", "R^(m×n)", "R^{m×n}", "R^(m*n)", "ℝᵐˣⁿ",
    "R^(m, n)", "ℝ^(m,n)",
])
def test_every_matrix_spelling_is_the_same_claim(space):
    canon = assert_round_trips(_law(space), corner)
    assert canon == "for a in R^(m,n)|missing, f(a) = a[0][0]"
    assert _verdict(corner, claim(_law(space))) == "holds"


@pytest.mark.parametrize("space", [
    "R^(3,3)", "R^{3,3}", "R^(3×3)", "ℝ^{3×3}", "ℝ³ˣ³", "R^(3*3)",
])
def test_a_fixed_size_matrix_reads_in_every_spelling(space):
    canon = assert_round_trips(_law(space), corner)
    assert canon == "for a in R^(3,3)|missing, f(a) = a[0][0]"


def test_the_ascii_display_uses_commas_and_the_unicode_superscripts():
    cj = claim(_law("R^(2*3)"))
    assert "R^(2,3)" in render_claim_text(cj, unicode=False)
    assert "ℝ²ˣ³" in render_claim_text(cj, unicode=True)
    cj = claim(_law("R^(m*n)"))
    assert "ℝᵐˣⁿ" in render_claim_text(cj, unicode=True)


@pytest.mark.parametrize("space, shown", [
    ("R^(x,n)", "ℝ^(x,n)"),
    ("R^(x*n)", "ℝ^(x,n)"),
    ("R^(n,x)", "ℝ^(n,x)"),
    ("R^(nx,m)", "ℝ^(nx,m)"),
    ("R^(q,n)", "ℝ^(q,n)"),
])
def test_a_dimension_the_superscripts_cannot_carry_displays_plainly(
        space, shown):
    cj = claim(_law(space))
    assert shown in render_claim_text(cj, unicode=True)
    assert_round_trips(_law(space), corner)


@pytest.mark.parametrize("space, shown", [
    ("R^x", "ℝ^x"),
    ("R^q", "ℝ^q"),
    ("R^n", "ℝⁿ"),
    ("R^3", "ℝ³"),
])
def test_a_vector_dimension_the_superscripts_cannot_carry(space, shown):
    law = f"for v in {space}, f(v) == v[0]"
    assert shown in render_claim_text(claim(law), unicode=True)
    assert_round_trips(law, first)


def test_a_parameter_named_x_is_unaffected():
    law = "for x in R^(m,n), f(x) == x[0][0]"
    canon = assert_round_trips(law, corner)
    assert canon == "for x in R^(m,n)|missing, f(x) = x[0][0]"
    shown = render_claim_text(claim(law), unicode=True)
    assert "∀ x ∈ ℝᵐˣⁿ" in shown
    assert_round_trips("for x in [0, 1], f(x) >= x² - 9", square)


def test_a_three_dimensional_space_reads_back():
    law = "for a in R^(k,m,n), f(a) == f(a)"
    canon = assert_round_trips(law)
    assert "R^(k,m,n)" in canon
    assert "ℝᵏˣᵐˣⁿ" in render_claim_text(claim(law), unicode=True)


@pytest.mark.parametrize("spelling", [
    "a in R^(m,)", "a in R^(,n)", "a in R^(m,,n)", "a in R^{m",
])
def test_a_malformed_matrix_space_is_refused(spelling):
    from mathema.conjecture import InvalidConjecture
    with pytest.raises(InvalidConjecture):
        claim(f"for {spelling}, f(a) >= 0")


def test_the_canonical_text_is_the_comma_form():
    assert canonical_claim_text(claim(_law("R^(m*n)"))) == \
        canonical_claim_text(claim(_law("R^(m,n)")))
