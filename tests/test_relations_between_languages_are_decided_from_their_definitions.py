# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A relation between two languages that each state a regular-language
definition is decided from the definitions: no string separating them
is a proof, and a string the solver finds is executed against both
languages' own membership before it falsifies anything or proves a
negative relation. The languages here state hand-written definitions
and decide membership with Python's `re`."""
import re

import pytest

from mathema import claim, regular
from mathema.conjecture import check_conjectures
from mathema.languages import StringLanguage, register_language, unregister_language

pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]
LOWER = {"op": "chars", "ranges": [[97, 122]]}
DIGIT = {"op": "chars", "ranges": [[48, 57]]}
DASH = {"op": "literal", "codes": [45]}


def _plus(node):
    return {"op": "repeat", "arg": node, "min": 1, "max": None}


SLUG = _plus({"op": "union", "args": [LOWER, DIGIT, DASH]})
SLUG_DOLLAR = {"op": "concat", "args": [
    SLUG, {"op": "repeat", "arg": {"op": "literal", "codes": [10]}, "min": 0, "max": 1}]}
ANY = {"op": "repeat", "arg": {"op": "chars", "ranges": ALL}, "min": 0, "max": None}


class Defined:
    """A language of strings deciding membership by a compiled pattern
    and stating `definition` in its persisted form."""

    def __init__(self, name, pattern, definition, accepts="fullmatch"):
        self._base = StringLanguage(name, char_ok=lambda c: True, pool="ab")
        self.name, self._definition = name, definition
        self._accepts = getattr(re.compile(pattern), accepts)

    def __getattr__(self, attr):
        return getattr(self._base, attr)

    def contains(self, value):
        return isinstance(value, str) and self._accepts(value) is not None

    def to_json(self):
        return {"name": self.name, "definition": self._definition}


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


_LANGUAGES = (
    Defined("slug", r"[a-z0-9-]+\Z", _exact(SLUG)),
    Defined("slug_again", r"[0-9a-z-]+\Z", _exact(SLUG)),
    # `match` with `$` stops before one final newline, so it admits one
    Defined("slug_dollar", r"[a-z0-9-]+$", _exact(SLUG_DOLLAR), accepts="match"),
    Defined("digits", r"[0-9]+\Z", _exact(_plus(DIGIT))),
    Defined("letters", r"[a-z]+\Z", _exact(_plus(LOWER))),
    # states the slug and admits only letters: its definition is wrong
    Defined("misdefined", r"[a-z]+\Z", _exact(SLUG)),
    # a slug whose definition is two bounds, everything and nothing
    Defined("bounded", r"[a-z0-9-]+\Z",
            {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": False,
             "at_least": ANY, "at_most": {"op": "empty"}}),
    Defined("anything", r"(?s).*", _exact(ANY)),
)
UNDEFINED = StringLanguage("undefined", char_ok=str.isalpha, pool="ab")


@pytest.fixture(autouse=True)
def languages():
    for language in (*_LANGUAGES, UNDEFINED):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (*_LANGUAGES, UNDEFINED):
            unregister_language(language.name)


def _f(x):
    return x


def _row(text):
    (row,) = check_conjectures(_f, [claim(text)])
    return row


@pytest.mark.parametrize("text", [
    "L[slug] subset L[slug_dollar]",
    "L[slug] = L[slug_again]",
    "L[digits] disjoint L[letters]",
    "L[digits] subset L[slug] and L[digits] != L[slug]",
    "L[bounded] subset L[anything]",
    'L[digits] | {"a-b"} subset L[slug]',
    '{"a-b", "7"} subset L[slug]',
    'L[letters] disjoint {"7", "a-b"}',
])
def test_a_relation_with_no_separating_string_is_proven_on_the_smt_route(text):
    row = _row(text)
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.route == "derive"
    assert row.meta["mathema.derive_route"] == "smt"
    assert row.sketch.startswith("smt: membership, regular language: ")


def test_the_solver_alone_finds_the_trailing_newline_and_it_is_executed():
    row = _row("L[slug_dollar] subset L[slug]")
    assert row.verdict == "falsified"
    witness = row.meta["mathema.domain_relation"]["witness"]
    assert witness["executed"] is True
    member = witness["member"]
    assert member.endswith("\n") and re.fullmatch(r"[a-z0-9-]+\n", member)
    assert repr(member) in row.counterexample


@pytest.mark.parametrize("text", [
    "L[slug_dollar] not subset L[slug]",
    "L[slug_dollar] != L[slug]",
    "L[slug] != L[digits]",
])
def test_a_negative_relation_is_proven_by_an_executed_member(text):
    row = _row(text)
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta["mathema.domain_relation"]["witness"]["executed"] is True
    assert row.meta["mathema.derive_route"] == "smt"


@pytest.mark.parametrize("text", [
    "L[slug] disjoint L[slug_dollar]",
    "L[slug] = L[digits]",
    "L[slug] not subset L[slug_dollar]",
    "L[slug] != L[slug_again]",
    '{"A"} subset L[slug]',
])
def test_a_false_relation_is_falsified(text):
    assert _row(text).verdict == "falsified"


def test_a_member_the_languages_do_not_confirm_falsifies_nothing():
    row = _row("L[misdefined] subset L[letters]")
    assert row.verdict == "unknown"
    assert row.note == ("the solver found a string the languages' own membership "
                        "does not confirm, so their definitions decide nothing here")


def test_bounds_too_wide_to_decide_read_unknown():
    assert _row("L[bounded] subset L[slug]").verdict == "unknown"
    assert _row("L[slug] subset L[bounded]").verdict == "unknown"


def test_a_language_stating_no_definition_is_not_decided():
    row = _row("L[undefined] subset L[slug]")
    assert row.verdict == "unknown"
    assert row.note == "a relation over a language has no solver lowering yet"


def test_the_row_records_the_hash_of_each_definition_it_read():
    row = _row("L[slug] subset L[slug_dollar]")
    assert row.meta["mathema.domain_relation"]["definitions"] == {
        "L[slug]": regular.term_hash(_exact(SLUG)),
        "L[slug_dollar]": regular.term_hash(_exact(SLUG_DOLLAR))}


AB_ONLY = {"kind": "regular_language", "version": 1, "alphabet": [[97, 98]], "exact": True,
           "language": {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 98]]},
                        "min": 0, "max": None}}
NO_CHARACTER = {"kind": "regular_language", "version": 1, "alphabet": [], "exact": True,
                "language": {"op": "epsilon"}}


@pytest.fixture
def narrow():
    languages = (Defined("fab", r"[ab]*", AB_ONLY), Defined("onlyempty", r"", NO_CHARACTER))
    for language in languages:
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in languages:
            unregister_language(language.name)


def test_a_listed_string_outside_a_definitions_alphabet_is_still_a_member(narrow):
    row = _row('L[fab] | {"c"} subset L[fab]')
    assert row.verdict == "falsified", (row.verdict, row.sketch)
    assert row.meta["mathema.domain_relation"]["witness"]["member"] == "c"
    assert _row('L[fab] \\ {"a"} subset L[fab]').verdict == "proven"
    assert _row('{"c"} disjoint L[fab]').verdict == "proven"
    assert _row('{"c", "ab"} subset L[fab]').verdict == "falsified"


def test_a_definition_over_no_character_gives_a_verdict(narrow):
    assert _row("L[onlyempty] subset L[fab]").verdict == "proven"
    assert _row('L[onlyempty] = {""}').verdict == "proven"
    assert _row("L[fab] subset L[onlyempty]").verdict == "falsified"
