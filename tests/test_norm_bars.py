# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A norm written with double bars, the order as a subscript.

`||x||` is `norm(x)` and `||x||_k` is `norm(x, k)` for `k` one of `1`,
`2`, an integer `p >= 1` and `inf` (also `oo` and `∞`); the two
spellings lower to the same text and reach the same verdict on the
same route. The order is never a superscript, so `||x||^2` is the
square of the norm. A written `||x||` renders back as written, `||x||`
in ascii and `‖x‖` in unicode with the order a subscript glyph, and a
written `norm(x)` stays the call. The record's note names the norm a
bare `||x||` resolves to: Euclidean for a vector, Frobenius for a
matrix. Any other order is refused with the accepted orders named.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema._linalg_eval import _norm
from mathema.claims import check_conjectures, claim
from mathema.conjecture import InvalidConjecture
from mathema.grammar import normalize
from mathema.spec import canonical_claim_text, render_claim_text
from tests.test_claim_text_soundness import assert_round_trips


def _spaceless(text: str) -> str:
    return text.replace(" ", "")


# --- the grammar ----------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("||x||", "norm(x)"),
    ("||x||_1", "norm(x, 1)"),
    ("||x||_2", "norm(x, 2)"),
    ("||x||_12", "norm(x, 12)"),
    ("||x||_inf", "norm(x, inf)"),
    ("||x||_oo", "norm(x, inf)"),
    ("||x||_∞", "norm(x, inf)"),
    ("||x - y||", "norm(x - y)"),
    ("||x - y||_2", "norm(x - y, 2)"),
    ("||f(x)||_1", "norm(f(x), 1)"),
    ("||x||^2", "norm(x)**2"),
    ("||x||_2^2", "norm(x, 2)**2"),
    ("||x||_2 + ||y||_2", "norm(x, 2) + norm(y, 2)"),
    ("2 * ||x|| / ||y||_inf", "2 * norm(x) / norm(y, inf)"),
    ("||a| - |b||", "abs(abs(a) - abs(b))"),
    ("‖x‖", "norm(x)"),
    ("‖x‖₂", "norm(x, 2)"),
    ("‖x‖₁₂", "norm(x, 12)"),
    ("‖x‖∞", "norm(x, inf)"),
    ("‖x - y‖", "norm(x - y)"),
    ("‖x‖^2", "norm(x)**2"),
    ("‖x‖²", "norm(x)**2"),
])
def test_double_bars_lower_to_the_norm_call(text, expected):
    assert _spaceless(normalize(text)) == _spaceless(expected)


@pytest.mark.parametrize("sugar, words", [
    ("for x in R^n, ||x|| >= 0", "for x in R^n, norm(x) >= 0"),
    ("for x in R^n, ||x||_1 >= ||x||_2", "for x in R^n, norm(x, 1) >= norm(x, 2)"),
    ("for x in R^n, ||x||_inf <= ||x||_1", "for x in R^n, norm(x, inf) <= norm(x, 1)"),
    ("for x in R^n, ||x||_oo <= ||x||_1", "for x in R^n, norm(x, inf) <= norm(x, 1)"),
    ("for x in R^n, ||x||^2 == dot(x, x)", "for x in R^n, norm(x)**2 == dot(x, x)"),
    ("for A in R^(n,n), ||A|| >= 0", "for A in R^(n,n), norm(A) >= 0"),
    ("for A in R^(n,n), ||A||_2 <= ||A||", "for A in R^(n,n), norm(A, 2) <= norm(A)"),
])
def test_the_sugar_parses_to_the_same_sides_as_the_words(sugar, words):
    a, b = claim(sugar), claim(words)
    assert (a.lhs, a.relation, a.rhs, a.domain) == (b.lhs, b.relation, b.rhs, b.domain)


def test_double_bars_around_a_matrix_are_its_norm_not_its_determinant():
    cj = claim("for A in R^(n,n), ||A|| >= |A|")
    assert (cj.lhs, cj.rhs) == ("norm(A)", "det(A)")


@pytest.mark.parametrize("bad", [
    "for x in R^n, ||x||_0 >= 0",
    "for x in R^n, ||x||_0.5 >= 0",
    "for x in R^n, ||x||_p >= 0",
    "for x in R^n, ||x||_-1 >= 0",
])
def test_an_order_the_bars_do_not_read_is_refused_naming_the_accepted_ones(bad):
    with pytest.raises(InvalidConjecture, match=r"1, 2, an integer p >= 1, or inf"):
        claim(bad)


