# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that calls a validator on its variable with literal text
added (`f("p:" + h + "0")`) is decided when the texts called on leave
the variable's own language. The question is then one of the term
algebra: whether every text `prefix + h + suffix`, `h` in the
variable's language, is in the language the pattern accepts over all
text, or is outside it. A text the solver finds is run through the real
function before it falsifies, and each verdict is cross-checked by
enumeration on the derivative matcher."""
import ast

import pytest

import _text_validators as T

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def _value(row):
    return ast.literal_eval(row.counterexample.partition(" = ")[2])


@pytest.mark.parametrize("fn,text,verdict", [
    (T.is_person, 'let h be L[twodigits], f("p:" + h) == True', "proven"),
    (T.is_person, 'let h be L[twodigits], f("p:" + h + "0") == False', "proven"),
    (T.is_person, 'let h be L[twodigits], f("p:" + h + "0") == True', "falsified"),
    (T.is_person, 'let h be L[twodigits], f("p" + h) == True', "falsified"),
    (T.check_slug, 'let h be L[slugs], raises(f("a" + h + "\\n"), ValueError)', "proven"),
    (T.check_slug_dollar, 'let h be L[slugs], raises(f("a" + h + "\\n"), ValueError)',
     "falsified"),
])
def test_texts_called_on_outside_the_variables_language_are_decided(fn, text, verdict):
    row = T.row(fn, text)
    assert row.verdict == verdict, (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)


def test_each_verdict_agrees_with_enumeration_on_the_matcher():
    digits = [t for t in T.enumerated("0a9:", 2) if T.in_language("twodigits", t)]
    assert len(digits) == 4
    for h in digits:
        assert T.accepted_by(T.PERSON, "fullmatch", "p:" + h) and T.is_person("p:" + h)
        assert not T.accepted_by(T.PERSON, "fullmatch", "p:" + h + "0")
        assert T.is_person("p:" + h + "0") is False
    wrong = T.row(T.is_person, 'let h be L[twodigits], f("p:" + h + "0") == True')
    h = _value(wrong)
    assert T.in_language("twodigits", h)
    assert T.is_person("p:" + h + "0") is False
    slugs = [t for t in T.enumerated("ab-z", 4) if T.in_language("slugs", t)]
    assert len(slugs) > 20
    for h in slugs:
        assert not T.accepted_by(T.SLUG, "match", "a" + h + "\n")
        with pytest.raises(ValueError):
            T.check_slug("a" + h + "\n")
    dollar = T.row(T.check_slug_dollar, 'let h be L[slugs], raises(f("a" + h + "\\n"), ValueError)')
    h = _value(dollar)
    assert T.in_language("slugs", h) and T.accepted_by(T.SLUG_DOLLAR, "match", "a" + h + "\n")
    assert T.check_slug_dollar("a" + h + "\n") == "a" + h + "\n"


def test_the_reading_is_checked_on_members_of_the_variables_language():
    row = T.row(T.is_person, 'let h be L[twodigits], f("p:" + h) == True')
    reading = [a for a in row.meta["mathema.assumptions"]["definitions"]
               if a["statement"].startswith("is_person accepts a text")]
    assert reading and reading[0]["status"] == "checked", reading
    assert reading[0]["artefact"]["texts run"] >= 100


@pytest.mark.parametrize("text", [
    'let h be L[twodigits], f("p:" + h + h) == True',
    'let h be L[plaintext], f("p:" + h) == True',
])
def test_a_second_copy_or_an_undefined_language_still_declines(text):
    row = T.row(T.is_person, text, route="best")
    assert not T.on_smt(row), (row.verdict, row.sketch)
