# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A length refinement inside a language piece, `L[ascii, len <= 80]`:
the members of the language whose length (in code points, Python's
`len`) lies in the bound. It parses in every spelling (`<=`, `<`, `>=`,
`>`, `in [lo, hi]`), renders back to itself, persists, and is a
language of its own: membership checks the length, samples and hazards
stay inside it, the member one past the bound is its outside draw, and
an adaptor that reads an annotation's `MaxLen(80)` infers it."""
import random
import textwrap
from typing import Annotated

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import (InvalidDomain, LanguageRef, domain_bound_from_json,
                            domain_bound_to_json, domain_contains, parse_binding)
from mathema.languages import (StringLanguage, language_problems, register_language,
                               resolve_language, unregister_language)
from mathema.spec import render_claim_text

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ")


@pytest.fixture
def letters():
    register_language("letters", LETTERS)
    try:
        yield
    finally:
        unregister_language("letters")


def _bound(text):
    return parse_binding(f"s in {text}")[1]


def _ref(text):
    return _bound(text).pieces[0]


@pytest.mark.parametrize("text", [
    "L[letters, len <= 80]", "L[letters, len < 80]", "L[letters, len >= 1]",
    "L[letters, len > 20]", "L[letters, len in [1, 80]]", "L[letters, len in (0, 80]]",
])
def test_every_spelling_parses_and_renders_back_to_itself(letters, text):
    cj = claim(f"for s in {text}, f(s) == s")
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert text in shown, shown
        assert render_claim_text(claim(shown), unicode=unicode) == shown


def test_the_refinement_is_carried_on_the_piece_and_persisted(letters):
    ref = _ref("L[letters, len <= 80]")
    assert isinstance(ref, LanguageRef) and ref.name == "letters"
    assert ref.refinement("len") is not None
    assert repr(ref) == "L[letters, len <= 80]"
    assert domain_bound_from_json(domain_bound_to_json(_bound("L[letters, len <= 80]"))) \
        == _bound("L[letters, len <= 80]")
    assert _ref("L[letters]").refinement("len") is None


def test_membership_counts_code_points(letters):
    b = _bound("L[letters, len <= 3]")
    assert domain_contains("abc", b) and domain_contains("", b)
    assert not domain_contains("abcd", b)
    assert not domain_contains("ab1", b)
    b = _bound("L[letters, len > 2]")
    assert domain_contains("abc", b) and not domain_contains("ab", b)


def test_the_refined_language_is_a_language(letters):
    language = resolve_language(_ref("L[letters, len in [2, 5]]"))
    assert language_problems(language) == []
    rng = random.Random(0)
    for _ in range(100):
        s = language.sample(rng)
        assert LETTERS.contains(s) and 2 <= len(s) <= 5, s
    lengths = {len(h.value) for h in language.hazards()}
    assert lengths and all(2 <= n <= 5 for n in lengths)
    assert {2, 5} <= lengths, "the members at both bounds are hazards"
    outside = language.outside(rng)
    assert LETTERS.contains(outside) and len(outside) in (1, 6), outside


def test_a_bound_nothing_satisfies_is_refused_at_parse(letters):
    with pytest.raises(InvalidDomain, match="no len satisfies"):
        parse_binding("s in L[letters, len in [5, 2]]")
    with pytest.raises(InvalidDomain):
        parse_binding("s in L[letters, len < 0]")


def test_a_key_nothing_serves_is_refused_at_resolution(letters):
    from mathema.languages import UnknownRefinement
    with pytest.raises(UnknownRefinement, match=r"'n'.*known keys are len"):
        resolve_language(_ref("L[letters, n <= 80]"))


def _load(tmp_path, body, name="refine_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_claim_over_the_refinement_never_sees_a_longer_member(tmp_path, letters):
    mod = _load(tmp_path, '''
        def pad(s: str) -> str:
            """Padded to eight characters."""
            return s.ljust(8)
    ''')
    (p,) = check_conjectures(mod.pad, [claim("for s in L[letters, len <= 8], len(f(s)) == 8")])
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    (q,) = check_conjectures(mod.pad, [claim("for s in L[letters], len(f(s)) == 8")])
    assert q.verdict == "falsified", (q.verdict, q.note)


def test_the_member_past_the_bound_tests_the_refusal(tmp_path, letters):
    mod = _load(tmp_path, '''
        def pad(s: str) -> str:
            """Padded to eight characters."""
            return s.ljust(8)

        def checked(s: str) -> str:
            """Padded to eight characters; longer text is refused."""
            if len(s) > 8:
                raise ValueError("at most eight characters")
            return s.ljust(8)
    ''')
    (p,) = check_conjectures(mod.pad, [claim(
        "for s in L[letters, len <= 8], excluded_outside_domain(s)", route="best")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    (q,) = check_conjectures(mod.checked, [claim(
        "for s in L[letters, len <= 8], excluded_outside_domain(s)", route="best")])
    assert q.verdict in ("holds", "proven"), (q.verdict, q.note, q.counterexample)


class MaxLen:
    def __init__(self, max_length):
        self.max_length = max_length


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def text_adaptor(monkeypatch):
    import typing

    from mathema.domain import Interval
    from tests._length_refinement import length

    def adapt(hint):
        if hint is str:
            return LETTERS
        if typing.get_origin(hint) is typing.Annotated and typing.get_args(hint)[0] is str:
            limits = [getattr(m, "max_length", None) for m in typing.get_args(hint)[1:]]
            limits = [n for n in limits if isinstance(n, int)]
            return length(LETTERS, Interval(0.0, float(min(limits)))) if limits else LETTERS
        return None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("text", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    register_language("letters", LETTERS)
    try:
        yield
    finally:
        unregister_language("letters")
        languages._loaded_adaptors.cache_clear()


def test_a_max_length_marker_infers_the_refined_language(text_adaptor):
    def pad(s: Annotated[str, MaxLen(8)]) -> str:
        """Padded to eight characters."""
        return s.ljust(8)

    (p,) = check_conjectures(pad, [claim("len(f(s)) == 8")])
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert "inferred s in L[letters, len <= 8] from" in p.note, p.note


def test_a_language_domain_says_missing_in_both_modes(letters):
    # the empty-set glyph means the empty language to a reader of formal
    # languages, so a language domain spells the missing value as a word
    for unicode in (True, False):
        shown = render_claim_text(claim("for s in L[letters], f(s) == s"), unicode=unicode)
        assert "L[letters]," in shown and "∅" not in shown, shown
        shown = render_claim_text(claim("for s in L[letters] | {missing}, f(s) == s"),
                                  unicode=unicode)
        assert "L[letters]|missing" in shown and "∅" not in shown, shown
    shown = render_claim_text(claim("for x in [0, 1], f(x) >= 0"), unicode=True)
    assert "∪ {None, ∅}" in shown, "a numeric domain keeps its glyph"