@pytest.mark.parametrize("bad", [
    "for x in R^n, ||x| >= 0",
    "for x in R^n, ||x||_2 + |y >= 0",
])
def test_bars_that_do_not_pair_are_still_refused(bad):
    with pytest.raises(InvalidConjecture, match="do not pair up"):
        claim(bad)


# --- rendering ------------------------------------------------------------

@pytest.mark.parametrize("law, ascii_form, unicode_form", [
    ("for x in R^n, ||x|| >= 0",
     "for x in R^n|missing, ||x|| >= 0",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖ ≥ 0"),
    ("for x in R^n, ||x||_1 >= ||x||_2",
     "for x in R^n|missing, ||x||_1 >= ||x||_2",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖₁ ≥ ‖x‖₂"),
    ("for x in R^n, ||x||_inf <= ||x||_1",
     "for x in R^n|missing, ||x||_inf <= ||x||_1",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_oo <= ||x||_1",
     "for x in R^n|missing, ||x||_inf <= ||x||_1",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_∞ <= ||x||_1",
     "for x in R^n|missing, ||x||_inf <= ||x||_1",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_12 <= ||x||_1",
     "for x in R^n|missing, ||x||_12 <= ||x||_1",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖₁₂ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||^2 == dot(x, x)",
     "for x in R^n|missing, ||x||^2 = dot(x, x)",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖^2 = dot(x, x)"),
    ("for x in R^n, y in R^n, ||x - y|| <= ||x|| + ||y||",
     "for x in R^n|missing, y in R^n|missing, ||x - y|| <= ||x|| + ||y||",
     "∀ x ∈ ℝⁿ ∪ {∅}, y ∈ ℝⁿ ∪ {∅}, ‖x - y‖ ≤ ‖x‖ + ‖y‖"),
    ("for A in R^(n,n), ||A||_2 <= ||A||",
     "for A in R^(n,n)|missing, ||A||_2 <= ||A||",
     "∀ A ∈ ℝⁿˣⁿ ∪ {∅}, ‖A‖₂ ≤ ‖A‖"),
    ("∀ x ∈ ℝⁿ, ‖x‖₂ ≤ ‖x‖₁",
     "for x in R^n|missing, ||x||_2 <= ||x||_1",
     "∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖₂ ≤ ‖x‖₁"),
    # the words stay the words
    ("for x in R^n, norm(x) >= 0",
     "for x in R^n|missing, norm(x) >= 0",
     "∀ x ∈ ℝⁿ ∪ {∅}, norm(x) ≥ 0"),
    ("for x in R^n, norm(x, 2) <= norm(x, 1)",
     "for x in R^n|missing, norm(x, 2) <= norm(x, 1)",
     "∀ x ∈ ℝⁿ ∪ {∅}, norm(x, 2) ≤ norm(x, 1)"),
])
def test_a_norm_renders_as_the_author_spelled_it(law, ascii_form, unicode_form):
    cj = claim(law)
    assert render_claim_text(cj, unicode=False) == ascii_form
    assert render_claim_text(cj, unicode=True) == unicode_form
    assert canonical_claim_text(cj) == ascii_form


def test_the_canonical_text_writes_every_infinity_spelling_as_inf():
    texts = {canonical_claim_text(claim(f"for x in R^n, ||x||_{spelling} <= ||x||_1"))
             for spelling in ("inf", "oo", "∞")}
    assert texts == {"for x in R^n|missing, ||x||_inf <= ||x||_1"}


def test_a_norm_of_a_bar_term_keeps_the_call_spelling():
    cj = claim("for x in R^n, ||abs(x)|| == ||x||")
    assert render_claim_text(cj, unicode=False) == \
        "for x in R^n|missing, norm(|x|) = ||x||"


@pytest.mark.parametrize("law", [
    "for x in R^n, ||x|| >= 0",
    "for x in R^n, ||x||_1 >= ||x||_2",
    "for x in R^n, ||x||_oo <= ||x||_1",
    "for x in R^n, ||x||^2 == dot(x, x)",
    "for x in R^n, y in R^n, ||x - y|| <= ||x|| + ||y||",
    "for A in R^(m,n), ||A|| >= 0",
    "for A in R^(n,n), ||A||_2 <= ||A||",
    "for x in R^n, ||abs(x)|| == ||x||",
    "assuming ||x|| > 0, for x in R^n, ||x||_inf > 0",
])
def test_render_parse_render_is_a_fixed_point_in_both_modes(law):
    assert_round_trips(law)
    cj = claim(law)
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert render_claim_text(claim(shown), unicode=unicode) == shown


def test_the_two_spellings_are_two_canonical_texts():
    bars = claim("for x in R^n, ||x||_2 <= 1")
    words = claim("for x in R^n, norm(x, 2) <= 1")
    assert (bars.lhs, bars.rhs) == (words.lhs, words.rhs)
    assert canonical_claim_text(bars) != canonical_claim_text(words)


# --- the evaluation path: numpy's norm, both ranks, the matrix orders ------

_V = np.array([3.0, -4.0, 12.0])
_M = np.array([[1.0, -2.0], [3.0, 4.0]])
_RANK_ONE = np.array([[1.0, 2.0], [2.0, 4.0]])


@pytest.mark.parametrize("value, order, expected", [
    (_V, None, 13.0),                              # Euclidean
    (_V, 2, 13.0),
    (_V, 1, 19.0),                                 # sum of magnitudes
    (_V, np.inf, 12.0),                            # largest magnitude
    (_M, None, np.sqrt(30.0)),                     # Frobenius
    (_M, 1, 6.0),                                  # max column sum
    (_M, 2, np.linalg.svd(_M, compute_uv=False)[0]),   # spectral
    (_M, np.inf, 7.0),                             # max row sum
    # the boundaries: the zero vector, one entry, one cell, rank one
    (np.zeros(3), None, 0.0),
    (np.zeros(3), 1, 0.0),
    (np.zeros(3), np.inf, 0.0),
    (np.array([-3.0]), None, 3.0),
    (np.array([-3.0]), 1, 3.0),
    (np.array([-3.0]), np.inf, 3.0),
    (np.array([[-2.0]]), None, 2.0),
    (np.array([[-2.0]]), 1, 2.0),
    (np.array([[-2.0]]), 2, 2.0),
    (np.array([[-2.0]]), np.inf, 2.0),
    (_RANK_ONE, None, 5.0),                        # Frobenius equals spectral at rank one
    (_RANK_ONE, 2, 5.0),
    (_RANK_ONE, 1, 6.0),
    (_RANK_ONE, np.inf, 6.0),
])
def test_the_norm_agrees_with_numpy_for_both_ranks_and_every_order(value, order, expected):
    got = _norm(value) if order is None else _norm(value, order)
    assert got == pytest.approx(expected)
    assert got == pytest.approx(np.linalg.norm(value) if order is None
                                else np.linalg.norm(value, order))


def test_the_matrix_orders_are_three_different_numbers():
    # a control on the parametrisation above: on this matrix the column
    # sums, the singular values and the row sums do not coincide
    values = {_norm(_M, 1), _norm(_M, 2), _norm(_M, np.inf), _norm(_M)}
    assert len(values) == 4, values


@pytest.mark.parametrize("text, written", [
    ("for x in R^n, ||x|| >= 0", True),
    ("for x in R^n|missing, ||x||_2 <= ||x||_1", True),
    ("∀ x ∈ ℝⁿ ∪ {∅}, ‖x‖₂ ≤ ‖x‖₁", True),
    ("assuming ||x|| > 0, for x in R^n, f(x) >= 0", True),
    ("for x in R^n, norm(x) >= 0", False),
    ("for x in [0, 1], |x| <= 1", False),
    ("for a in [0, 1], b in [0, 1], ||a| - |b|| <= 1", False),
    ("for A in R^(n,n), |A| >= 0", False),
    ('f(s) == "||x||"', False),
])
def test_the_renderer_reads_the_bar_spelling_from_the_author_text(text, written):
    from mathema.grammar import norm_bars_written
    assert norm_bars_written(text) is written


# --- the same verdict on the same route as the words ---------------------

def euclidean_length(x: np.ndarray) -> float:
    return float(np.linalg.norm(x))


def manhattan_length(x: np.ndarray) -> float:
    return float(np.sum(np.abs(x)))


def largest_magnitude(x: np.ndarray) -> float:
    return float(np.max(np.abs(x)))


def squared_length(x: np.ndarray) -> float:
    return float(np.dot(x, x))


def distance(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.linalg.norm(x - y))


def frobenius(A: np.ndarray) -> float:
    return float(np.sqrt(np.sum(A * A)))


def largest_singular_value(A: np.ndarray) -> float:
    return float(np.linalg.svd(A, compute_uv=False)[0])


def max_column_sum(A: np.ndarray) -> float:
    return float(np.max(np.sum(np.abs(A), axis=0)))


def max_row_sum(A: np.ndarray) -> float:
    return float(np.max(np.sum(np.abs(A), axis=1)))


def _adjudicate(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn, sugar, words, verdict", [
    (euclidean_length, "for x in R^n, f(x) ~= ||x||",
     "for x in R^n, f(x) ~= norm(x)", "holds"),
    (euclidean_length, "for x in R^n, f(x) ~= ||x||_2",
     "for x in R^n, f(x) ~= norm(x, 2)", "holds"),
    (manhattan_length, "for x in R^n, f(x) ~= ||x||_1",
     "for x in R^n, f(x) ~= norm(x, 1)", "holds"),
    (largest_magnitude, "for x in R^n, f(x) ~= ||x||_inf",
     "for x in R^n, f(x) ~= norm(x, inf)", "holds"),
    (largest_magnitude, "for x in R^n, f(x) ~= ||x||_oo",
     "for x in R^n, f(x) ~= norm(x, inf)", "holds"),
    (squared_length, "for x in R^n, f(x) ~= ||x||^2",
     "for x in R^n, f(x) ~= norm(x)**2", "holds"),
    (distance, "for x in R^n, y in R^n, f(x, y) ~= ||x - y||",
     "for x in R^n, y in R^n, f(x, y) ~= norm(x - y)", "holds"),
    (frobenius, "for A in R^(m,n), f(A) ~= ||A||",
     "for A in R^(m,n), f(A) ~= norm(A)", "holds"),
    (largest_singular_value, "for A in R^(n,n), f(A) ~= ||A||_2",
     "for A in R^(n,n), f(A) ~= norm(A, 2)", "holds"),
    (max_column_sum, "for A in R^(m,n), f(A) ~= ||A||_1",
     "for A in R^(m,n), f(A) ~= norm(A, 1)", "holds"),
    (max_row_sum, "for A in R^(m,n), f(A) ~= ||A||_inf",
     "for A in R^(m,n), f(A) ~= norm(A, inf)", "holds"),
    # a false sibling falsifies in either spelling, with a witness
    (manhattan_length, "for x in R^n, f(x) ~= ||x||_2",
     "for x in R^n, f(x) ~= norm(x, 2)", "falsified"),
    (max_column_sum, "for A in R^(m,n), f(A) ~= ||A||_inf",
     "for A in R^(m,n), f(A) ~= norm(A, inf)", "falsified"),
])
def test_the_sugar_reaches_the_verdict_of_the_words(fn, sugar, words, verdict):
    a, b = _adjudicate(fn, sugar), _adjudicate(fn, words)
    assert (a.verdict, a.route) == (b.verdict, b.route) == (verdict, "probe"), \
        (a.verdict, a.note, b.verdict, b.note)
    if verdict == "falsified":
        assert a.counterexample and b.counterexample


# --- the note names the resolved norm -------------------------------------

def test_a_bare_norm_of_a_vector_is_noted_as_euclidean():
    p = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= ||x||")
    assert "||x|| is the Euclidean norm of x" in (p.note or ""), p.note


def test_a_bare_norm_of_a_matrix_is_noted_as_frobenius():
    p = _adjudicate(frobenius, "for A in R^(m,n), f(A) ~= ||A||")
    assert "||A|| is the Frobenius norm of A" in (p.note or ""), p.note


def test_a_bare_norm_of_a_difference_is_noted_from_its_operands():
    p = _adjudicate(distance, "for x in R^n, y in R^n, f(x, y) ~= ||x - y||")
    assert "||x - y|| is the Euclidean norm of x - y" in (p.note or ""), p.note


def test_a_bare_norm_of_a_call_is_noted_for_either_rank():
    # the rank of f(x) cannot be read from the claim, so the note says
    # what the bars mean for a vector and for a matrix
    from mathema.lexicon import unit_vector
    p = _adjudicate(unit_vector, "assuming ||x|| > 0, for x in R^n, ||f(x)|| ~= 1")
    assert ("||f(x)|| is the Euclidean norm of f(x) as a vector, "
            "the Frobenius norm as a matrix") in (p.note or ""), p.note


def test_a_written_order_needs_no_note():
    p = _adjudicate(manhattan_length, "for x in R^n, f(x) ~= ||x||_1")
    assert "norm of" not in (p.note or ""), p.note


def test_the_call_spelling_gets_no_note():
    p = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= norm(x)")
    assert "norm of" not in (p.note or ""), p.note


# --- the lexicon rows -----------------------------------------------------

#: every row of the sugar, with the verdict and route it reaches
#: against its example function; the trap row falsifies with a witness
_LEXICON_ROWS = {
    "norm_bars_euclidean": ("holds", "probe"),
    "norm_bars_two": ("holds", "probe"),
    "norm_bars_one": ("holds", "probe"),
    "norm_bars_inf": ("holds", "probe"),
    "norm_bars_chain": ("holds", "probe"),
    "norm_bars_homogeneous": ("holds", "probe"),
    "norm_bars_unit_vector": ("holds", "probe"),
    "norm_bars_distance": ("holds", "probe"),
    "norm_bars_distance_symmetric": ("holds", "probe"),
    "norm_bars_distance_zero": ("holds", "probe"),
    "norm_bars_triangle": ("holds", "probe"),
    "norm_bars_portfolio_weights": ("holds", "probe"),
    "norm_bars_squared": ("holds", "probe"),
    "norm_bars_order_trap": ("falsified", "probe"),
    "matrix_norm_bars_frobenius": ("holds", "probe"),
    "matrix_norm_bars_gram_trace": ("holds", "probe"),
    "matrix_norm_bars_spectral": ("holds", "probe"),
    "matrix_norm_bars_spectral_below_frobenius": ("holds", "probe"),
}


def test_every_sugar_row_of_the_lexicon_is_pinned_here():
    from mathema.lexicon import LEXICON
    sugar_rows = {key for key in LEXICON if "norm_bars" in key}
    assert sugar_rows == set(_LEXICON_ROWS)


@pytest.mark.parametrize("key, verdict, route", sorted(
    (key, *want) for key, want in _LEXICON_ROWS.items()))
def test_each_lexicon_row_reaches_its_pinned_verdict(key, verdict, route):
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON, SECTIONS, TAGS
    (fn,) = [fn for fn, keys in EXAMPLE_FUNCTIONS.values() if key in keys]
    assert key in SECTIONS["linear_algebra"]
    assert "norm" in TAGS[key]
    p = _adjudicate(fn, LEXICON[key])
    assert (p.verdict, p.route) == (verdict, route), (p.verdict, p.note)
    if verdict == "falsified":
        assert p.counterexample, p.note
    assert_round_trips(LEXICON[key], fn)


def test_the_trap_row_names_the_two_numbers_that_differ():
    from mathema.lexicon import LEXICON
    p = _adjudicate(manhattan_length, LEXICON["norm_bars_order_trap"])
    assert p.verdict == "falsified"
    assert " vs " in str(p.counterexample), p.counterexample


def test_the_triangle_inequality_fails_with_the_wrong_norms():
    # the control for the triangle row: the same distance is not bounded
    # by the sum of the largest magnitudes, and a witness says so
    from mathema.lexicon import distance as lexicon_distance
    p = _adjudicate(lexicon_distance,
                    "for x in R^n, y in R^n, f(x, y) <= ||x||_inf + ||y||_inf")
    assert p.verdict == "falsified" and p.counterexample, (p.verdict, p.note)


def test_the_unit_vector_row_needs_its_premise_for_the_zero_vector():
    # without the premise the zero vector divides by zero; the probe
    # over R^n does not draw that one point, so the row states the
    # premise rather than leaning on the draw
    from mathema.lexicon import LEXICON, unit_vector
    law = LEXICON["norm_bars_unit_vector"]
    assert law.startswith("assuming ||x|| > 0, ")
    p = _adjudicate(unit_vector, law)
    assert p.verdict == "holds", (p.verdict, p.note)
    with pytest.raises(FloatingPointError):
        with np.errstate(all="raise"):
            unit_vector(np.zeros(3))


def test_the_lexicon_rows_carry_the_documented_tags():
    from mathema.lexicon import TAGS
    assert "euclidean" in TAGS["norm_bars_euclidean"]
    assert "frobenius" in TAGS["matrix_norm_bars_frobenius"]
    assert "subscript" in TAGS["norm_bars_one"]
