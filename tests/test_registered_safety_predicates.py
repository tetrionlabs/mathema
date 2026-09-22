# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A registered claim family can own a new safety predicate.

The safety-predicate vocabulary is open at the family seam: a family
registered under a name shaped like `is_<slug>_safe` contributes that
name to the grammar (the claim parses) and to the route tables (the
claim adjudicates through the family's own derive/probe halves),
without any edit to core's static tables. The registered NAME is the
predicate, the same name-is-the-contract rule target resolvers use.
The static tables keep meaning exactly core's own vocabulary.
"""
import pytest

from mathema import families, routes
from mathema.claim_families import SafetyFamily
from mathema.claims import check_conjectures, claim
from mathema.conjecture import InvalidConjecture
from mathema.symbolic import ProofResult


def _gain(x: float) -> float:
    """Twice x."""
    return 2 * x


def _cyber_derive(fn, facts, lhs_src, rhs_src, relation, domain=None,
                  tolerance=None):
    return ProofResult("proven",
                       sketch="every reachable input class was enumerated")


@pytest.fixture
def cyber_family():
    family = SafetyFamily("is_cyber_safe", derive=_cyber_derive)
    families.register("is_cyber_safe", family)
    try:
        yield family
    finally:
        families._REGISTRY.pop("is_cyber_safe", None)


def test_a_registered_predicate_parses_and_adjudicates(cyber_family):
    cj = claim("is_cyber_safe(x)")
    assert cj.relation == "is_cyber_safe" and cj.lhs == "x"
    (p,) = check_conjectures(_gain, [cj])
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "examine"


def test_the_vocabulary_reflects_registration(cyber_family):
    assert "is_cyber_safe" in routes.examine_predicates()
    assert "is_cyber_safe" in routes.safety_predicates()
    assert "is_cyber_safe" in routes.route_capabilities("examine")
    # the static tables keep meaning core's own vocabulary
    assert "is_cyber_safe" not in routes.SAFETY_PREDICATES


def test_an_unregistered_predicate_still_fails_loudly():
    with pytest.raises(InvalidConjecture, match="no relation"):
        claim("is_totally_novel_safe(x)")


def test_a_family_name_not_shaped_like_a_predicate_adds_nothing():
    class _Shape:
        def can_handle(self, fn, facts, claim_name):
            return False

        def routes(self):
            return {}
    families.register("widget_helper", _Shape())
    try:
        assert "widget_helper" not in routes.examine_predicates()
    finally:
        families._REGISTRY.pop("widget_helper", None)
