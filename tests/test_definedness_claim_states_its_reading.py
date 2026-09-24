# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim named `is_defined` with a stated region asserts that f
returns on exactly that region, not that the region's relation holds
everywhere. Its statement says so, `f is defined --> <region>`, and
that spelling parses back to the same claim."""
import pytest

import mathema
from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.spec import canonical_claim_text, fingerprint_text


def discount_factor(x: float) -> float:
    return 1 / (1 - x)


def test_the_suggested_region_claim_renders_as_the_definedness_region():
    probes = {p.name: p for p in mathema.check(discount_factor).probes}
    p = probes["is_defined"]
    assert p.verdict == "proven"
    assert p.statement == "f is defined --> 1 - x != 0"


def test_the_pole_itself_is_still_a_falsification_elsewhere():
    probes = {p.name: p for p in mathema.check(discount_factor).probes}
    assert probes["is_pole_safe[x]"].verdict == "falsified"
    assert "x = 1" in probes["is_pole_safe[x]"].counterexample


def test_the_region_spelling_parses_to_the_named_claim():
    cj = claim("f is defined --> 1 - x != 0")
    assert cj.name == "is_defined"
    assert (cj.lhs, cj.relation, cj.rhs) == ("1 - x", "!=", "0")
    assert canonical_claim_text(cj) == "f is defined --> 1 - x != 0"
    assert claim("is_defined(f) --> 1 - x != 0").lhs == cj.lhs
    again = claim(canonical_claim_text(cj))
    assert (again.name, again.lhs, again.relation, again.rhs) == \
        (cj.name, cj.lhs, cj.relation, cj.rhs)


def test_a_numbered_conjunct_keeps_its_name():
    cj = claim("f is defined --> y >= 0", name="is_defined[2]")
    assert cj.name == "is_defined[2]"
    assert canonical_claim_text(cj) == "f is defined --> y >= 0"


def test_the_region_spelling_under_another_name_is_refused():
    with pytest.raises(InvalidConjecture):
        claim("f is defined --> 1 - x != 0", name="pole_free")


def test_the_region_spelling_adjudicates_as_region_equivalence():
    [p] = check_conjectures(discount_factor, [
        claim("f is defined --> 1 - x != 0", route="derive")])
    assert p.verdict == "proven"
    [q] = check_conjectures(discount_factor, [
        claim("f is defined --> 2 - x != 0", route="derive")])
    assert q.verdict == "falsified"


def test_the_rendering_leaves_the_claim_identity_unchanged():
    stored = claim("1 - x != 0", name="is_defined")
    assert fingerprint_text(stored) == "1 - x != 0"
    assert fingerprint_text(claim("f is defined --> 1 - x != 0")) == \
        fingerprint_text(stored)
