# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over every text of a language, about a function that is a
pattern validator, is decided from the regular-language definitions of
the domain and of the pattern: proven when no text breaks it, and
falsified by a text the solver finds once the real function, run on
it, breaks the claim.

The validators are the slug check with `$`, which under `match` admits
one final newline, and with `\\Z`, which does not. The definitions are
written by hand and served by an adaptor made for these tests, which
reads the bound method of a compiled pattern (`PAT.match`); no pattern
dialect is compiled here."""
import re
import warnings

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

pytest.importorskip("z3")

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*$")
_SLUG_FIXED = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_UNDEFINED = re.compile(r"(?=a)a")


def check_slug(text: str) -> str:
    """Return text if it is a slug, else raise ValueError."""
    if not _SLUG.match(text):
        raise ValueError(text)
    return text


def check_slug_fixed(text: str) -> str:
    """Return text if it is a slug, else raise ValueError."""
    if not _SLUG_FIXED.match(text):
        raise ValueError(text)
    return text


def is_slug(text: str) -> bool:
    return _SLUG_FIXED.match(text) is not None


def check_undefined(text: str) -> str:
    if not _UNDEFINED.match(text):
        raise ValueError(text)
    return text


def check_and_lower(text: str) -> str:
    if not _SLUG_FIXED.match(text):
        raise ValueError(text)
    return text.lower()


ALL = [[0, 0x10FFFF]]
HEAD = {"op": "chars", "ranges": [[48, 57], [97, 122]]}
TAIL = {"op": "chars", "ranges": [[45, 45], [48, 57], [97, 122]]}
SLUG = {"op": "concat", "args": [HEAD, {"op": "repeat", "arg": TAIL, "min": 0, "max": None}]}
NEWLINE = {"op": "literal", "codes": [10]}
SLUG_THEN_NEWLINE = {"op": "concat", "args": [
    SLUG, {"op": "repeat", "arg": NEWLINE, "min": 0, "max": 1}]}
ANY = {"op": "repeat", "arg": {"op": "chars", "ranges": ALL}, "min": 0, "max": None}


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


class Defined:
    """A language of strings stating `definition` in its persisted
    form, membership decided by `accepts`."""

    def __init__(self, name, accepts, definition):
        self._base = StringLanguage(name, char_ok=lambda c: True, pool="ab")
        self.name, self._accepts, self._definition = name, accepts, definition

    def __getattr__(self, attr):
        return getattr(self._base, attr)

    def contains(self, value):
        return isinstance(value, str) and bool(self._accepts(value))

    def to_json(self):
        return {"name": self.name, "definition": self._definition}


#: the whole-text language each bound method accepts, by pattern and mode
_DEFINITIONS = {
    (_SLUG.pattern, "match"): SLUG_THEN_NEWLINE,
    (_SLUG_FIXED.pattern, "match"): SLUG,
}


def adapt(obj):
    """The language of texts a compiled pattern's bound method accepts,
    for the two patterns these tests define."""
    pattern = getattr(obj, "__self__", None)
    node = _DEFINITIONS.get((getattr(pattern, "pattern", None), getattr(obj, "__name__", "")))
    if not isinstance(pattern, re.Pattern) or node is None:
        return None
    return Defined(f"pattern {pattern.pattern}", obj, _exact(node))


class _Entry:
    name, value = "test_patterns", "tests:adapt"

    @staticmethod
    def load():
        return adapt


ANYTEXT = Defined("anytext", lambda s: True, _exact(ANY))
LINES = Defined("lines", lambda s: s.endswith("\n"),
                _exact({"op": "concat", "args": [ANY, NEWLINE]}))
SLUGS = Defined("slugs", lambda s: _SLUG_FIXED.match(s), _exact(SLUG))
PLAIN = StringLanguage("plain", char_ok=lambda c: True, pool="ab")


@pytest.fixture(autouse=True)
def served(monkeypatch):
    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: (_Entry,))
    languages._loaded_adaptors.cache_clear()
    for language in (ANYTEXT, LINES, SLUGS, PLAIN):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (ANYTEXT, LINES, SLUGS, PLAIN):
            unregister_language(language.name)
        languages._loaded_adaptors.cache_clear()


def _row(fn, text, route="derive"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        (row,) = check_conjectures(fn, [claim(text, route=route)])
    return row


_BENCHMARK = 'for text in L[anytext], raises(f(text + "\\n"), ValueError)'


def test_the_fixed_validator_refuses_every_text_ending_in_a_newline():
    row = _row(check_slug_fixed, _BENCHMARK)
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert row.route == "derive"
    assert row.meta["mathema.derive_route"] == "smt"
    assert row.sketch.startswith("smt: membership, validator pattern "
                                 "re.compile('[a-z0-9][a-z0-9-]*\\\\Z').match: ")


def test_the_dollar_validator_is_falsified_by_a_text_the_solver_finds():
    row = _row(check_slug, _BENCHMARK)
    assert row.verdict == "falsified", (row.verdict, row.note, row.sketch)
    assert row.meta["mathema.derive_route"] == "smt"
    found = re.fullmatch(r"text = '([a-z0-9][a-z0-9-]*)'", row.counterexample)
    assert found, row.counterexample
    assert check_slug(found.group(1) + "\n") == found.group(1) + "\n"


def test_the_solver_alone_finds_the_trailing_newline():
    row = _row(check_slug, "for text in L[lines], raises(f(text), ValueError)")
    assert row.verdict == "falsified", (row.verdict, row.note, row.sketch)
    found = re.fullmatch(r"text = '([a-z0-9][a-z0-9-]*)\\n'", row.counterexample)
    assert found, row.counterexample
    assert _row(check_slug_fixed,
                "for text in L[lines], raises(f(text), ValueError)").verdict == "proven"


@pytest.mark.parametrize("fn,text,verdict", [
    (check_slug_fixed, "for text in L[slugs], f(text) == text", "proven"),
    (check_slug, "for text in L[slugs], f(text) == text", "proven"),
    (check_slug_fixed, "for text in L[anytext], f(text) == text", "falsified"),
    (is_slug, "for text in L[slugs], f(text) == True", "proven"),
    (is_slug, "for text in L[lines], f(text) == False", "proven"),
    (is_slug, "for text in L[anytext], f(text) == True", "falsified"),
    (is_slug, 'for text in L[slugs], f("x-" + text) == True', "proven"),
    (is_slug, 'for text in L[slugs], f("-" + text) == True', "falsified"),
])
def test_the_claims_a_validator_decides(fn, text, verdict):
    row = _row(fn, text)
    assert row.verdict == verdict, (row.verdict, row.note, row.sketch)
    assert row.meta["mathema.derive_route"] == "smt"


def test_the_record_carries_the_hash_of_each_definition_read():
    from mathema import regular
    row = _row(check_slug_fixed, _BENCHMARK)
    assert row.meta["mathema.smt"]["definitions"] == {
        "L[anytext]": regular.term_hash(_exact(ANY)),
        "re.compile('[a-z0-9][a-z0-9-]*\\\\Z').match": regular.term_hash(_exact(SLUG))}


@pytest.mark.parametrize("fn,text,said", [
    (check_undefined, _BENCHMARK, "definition-unread(re.Pattern)"),
    (check_slug_fixed, 'for text in L[plain], raises(f(text + "\\n"), ValueError)',
     "the domain of text states no regular-language definition"),
])
def test_a_definition_nothing_states_leaves_derive_undecided_with_the_reason(fn, text, said):
    row = _row(fn, text)
    assert (row.meta or {}).get("mathema.derive_route") != "smt"
    assert said in (row.sketch or "") + (row.note or "")


@pytest.mark.parametrize("fn,text", [
    (check_and_lower, _BENCHMARK),
    (check_slug_fixed, "for text in L[anytext], raises(f(text.upper()), ValueError)"),
    (check_slug_fixed, 'for text in L[anytext], raises(f(text + "\\n"), TypeError)'),
])
def test_a_function_or_claim_that_does_more_is_not_lowered(fn, text):
    row = _row(fn, text)
    assert (row.meta or {}).get("mathema.derive_route") != "smt"
    assert "smt:" not in (row.sketch or "")
