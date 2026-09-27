# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language may supply a derive strategy for claims quantified over
it: a `derive` method, found through any refinements wrapped around the
language, is handed the claim's parameter, sides, relation, the
functions the claim binds and the refinements in force. A proof it
returns is the claim's derive verdict, its route named by the
mechanism the strategy states (`derive:<mechanism>`). Anything else it
returns, raises, or a disproof it claims, leaves the claim to the
probe, since a disproof is only ever an executed witness."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import (RefinedLanguage, StringLanguage, derive_strategy,
                               register_language, register_refinement, unregister_language,
                               unregister_refinement)
from mathema.symbolic._proof_support import ProofResult

CALLS: list = []


class _Strategic(StringLanguage):
    """Letters, with a derive strategy whose answer each test sets."""

    answer: object = None

    def derive(self, **request):
        CALLS.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


WORDS = _Strategic("strategic_words", char_ok=str.isalpha, pool="ab")


def vowels(language, interval):
    """A refinement on the number of vowels, for these tests."""
    return RefinedLanguage(language, "vowels", interval,
                           measure=lambda s: sum(c in "aeiou" for c in s),
                           plain=lambda n: "a" * n)


@pytest.fixture
def words():
    register_language("strategic_words", WORDS)
    register_refinement("vowels", vowels)
    CALLS.clear()
    try:
        yield WORDS
    finally:
        WORDS.answer = None
        unregister_language("strategic_words")
        unregister_refinement("vowels")


def a_count(s) -> int:
    """How many a's the text has."""
    return s.count("a")


def _check(text):
    (p,) = check_conjectures(a_count, [claim(text)])
    return p


def test_a_proof_from_the_strategy_is_the_derive_verdict(words):
    words.answer = ProofResult("proven", sketch="counted by the stub",
                               meta={"mathema.derive_route": "stub"})
    p = _check("for s in L[strategic_words], f(s) >= 0")
    assert (p.verdict, p.route) == ("proven", "derive:stub"), (p.verdict, p.route, p.note)
    assert p.sketch == "counted by the stub"


def test_the_strategy_is_handed_the_claim_and_the_refinements(words):
    words.answer = ProofResult("proven", sketch="stub", meta={"mathema.derive_route": "stub"})
    _check("for s in L[strategic_words, vowels <= 3], f(s) >= 0")
    (request,) = CALLS
    assert request["param"] == "s"
    assert (request["lhs"], request["relation"], request["rhs"]) == ("f(s)", ">=", "0")
    assert request["functions"]["f"] is a_count and request["functions"]["a_count"] is a_count
    assert request["refinements"] == {"vowels": (0, 3)}


def test_the_strategy_is_found_through_refinements(words):
    refined = vowels(vowels(WORDS, (0, 5)), (1, 3))
    hook, refinements = derive_strategy(refined)
    assert hook == WORDS.derive and refinements == {"vowels": (1, 3)}
    assert derive_strategy(StringLanguage("plain", char_ok=str.isalpha)) is None


@pytest.mark.parametrize("answer", [
    None,
    ProofResult("undecided", sketch="the stub could not"),
    ProofResult("unliftable", sketch="outside the stub's class"),
    ProofResult("disproven", sketch="the stub claims a disproof"),
    ValueError("the stub broke"),
])
def test_anything_but_a_proof_leaves_the_claim_to_the_probe(words, answer):
    words.answer = answer
    p = _check("for s in L[strategic_words], f(s) >= 0")
    assert p.verdict == "holds" and p.route.startswith("probe"), (p.verdict, p.route, p.note)


def test_a_proof_never_lands_on_a_false_claim_through_the_probe_s_back(words):
    words.answer = ProofResult("unliftable", sketch="outside")
    p = _check("for s in L[strategic_words], f(s) >= 1")
    assert p.verdict == "falsified", (p.verdict, p.note)
