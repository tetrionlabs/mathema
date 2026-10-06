# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Refinements inside `L[...]` are a seam. Core parses any `key op n`
or `key in [lo, hi]` generically, renders the keys in one canonical
order, persists each under its key, and hands them to the language at
resolution: a key is served by a registered refinement (in the process
or under the `mathema.language_refinements` entry-point group), and an
unknown key is refused then, naming the keys that are known. Core owns
no key. `RefinedLanguage` is the kit a key is built from: a measure,
and optionally the plain and built members of a given measure."""
import random

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import (InvalidDomain, LanguageRef, domain_bound_from_json,
                            domain_bound_to_json, parse_binding)
from mathema.interfaces import extension
from mathema.languages import (RefinedLanguage, StringLanguage, UnknownRefinement,
                               language_problems, refinement_keys, register_language,
                               register_refinement, resolve_language, unregister_language,
                               unregister_refinement)
from mathema.spec import render_claim_text

WORDS = StringLanguage("words", char_ok=str.isalpha, pool="ab")


def vowels(language, interval):
    """A refinement on the number of vowels, for these tests."""
    return RefinedLanguage(language, "vowels", interval,
                           measure=lambda s: sum(c in "aeiou" for c in s),
                           plain=lambda n: "a" * n)


@pytest.fixture
def words():
    register_language("words", WORDS)
    register_refinement("vowels", vowels)
    try:
        yield
    finally:
        unregister_language("words")
        unregister_refinement("vowels")


def same(s):
    """The text, unchanged."""
    return s


def _ref(text):
    return parse_binding(f"s in {text}")[1].pieces[0]


@pytest.mark.parametrize("text", [
    "L[json, depth <= 6]", "L[json, depth < 6]", "L[json, nodes >= 1]", "L[json, nodes > 2]",
    "L[json, children in [1, 5]]", "L[json, children in (0, 5]]",
    "L[json, depth <= 6, nodes <= 200]", "L[ascii, len <= 80]",
])
def test_any_key_parses_and_renders_back(text):
    cj = claim(f"for s in {text}, f(s) == s")
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert text in shown, shown
        assert render_claim_text(claim(shown), unicode=unicode) == shown


def test_keys_render_in_one_order_whatever_order_they_are_written():
    assert repr(_ref("L[json, nodes <= 200, depth <= 6]")) == "L[json, depth <= 6, nodes <= 200]"
    assert _ref("L[json, nodes <= 200, depth <= 6]") == _ref("L[json, depth <= 6, nodes <= 200]")


@pytest.mark.parametrize("text, message", [
    ("L[json, depth <= 6, depth <= 3]", "twice"),
    ("L[json, depth ~ 6]", "key <= n"),
    ("L[json, depth <= 2, depth in [0, 1]]", "twice"),
    ("L[json, depth in [5, 2]]", "no depth satisfies"),
])
def test_a_malformed_refinement_is_refused_at_parse(text, message):
    with pytest.raises(InvalidDomain, match=message):
        parse_binding(f"s in {text}")


def test_every_key_persists_under_its_own_name():
    bound = parse_binding("s in L[json, depth <= 6, nodes <= 200]")[1]
    data = domain_bound_to_json(bound)
    assert set(data["pieces"][0]) == {"language", "depth", "nodes"}
    assert domain_bound_from_json(data) == bound
    legacy = {"language": "ascii", "len": {"lo": 0.0, "hi": 80.0, "closed_lo": True, "closed_hi": True}}
    assert repr(domain_bound_from_json(legacy)) == "L[ascii, len <= 80]"


def test_a_registered_key_refines_the_language(words):
    language = resolve_language(_ref("L[words, vowels <= 2]"))
    assert language_problems(language) == []
    assert language.contains("bab") and not language.contains("aaab")
    assert language.name == "words, vowels <= 2"
    assert [h.value for h in language.hazards()][:2] == ["", "aa"]
    rng = random.Random(0)
    assert all(language.contains(language.sample(rng)) for _ in range(50))
    assert language.outside(rng) == "aaa"
    (problem,) = language.explain("aaab")
    assert problem.predicate == "vowels <= 2"


def test_an_unknown_key_is_refused_at_resolution_naming_the_known_keys(words):
    with pytest.raises(UnknownRefinement, match=r"'depth'.*vowels"):
        resolve_language(_ref("L[words, depth <= 3]"))
    (p,) = check_conjectures(same, [claim("for s in L[words, depth <= 3], f(s) == s")])
    assert p.verdict == "unknown"
    assert p.meta["mathema.probe_gap"] == "language-unresolved"
    assert "mathema.language_refinements" in p.note
    assert "len, depth, nodes and width" in p.note


def test_core_owns_no_key(monkeypatch):
    monkeypatch.setattr(languages, "_discovered_refinements", lambda: {})
    saved = dict(languages._REFINEMENTS)
    languages._REFINEMENTS.clear()
    try:
        assert refinement_keys() == ()
    finally:
        languages._REFINEMENTS.update(saved)


def test_the_seam_is_on_the_extension_surface():
    for name in ("RefinedLanguage", "register_refinement", "unregister_refinement",
                 "refinement_keys", "UnknownRefinement", "REFINEMENT_GROUP"):
        assert name in extension.SURFACE["languages"], name
    assert LanguageRef("json").refinement("depth") is None


def pairs(language, interval):
    """A refinement on the number of letter pairs, whose members only
    ever have an even length."""
    return RefinedLanguage(language, "pairs_len", interval, measure=len,
                           plain=lambda n: "ab" * (n // 2) if n % 2 == 0 else None)


def test_where_no_member_has_the_bound_s_measure_the_nearest_ones_are_visited(words):
    even = StringLanguage("even_words", char_ok=str.isalpha, pool="ab")
    refined = pairs(even, (0, 7))
    assert max(len(h.value) for h in refined.hazards()) == 6
    outside = refined.outside(random.Random(0))
    assert outside == "abababab", outside
