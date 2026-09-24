# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`ε` (also `eps`, `epsilon`, `\\epsilon`) in a claim is the claim's
tolerance: the declared `tolerance` when there is one, else the default
1e-9 that `==` and `~=` use. It is never a free variable to sample, on
either route, and every spelling round-trips through the canonical text
and the declared layer unchanged."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.spec import (canonical_claim_text, declare, entry_claims,
                          render_claim_text)

_SPELLINGS = ["ε", "eps", "epsilon", "\\epsilon"]


def exact(x: float) -> float:
    return x


def tiny_gap(x: float) -> float:
    return x + 1e-10


def small_gap(x: float) -> float:
    return x + 1e-7


def _law(eps: str) -> str:
    return f"for x in [0, 1], abs(f(x) - x) <= {eps}"


@pytest.mark.parametrize("eps", _SPELLINGS)
def test_each_spelling_is_a_canonical_fixed_point(eps):
    cj = claim(_law(eps))
    for render in (lambda c: canonical_claim_text(c),
                   lambda c: render_claim_text(c, unicode=True),
                   lambda c: render_claim_text(c, unicode=False)):
        once = render(cj)
        assert render(claim(once)) == once, once


@pytest.mark.parametrize("eps", _SPELLINGS)
def test_epsilon_is_not_renamed_as_a_parameter(eps):
    assert "let " not in render_claim_text(claim(_law(eps)), unicode=True)


@pytest.mark.parametrize("eps", _SPELLINGS)
def test_each_spelling_survives_the_declared_layer(eps):
    cj = claim(_law(eps), tolerance=1e-6)
    (back,) = entry_claims({"claims": [declare(cj)]})
    assert canonical_claim_text(back) == canonical_claim_text(cj)
    assert back.tolerance == 1e-6


@pytest.mark.parametrize("eps", _SPELLINGS)
@pytest.mark.parametrize("route,supported", [("derive", "proven"),
                                             ("probe", "holds")])
def test_with_no_declared_tolerance_epsilon_is_the_default(eps, route, supported):
    for fn in (exact, tiny_gap):
        (p,) = check_conjectures(fn, [claim(_law(eps), route=route)])
        assert p.verdict == supported, (fn.__name__, p.verdict, p.counterexample)
    (p,) = check_conjectures(small_gap, [claim(_law(eps), route=route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


@pytest.mark.parametrize("route,supported", [("derive", "proven"),
                                             ("probe", "holds")])
def test_a_declared_tolerance_is_what_epsilon_means(route, supported):
    (p,) = check_conjectures(small_gap, [claim(_law("ε"), route=route,
                                               tolerance=1e-6)])
    assert p.verdict == supported, (p.verdict, p.counterexample)


@pytest.mark.parametrize("key", ["tolerance_epsilon", "tolerance_eps_ascii",
                                 "tolerance_epsilon_word",
                                 "tolerance_epsilon_latex"])
def test_the_lexicon_entries_prove_against_their_example(key):
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
    fn, keys = EXAMPLE_FUNCTIONS["nearly_identity"]
    assert key in keys
    (p,) = check_conjectures(fn, [claim(LEXICON[key], route="derive")])
    assert p.verdict == "proven", (key, p.verdict, p.note)


def shift_eps(x: float, eps: float) -> float:
    return x + eps


def shift_epsilon(x: float, epsilon: float) -> float:
    return x + epsilon


def shift_greek(x: float, ε: float) -> float:
    return x + ε


@pytest.mark.parametrize("fn,name", [(shift_eps, "eps"),
                                     (shift_epsilon, "epsilon"),
                                     (shift_greek, "ε")])
@pytest.mark.parametrize("route", ["derive", "probe"])
def test_a_parameter_named_like_the_tolerance_stays_a_parameter(fn, name, route):
    domain = f"for x in [0, 1], {name} in [0, 0.5], "
    (p,) = check_conjectures(fn, [claim(domain + f"f(x, {name}) - x == {name}",
                                        route=route)])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)
    (q,) = check_conjectures(fn, [claim(domain + f"f(x, {name}) - x == 2 * {name}",
                                        route=route)])
    assert q.verdict == "falsified" and q.counterexample
    once = canonical_claim_text(claim(domain + f"f(x, {name}) - x == {name}"))
    assert canonical_claim_text(claim(once)) == once
