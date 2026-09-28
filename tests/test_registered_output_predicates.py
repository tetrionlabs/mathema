# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A registered claim family can own a new output-contract predicate.

The output vocabulary is open at the family seam the way the safety
vocabulary is: a family registered under a name shaped like
`output_<slug>` or `is_<slug>_output` contributes that name to the
grammar (the claim parses with an `f(...)` subject) and to the route
tables (the claim adjudicates on the family's probe), without any edit
to core's static tables, which keep meaning core's own vocabulary."""
import pytest

from mathema import families, routes
from mathema.claim_families import OutputPredicateFamily
from mathema.claims import check_conjectures, claim
from mathema.conjecture import InvalidConjecture
from mathema.spec import render_claim_text


def _short(text: str) -> str:
    """The first three characters."""
    return text[:3]


@pytest.fixture
def short_family():
    family = OutputPredicateFamily("output_is_short", lambda out: len(out) <= 3)
    families.register("output_is_short", family)
    try:
        yield family
    finally:
        families._REGISTRY.pop("output_is_short", None)


def test_a_registered_output_predicate_parses_with_an_expression_subject(short_family):
    cj = claim('for text in {"a", "abcdef"}, output_is_short(f(text))')
    assert cj.relation == "output_is_short" and cj.lhs == "f(text)"
    (p,) = check_conjectures(_short, [cj])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.route == "probe:algorithmic"


def test_the_vocabulary_reflects_registration(short_family):
    assert "output_is_short" in routes.output_predicates()
    assert "output_is_short" in routes.examine_predicates()
    assert "output_is_short" in routes.route_capabilities("examine")
    assert "output_is_short" not in routes.OUTPUT_PREDICATES


def test_the_claim_renders_back_to_itself(short_family):
    cj = claim('for text in {"a", "abcdef"}, output_is_short(f(text))')
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert "output_is_short(f(text))" in shown
        assert claim(shown).relation == "output_is_short"


def test_an_unregistered_output_predicate_still_fails_loudly():
    with pytest.raises(InvalidConjecture):
        claim("output_is_totally_novel(f(x))")
