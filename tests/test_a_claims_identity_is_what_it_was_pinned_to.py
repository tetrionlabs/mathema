# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's identity today. `mathema.spec.fingerprint_text` is the text
two claims share exactly when they are the same claim, and
`mathema.spec.claims_fingerprint` is the twelve-hex digest of a claim
set: the grammar, then per claim (sorted by name) its identity text, its
name, route, grammar and tolerance. The values pinned here are those of
a few fixed claim sets; the corpus test pins the identity of every
shipped claim text.
"""
import pytest

from mathema.conjecture import claim
from mathema.spec import claims_fingerprint, fingerprint_text

BASE = {"name": "law", "statement": "for x in [0, 1], f(x) >= 0"}


def test_a_claim_set_has_the_fingerprint_it_had():
    assert claims_fingerprint([BASE]) == "b077da5b041d"
    assert claims_fingerprint([]) == claims_fingerprint([])


@pytest.mark.parametrize("changed,expected", [
    ({"route": "derive", "tolerance": 0.5}, "08278bc76fc1"),
    ({"name": "law2"}, "19d6827fbfda"),
])
def test_the_name_route_and_tolerance_are_part_of_the_identity(changed, expected):
    assert claims_fingerprint([{**BASE, **changed}]) == expected
    assert expected != claims_fingerprint([BASE])


@pytest.mark.parametrize("spelling", [
    {"statement": "∀ x ∈ [0, 1], f(x) ≥ 0"},
    {"statement": "f(x) >= 0",
     "domain": {"x": {"lo": 0, "hi": 1, "closed_lo": True, "closed_hi": True}}},
])
def test_the_spelling_of_a_claim_is_not_part_of_its_identity(spelling):
    assert claims_fingerprint([{**BASE, **spelling}]) == "b077da5b041d"


def test_the_set_is_sorted_by_name_before_it_is_hashed():
    other = {"name": "other", "statement": "for x in [0, 2], f(x) >= 0"}
    assert claims_fingerprint([BASE, other]) == claims_fingerprint([other, BASE])


def test_the_identity_text_is_the_canonical_ascii_rendering():
    cj = claim("∀ x ∈ [0, 1] ⊂ ℝ, f(x) ≥ 0")
    assert fingerprint_text(cj) == "for x in [0.0, 1.0] : float, f(x) >= 0"
