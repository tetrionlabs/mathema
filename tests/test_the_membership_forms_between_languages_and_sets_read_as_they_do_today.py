# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Membership and inclusion spellings over languages, number ranges and
finite sets, pinned to today's reading.

Two groups. The first holds the forms a membership extension is meant to
leave alone: a number range, a named number set or a finite set bound
twice with nothing left to quantify is refused, `x` bound twice before
the statement is refused, and a function applied to a bound name on the
left of `in` reads as a quantified membership claim. The second holds
the forms such an extension changes: the inclusion `L[A] subset L[B]` and
a bound name rebound last are refused today. A change to the second
group is expected and replaces its pins; a change to the first is a
regression.
"""
import pytest

from mathema.conjecture import ConflictingDomainBinding, InvalidConjecture, claim
from mathema.spec import fingerprint_text, render_claim_text

_NO_STATEMENT = ("{!r}: every segment after 'for' parses as a binding, the "
                 "quantifier has no statement left to quantify")


@pytest.mark.parametrize("text", [
    "for x in [0, 1], x in [0, 2]",
    "for n in Z, n in Z",
    "for x in [0, 1], x in R",
])
def test_a_number_domain_bound_twice_with_nothing_left_is_refused(text):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == _NO_STATEMENT.format(text)


def test_a_name_bound_twice_before_the_statement_is_refused():
    with pytest.raises(ConflictingDomainBinding) as raised:
        claim("for x in [0, 1], x in [0, 2], f(x) >= 0")
    assert str(raised.value) == "'x' is bound twice in one quantifier; give it one domain"


@pytest.mark.parametrize("text,rendered", [
    ("for c in L[ascii], f(c) in L[unicode]", "for c in L[ascii], f(c) in L[unicode]"),
    ("for order in L[ascii], f(order) in L[unicode]",
     "for order in L[ascii], f(order) in L[unicode]"),
    ("for k in {1, 2}, f(k) in {1, 2, 3}", "for k in {1, 2}, f(k) in {1, 2, 3}"),
])
def test_a_function_of_the_bound_name_on_the_left_of_in_keeps_its_form(text, rendered):
    cj = claim(text)
    assert render_claim_text(cj, unicode=False) == rendered
    assert fingerprint_text(cj) == rendered
    assert render_claim_text(claim(rendered), unicode=False) == rendered


@pytest.mark.parametrize("text", [
    "for s in L[ascii], s in L[ascii]",
    "for c in L[ascii], c in L[unicode]",
    "for k in {1, 2}, k in {1, 2, 3}",
])
def test_a_language_or_finite_set_rebound_last_is_refused_today(text):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == _NO_STATEMENT.format(text)


@pytest.mark.parametrize("text", [
    "L[ascii] subset L[unicode]",
    "L[ascii] ⊆ L[unicode]",
    "L[a] ⊂ L[b]",
])
def test_an_inclusion_between_two_languages_is_refused_today(text):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == f"no relation (==, !=, <=, >=, <, >) in {text!r}"
