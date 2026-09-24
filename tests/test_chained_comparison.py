# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Chained comparisons `a <= b <= c`: decomposed into conjoined
pairwise links, each adjudicated by the ordinary single-relation path
and folded (proven iff every link proves, falsified as soon as any
link does). Renders as the full chain and round-trips."""
import math

import pytest

from mathema.conjecture import claim, check_conjectures, InvalidConjecture
from mathema.spec import render_claim_text


def gm2(a, b):
    return math.sqrt(a * b)


def dbl(x):
    return 2 * x


def _verdict(fn, law, route="derive"):
    return check_conjectures(fn, [claim(law, route=route)])[0]


def test_power_mean_chain_holds_on_both_routes():
    law = ("for a in [0.1,10], b in [0.1,10], "
           "2/(1/a+1/b) <= f(a,b) <= (a+b)/2")
    assert _verdict(gm2, law).verdict in ("proven", "holds")
    assert _verdict(gm2, law, route="probe").verdict == "holds"


def test_provable_numeric_chain_proves_every_link():
    p = _verdict(dbl, "for x in [1,10], 1 <= f(x) <= 21")
    assert p.verdict == "proven"


def test_a_false_link_falsifies_the_chain_and_names_it():
    p = _verdict(gm2, "for a in [0.1,10], b in [0.1,10], 0 <= f(a,b) <= 0.001")
    assert p.verdict == "falsified"
    assert "link 2" in (p.counterexample or "") + p.note


def test_three_link_chain():
    p = _verdict(dbl, "for x in [1,10], 0 <= x <= f(x) <= 21")
    assert p.verdict == "proven"


def test_equality_in_a_chain_is_rejected_clearly():
    with pytest.raises(InvalidConjecture, match="ordering relations"):
        claim("for x in [1,10], f(x) == 2*x == x+x")


def test_comma_joined_relations_are_rejected_clearly():
    with pytest.raises(InvalidConjecture, match="one relation"):
        claim("for x in [1,10], f(x) >= 2, f(x) <= 20")


def test_chain_renders_full_and_round_trips():
    law = "for a in [0.1,10], b in [0.1,10], 2/(1/a+1/b) <= f(a,b) <= (a+b)/2"
    cj = claim(law)
    assert len(cj.links) == 2
    for unicode in (True, False):
        rendered = render_claim_text(cj, unicode=unicode)
        assert len(claim(rendered).links) == 2   # full chain survives
    # verdict round-trips through the rendered form
    v1 = _verdict(gm2, law)
    v2 = _verdict(gm2, render_claim_text(cj, unicode=False))
    assert v1.verdict == v2.verdict


def test_uppercase_abs_min_max_are_accepted_synonyms():
    def absval(x):
        return abs(x)
    assert _verdict(absval, "for x in [-5,5], Abs(f(x)) == Abs(x)").verdict \
        == "proven"


# --- a chained comparison in the FUNCTION BODY (distinct from a claim
#     chain above): `return lo <= x <= hi` is the conjunction Python
#     evaluates, and the lift accepts it rather than forcing the
#     `lo <= x and x <= hi` spelling that ruff would re-chain. ----------

def _unit(x):
    return 0.0 <= x <= 1.0


def test_body_chained_comparison_is_derivable():
    inside = _verdict(_unit, "for x in [0.2, 0.8], f(x) == 1")
    assert inside.verdict == "proven"
    assert inside.route == "derive"
    outside = _verdict(_unit, "for x in [2, 5], f(x) == 0")
    assert outside.verdict == "proven"
    assert outside.route == "derive"


def test_body_chain_indicator_is_bounded_zero_one():
    p = _verdict(_unit, "for x in [-5, 5], 0 <= f(x) <= 1")
    assert p.verdict == "proven"


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _clip01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


@pytest.mark.parametrize("fn, route", [(_logistic, "probe"),
                                       (_clip01, "best")])
def test_a_chain_reports_the_route_its_links_report(fn, route):
    # the chain's route names the mechanism that decided it, the same
    # stamp each link gets as a claim of its own
    chained = _verdict(fn, "for x in [-5, 5], 0 <= f(x) <= 1", route=route)
    singles = [_verdict(fn, law, route=route) for law in
               ("for x in [-5, 5], 0 <= f(x)", "for x in [-5, 5], f(x) <= 1")]
    assert chained.verdict in ("proven", "holds")
    assert all(s.verdict == chained.verdict for s in singles)
    link_routes = {s.route for s in singles}
    subroutes = {r for r in link_routes if ":" in r}
    expected = (link_routes.pop() if len(link_routes) == 1
                else subroutes.pop())
    assert chained.route == expected, (chained.route, link_routes)
