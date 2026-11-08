# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The inclusion statement between two languages: `L[A] subset L[B]`
states that every member of L[A] is a member of L[B], and reads as the
quantified `for c in L[A], c in L[B]`. Both spellings are one claim, and
the inclusion is the form every rendering writes back."""
import pytest

from mathema import claim
from mathema.conjecture import InvalidConjecture
from mathema.spec import fingerprint_text, render_claim_text


@pytest.mark.parametrize("text", [
    "L[ascii] subset L[unicode]",
    "L[ascii] ⊆ L[unicode]",
    "for c in L[ascii], c in L[unicode]",
    "∀ s ∈ L[ascii], s ∈ L[unicode]",
])
def test_every_spelling_of_an_inclusion_renders_as_subset(text):
    cj = claim(text)
    assert render_claim_text(cj, unicode=False) == "L[ascii] subset L[unicode]"
    assert render_claim_text(cj, unicode=True) == "L[ascii] ⊆ L[unicode]"


def test_the_two_spellings_are_one_claim():
    assert fingerprint_text(claim("L[ascii] subset L[unicode]")) == \
        fingerprint_text(claim("for c in L[ascii], c in L[unicode]"))


@pytest.mark.parametrize("text", [
    "L[ascii, len <= 8] subset L[unicode]",
    "L[ascii] subset L[unicode, len <= 80]",
])
def test_a_refined_language_keeps_its_refinement_through_a_round_trip(text):
    ascii_text = render_claim_text(claim(text), unicode=False)
    assert ascii_text == text
    unicode_text = render_claim_text(claim(text), unicode=True)
    assert render_claim_text(claim(unicode_text), unicode=False) == text


def test_an_inclusion_is_membership_of_the_bound_member():
    cj = claim("L[ascii] subset L[unicode]")
    (var, bound), = cj.domain.items()
    assert cj.relation == "in" and cj.lhs == var
    assert repr(bound.pieces[0]) == "L[ascii]"
    assert repr(cj.rhs_bound.pieces[0]) == "L[unicode]"


def test_proper_subset_is_refused_with_the_spelling_that_is_accepted():
    with pytest.raises(InvalidConjecture, match=r"proper subset.*L\[a\] subset L\[b\]"):
        claim("L[a] ⊂ L[b]")


@pytest.mark.parametrize("text", [
    "for c in L[ascii], f(c) in L[unicode]",
    'for c in L[ascii] | {""}, c in L[unicode]',
])
def test_a_claim_that_is_not_a_bare_inclusion_keeps_its_quantified_form(text):
    rendered = render_claim_text(claim(text), unicode=False)
    assert rendered.startswith("for c in ")
    assert render_claim_text(claim(rendered), unicode=False) == rendered
