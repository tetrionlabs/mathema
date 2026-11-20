# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each claim shape the validator route now proves is checked a second
way, with no solver: every short text over a small alphabet is placed
by core's derivative matcher (in the domain, in the language the
match accepts) and run through the validator, and none breaks the
claim. A wrong claim of the same shape, or the nearest wrong one, is
falsified, and its counterexample replays: the matcher places it as
the claim needs and the validator, run on it, breaks the claim."""
import ast

import pytest

import _text_validators as T

pytest.importorskip("z3")

#: the characters the texts are made of: the patterns' own and a few
#: outside them
ALPHABET = "abz-:0\n"
LONGEST = 4


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def _value(found):
    """The text a falsified row's counterexample names."""
    _, _, value = found.counterexample.partition(" = ")
    return ast.literal_eval(value)


def _outcome(fn, text):
    """`("returned", value)` or `("raised", exception class)`."""
    try:
        return "returned", fn(text)
    except Exception as e:
        return "raised", type(e)


def _defined_claim_breaks(fn, text):
    kind, value = _outcome(fn, text)
    return kind == "returned" and value != text


def test_every_text_where_a_refusing_validator_is_defined_is_returned():
    for fn, pattern in ((T.check_slug, T.SLUG), (T.check_slug_dollar, T.SLUG_DOLLAR)):
        row = T.row(fn, "for text in L[anytext], assuming f is defined, f(text) == text")
        assert row.verdict == "proven", (fn.__name__, row.verdict, row.sketch)
        checked = 0
        for text in T.enumerated(ALPHABET, LONGEST):
            assert T.in_language("anytext", text)
            kind, _ = _outcome(fn, text)
            assert (kind == "returned") == T.accepted_by(pattern, "match", text), text
            assert not _defined_claim_breaks(fn, text), text
            checked += 1
        assert checked > 2000


def test_without_the_premise_the_counterexample_replays_on_the_matcher():
    row = T.row(T.check_slug, "for text in L[anytext], f(text) == text")
    assert row.verdict == "falsified", (row.verdict, row.note)
    text = _value(row)
    assert T.in_language("anytext", text)
    assert not T.accepted_by(T.SLUG, "match", text)
    assert _outcome(T.check_slug, text)[0] == "raised"


def test_a_match_on_the_text_or_empty_agrees_with_enumeration():
    row = T.row(T.is_person_or_empty, "for actor in L[alnums], f(actor) == False")
    assert row.verdict == "proven", (row.verdict, row.sketch)
    alnum = [t for t in T.enumerated("ap0Z:", LONGEST) if T.in_language("alnums", t)]
    assert len(alnum) > 300
    for text in alnum:
        assert not T.accepted_by(T.PERSON, "fullmatch", text)
        assert T.is_person_or_empty(text) is False, text
    wrong = T.row(T.is_person_or_empty, 'for actor in L[anytext], f("p:" + actor) == False')
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)
    actor = _value(wrong)
    assert T.in_language("anytext", actor)
    assert T.accepted_by(T.PERSON, "fullmatch", "p:" + actor)
    assert T.is_person_or_empty("p:" + actor) is True


def test_a_plain_exception_of_the_package_agrees_with_enumeration():
    row = T.row(T.check_slug_own_error,
                'for text in L[anytext], raises(f(text + "\\n"), ValueError)')
    assert row.verdict == "proven", (row.verdict, row.sketch)
    for text in T.enumerated(ALPHABET, LONGEST):
        assert not T.accepted_by(T.SLUG, "match", text + "\n")
        kind, raised = _outcome(T.check_slug_own_error, text + "\n")
        assert kind == "raised" and issubclass(raised, ValueError), text
    wrong = T.row(T.check_slug_own_error, "for text in L[slugs], raises(f(text), ValueError)")
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)
    text = _value(wrong)
    assert T.in_language("slugs", text) and T.accepted_by(T.SLUG, "match", text)
    assert _outcome(T.check_slug_own_error, text) == ("returned", text)


def test_a_differently_named_variable_agrees_with_enumeration():
    row = T.row(T.is_person, 'let h be L[anytext], f("p:" + h + "z") == False')
    assert row.verdict == "proven", (row.verdict, row.sketch)
    for h in T.enumerated(ALPHABET + "9", LONGEST):
        assert not T.accepted_by(T.PERSON, "fullmatch", "p:" + h + "z")
        assert T.is_person("p:" + h + "z") is False
    wrong = T.row(T.is_person, 'let h be L[anytext], f("p:" + h) == False')
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)
    h = _value(wrong)
    assert T.in_language("anytext", h)
    assert T.accepted_by(T.PERSON, "fullmatch", "p:" + h)
    assert T.is_person("p:" + h) is True
