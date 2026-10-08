# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Over a language, the length of a value reads as `len(...)`: the
canonical form keeps the one dimension spelling, `dim(X, 0)`, and a
claim stamped with the `mathema/language` grammar displays it as
`len(X)` in both unicode and ascii text. The displayed text is a fixed
point (render, reparse, render gives the same text and the same
claim). Every other axis, and every claim outside the language
dialect, keeps `dim`."""
import pytest

from mathema.conjecture import claim
from mathema.spec import render_claim_text


@pytest.mark.parametrize("unicode, expected", [
    (True, "∀ s ∈ L[ascii], len(f(s)) ≤ len(s)"),
    (False, "for s in L[ascii], len(f(s)) <= len(s)"),
])
def test_length_over_a_language_renders_as_len(unicode, expected):
    cj = claim("for s in L[ascii], len(f(s)) <= len(s)")
    assert cj.grammar == "mathema/language"
    assert cj.lhs == "dim(f(s), 0)" and cj.rhs == "dim(s, 0)"
    assert render_claim_text(cj, unicode=unicode) == expected


@pytest.mark.parametrize("unicode", [True, False])
@pytest.mark.parametrize("text", [
    "for s in L[ascii], len(f(s)) <= len(s)",
    'for s in L[unicode] \\ {""}, len(f(s)) >= 1',
    "for s in L[ascii, len <= 80], len(f(s)) <= 80",
    "for s in L[ascii], 0 <= len(f(s)) <= len(s) + 2",
    "for s in L[ascii], len(f(s + g(s))) == len(s) + len(g(s))",
    "assuming len(s) >= 1, for s in L[ascii], f(s) == s",
])
def test_the_rendered_text_is_a_fixed_point(text, unicode):
    cj = claim(text)
    shown = render_claim_text(cj, unicode=unicode)
    assert "dim(" not in shown, shown
    again = claim(shown)
    assert again.grammar == cj.grammar == "mathema/language"
    assert render_claim_text(again, unicode=unicode) == shown
    thrice = claim(render_claim_text(again, unicode=unicode))
    assert (thrice.lhs, thrice.relation, thrice.rhs, thrice.assuming) == \
        (again.lhs, again.relation, again.rhs, again.assuming)


def test_a_premise_over_a_language_renders_len():
    cj = claim("assuming len(s) >= 1, for s in L[ascii], f(s) == s")
    assert render_claim_text(cj, unicode=False).startswith("assuming len(s) >= 1, ")


def test_len_nested_inside_a_call_argument_renders_as_len():
    cj = claim("for s in L[ascii], f(len(s)) == len(f(s))")
    assert render_claim_text(cj, unicode=False) == \
        "for s in L[ascii], f(len(s)) = len(f(s))"


def test_a_string_literal_spelling_dim_is_left_alone():
    cj = claim("for s in L[ascii], f(s + 'dim(s, 0)') == len(s)")
    shown = render_claim_text(cj, unicode=False)
    assert '"dim(s, 0)"' in shown and "= len(s)" in shown


def test_a_second_axis_keeps_dim():
    cj = claim("for s in L[ascii], dim(f(s), 1) == len(s)")
    assert render_claim_text(cj, unicode=False) == \
        "for s in L[ascii], dim(f(s), 1) = len(s)"


@pytest.mark.parametrize("unicode", [True, False])
def test_outside_the_language_dialect_len_reads_as_len_too(unicode):
    cj = claim("assuming len(x) == len(y), f(x, y) == f(y, x)")
    assert cj.grammar == "mathema"
    assert render_claim_text(cj, unicode=unicode).startswith(
        "assuming len(x) == len(y), ")
