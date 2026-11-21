# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A regular-language definition holds only texts, so a language whose
`contains()` also admits a value that is not a text (None, a number)
is not what its definition states, and no proof rests on it: a
validator claim or a relation over it is not proven. An honest
language of texts is still proven, and its proof lists `<L> holds only
texts` among its assumptions, checked."""
import re

import pytest

import _text_validators as T
from mathema.languages import register_language, unregister_language

pytest.importorskip("z3")

_A = re.compile(r"a+")
A_PLUS = T.exact(T.rep(T.lit("a"), 1, None))


def plain(s):
    if not _A.fullmatch(s):
        raise ValueError(s)
    return s


def or_empty(s):
    if not _A.fullmatch(s or ''):
        raise ValueError(s)
    return s


def predicate(s):
    return _A.fullmatch(s) is not None


class _AlsoSeven(T.Defined):
    """Strings of a's, and also None and the number 7."""

    def contains(self, value):
        return value is None or value == 7 or (
            isinstance(value, str) and value != "" and set(value) <= {"a"})


def _texts_of_a(s):
    return isinstance(s, str) and s != "" and set(s) <= {"a"}


ALSO_SEVEN = _AlsoSeven("asornone", None, A_PLUS)
HONEST = T.Defined("as", _texts_of_a, A_PLUS)


@pytest.fixture(autouse=True)
def served():
    T.serve()
    for language in (ALSO_SEVEN, HONEST):
        register_language(language.name, language)
    T.PATTERNS[(_A.pattern, "fullmatch")] = T.rep(T.lit("a"), 1, None)
    T._COMPILED[_A.pattern] = _A
    try:
        yield
    finally:
        T.PATTERNS.pop((_A.pattern, "fullmatch"), None)
        T._COMPILED.pop(_A.pattern, None)
        for language in (ALSO_SEVEN, HONEST):
            unregister_language(language.name)
        T.unserve()


SHAPES = [(plain, "for s in L[{}], f(s) == s"), (or_empty, "for s in L[{}], f(s) == s"),
          (predicate, "for s in L[{}], f(s) == True"), (None, "L[{}] subset L[as]")]


@pytest.mark.parametrize("fn,text", SHAPES, ids=["plain", "or_empty", "predicate", "subset"])
def test_a_language_admitting_a_non_text_proves_nothing(fn, text):
    row = T.row(fn or plain, text.format("asornone"))
    assert row.verdict != "proven", (row.verdict, row.sketch)


@pytest.mark.parametrize("fn,text", SHAPES, ids=["plain", "or_empty", "predicate", "subset"])
def test_an_honest_language_of_texts_is_still_proven(fn, text):
    row = T.row(fn or plain, text.format("as"))
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    texts = row.meta["mathema.assumptions"]["texts"]
    assert {"statement": "L[as] holds only texts", "status": "checked"}.items() <= texts[0].items()


def test_the_refusal_names_the_value_that_is_no_text():
    row = T.row(plain, "for s in L[asornone], f(s) == s")
    said = (row.sketch or "") + (row.note or "")
    assert "is a member of L[asornone]" in said and "holds only texts" in said, said
