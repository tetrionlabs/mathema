# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim named `is_defined` whose statement is a region asserts that f
returns on exactly that region (docs/conditional-claims.md). Its stored
statement is the region itself, and name plus statement rebuild the
same claim, through the declared layer and through a verified record."""
import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.spec import canonical_claim_text, declare, entry_claims, fingerprint_text


def discount_factor(x: float) -> float:
    return 1 / (1 - x)


def _same(a, b):
    return ((a.name, a.lhs, a.relation, a.rhs, a.negated)
            == (b.name, b.lhs, b.relation, b.rhs, b.negated))


def test_the_region_is_the_stored_statement():
    cj = claim("1 - x != 0", name="is_defined")
    assert canonical_claim_text(cj) == "1 - x != 0"
    assert fingerprint_text(cj) == "1 - x != 0"


def test_name_and_statement_rebuild_the_same_claim():
    for name in ("is_defined", "is_defined[2]"):
        cj = claim("1 - x != 0", name=name)
        again = claim(canonical_claim_text(cj), name=name)
        assert _same(cj, again)
        (back,) = entry_claims({"claims": [declare(cj)]})
        assert _same(cj, back)


def test_the_pole_itself_is_still_a_falsification_elsewhere():
    probes = {p.name: p for p in mathema.check(discount_factor).probes}
    assert probes["is_pole_safe[x]"].verdict == "falsified"
    assert "x = 1" in probes["is_pole_safe[x]"].counterexample


def test_the_region_claim_adjudicates_as_region_equivalence():
    [p] = check_conjectures(discount_factor, [
        claim("1 - x != 0", name="is_defined", route="derive")])
    assert p.verdict == "proven"
    [q] = check_conjectures(discount_factor, [
        claim("2 - x != 0", name="is_defined", route="derive")])
    assert q.verdict == "falsified"
    assert q.counterexample
