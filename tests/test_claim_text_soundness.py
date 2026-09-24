# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim grammar either reads a claim as exactly what was written or
refuses it. Every accepted spelling here is held to four checks: its
canonical text is a fixed point, both display renderings reparse to the
same canonical claim, the declared layer (`declare` then
`entry_claims`) rebuilds the same canonical claim, and a real function
gets the same verdict from the claim before and after the round trip.
Every refused spelling raises `InvalidConjecture` with a message that
says what to write instead."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.spec import (canonical_claim_text, declare, entry_claims,
                          fingerprint_text, render_claim_text)


def _verdict(fn, cj):
    (probe,) = check_conjectures(fn, [cj], extensive=False)
    return probe.verdict


def assert_round_trips(law, fn=None):
    """The four round-trip checks, returning the canonical text."""
    cj = claim(law)
    canon = canonical_claim_text(cj)
    assert canonical_claim_text(claim(canon)) == canon, "canonical drifts"
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert canonical_claim_text(claim(shown)) == canon, (
            f"display {shown!r} reparses to a different claim")
    (declared,) = entry_claims({"claims": [declare(cj)]})
    assert canonical_claim_text(declared) == canon, "declared layer drifts"
    if fn is not None:
        before = _verdict(fn, claim(law))
        assert _verdict(fn, claim(canon)) == before
        for unicode in (True, False):
            assert _verdict(fn, claim(render_claim_text(cj, unicode=unicode))) \
                == before
        assert _verdict(fn, declared) == before
    return canon


def five(x: float) -> float:
    return 5.0


def pick(r: float, mode: str) -> float:
    if mode == "alpha":
        return r
    raise ValueError(mode)


def labelled(m1: float, label: str) -> float:
    if label == "m":
        return m1
    raise ValueError(label)


# -- boolean connectives -------------------------------------------------

@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) >= 1 and f(x) <= 2",
    "for x in [0, 1], f(x) >= 1 or f(x) <= 2",
    "for x in [0, 1], f(x) >= 0 and 1 > 2",
    "f(x) >= not x",
    "f(x) >= x and 1",
])
def test_a_boolean_connective_between_relations_is_refused(law):
    with pytest.raises(InvalidConjecture, match="its own claim"):
        claim(law)


def test_the_false_conjunction_no_longer_holds():
    # read with Python precedence this was f(x) >= (1 and f(x) <= 2),
    # which a constant 5 satisfies
    with pytest.raises(InvalidConjecture):
        claim("for x in [0, 1], f(x) >= 1 and f(x) <= 2")
    assert _verdict(five, claim("for x in [0, 1], 1 <= f(x) <= 2")) \
        == "falsified"


def test_a_parenthesised_boolean_value_is_still_a_value():
    canon = assert_round_trips("f(a, b) == (a <= b and b <= 1)")
    assert "and" in canon


# -- string literals ------------------------------------------------------

def test_a_greek_word_inside_quotes_is_not_a_parameter():
    law = 'for r in [0, 1], f(r, "alpha") >= 0'
    canon = assert_round_trips(law, pick)
    assert '"alpha"' in canon or "'alpha'" in canon
    shown = render_claim_text(claim(law), unicode=True)
    assert "α" not in shown
    assert _verdict(pick, claim(law)) in ("proven", "holds")


def test_a_let_alias_never_substitutes_inside_quotes():
    law = 'let m = m1, for m1 in [0, 1], f(m, "m") >= 0'
    canon = assert_round_trips(law, labelled)
    assert "'m'" in canon or '"m"' in canon
    assert "(m1)'" not in canon


@pytest.mark.parametrize("law, literal", [
    ('f(x, "a^b") == 1', "a^b"),
    ('f(x, "≤") == 1', "≤"),
    ('f(x, "x!") == 1', "x!"),
    ('f(x, "|a|") == 1', "|a|"),
    ('f(x) == "a, b"', "a, b"),
    ('"a<=b" == f(x)', "a<=b"),
])
def test_grammar_sugar_never_rewrites_a_string_value(law, literal):
    canon = assert_round_trips(law)
    assert f"'{literal}'" in canon


def test_an_ascii_greek_name_and_its_letter_stay_two_parameters():
    law = "for theta in [0, 1], θ in [2, 3], f(theta, θ) >= 0"
    canon = assert_round_trips(law)
    shown = render_claim_text(claim(law), unicode=True)
    assert "let θ = theta" not in shown
    assert set(claim(shown).domain) == {"theta", "θ"}
    assert "theta" in canon and "θ" in canon


# -- comment marks ---------------------------------------------------------

@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) >= 1 # and f(x) <= 2",
    "# only a comment",
])
def test_a_hash_is_refused_rather_than_truncating_the_claim(law):
    with pytest.raises(InvalidConjecture, match="`#`"):
        claim(law)


def test_a_hash_inside_a_string_value_is_data():
    assert_round_trips('f(x, "a # b") >= 0')
