# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The language registry behind `L[<name>]`: a built-in resolves first
and is never overridden, an in-process registration next, then a
`mathema.languages` entry point, then a dotted reference imported and
offered to the `mathema.language_adaptors` adaptors. An unknown name
refuses with the vocabulary and the group to register under, a broken
entry point warns and is skipped, and a registered language must
satisfy the protocol."""
import fractions
import random

import pytest

import mathema.languages as languages
from mathema.domain import LanguageRef
from mathema.languages import (BUILTIN_LANGUAGES, Problem, UnknownLanguage,
                               describe_language, language_problems,
                               language_vocabulary, register_language,
                               resolve, resolve_language, unregister_language)


class _Words:
    name = "words"
    kind = "string"
    level = "finite"

    def __init__(self, *words):
        self.words = words

    def contains(self, value):
        return value in self.words

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "words", value)]

    def sample(self, rng):
        return rng.choice(self.words)

    def members(self, limit):
        return self.words if len(self.words) <= limit else None

    def hazards(self):
        return ()

    def outside(self, rng):
        return "zzz"

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "string", "enum": list(self.words)}


@pytest.fixture
def registered():
    words = _Words("yes", "no")
    register_language("answers", words)
    try:
        yield words
    finally:
        unregister_language("answers")


class _Entry:
    """A stand-in entry point: `name`, `value`, and a `load()`."""

    def __init__(self, name, value, obj=None, error=None):
        self.name, self.value, self._obj, self._error = name, value, obj, error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._obj


@pytest.fixture
def entry_points(monkeypatch):
    """Install fake `mathema.languages` and adaptor entry points."""
    def install(named=(), adaptors=()):
        monkeypatch.setattr(languages, "_discovered_languages",
                            lambda: {ep.name: ep for ep in named})
        monkeypatch.setattr(languages, "_discovered_adaptors",
                            lambda: tuple(adaptors))
        languages._load_language.cache_clear()
        languages._loaded_adaptors.cache_clear()
    yield install
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()


def test_a_builtin_resolves_first():
    language, source = resolve(LanguageRef("ascii"))
    assert language is BUILTIN_LANGUAGES["ascii"]
    assert source == "built-in"


def test_a_builtin_name_cannot_be_registered_over():
    with pytest.raises(ValueError, match="built-in"):
        register_language("ascii", _Words("a"))


def test_a_registered_language_resolves_by_name(registered):
    language, source = resolve("answers")
    assert language is registered and source == "registered"
    assert "answers" in language_vocabulary()
    unregister_language("answers")
    assert "answers" not in language_vocabulary()


def test_a_registered_language_must_satisfy_the_protocol():
    class Broken:
        name = "broken"
        kind = "string"
        level = "finite"

    problems = language_problems(Broken())
    assert any("missing 'contains'" in p for p in problems)
    with pytest.raises(ValueError, match="missing 'contains'"):
        register_language("broken", Broken())


def test_an_unknown_name_refuses_with_the_vocabulary():
    with pytest.raises(UnknownLanguage) as err:
        resolve_language(LanguageRef("nope"))
    message = str(err.value)
    assert "L[nope]" in message and "ascii" in message
    assert "mathema.languages" in message
    assert err.value.vocabulary == language_vocabulary()


def test_an_entry_point_language_resolves_by_name(entry_points):
    words = _Words("up", "down")
    entry_points(named=[_Entry("directions", "pkg.mod:words", obj=words)])
    language, source = resolve("directions")
    assert language is words
    assert source == "entry point pkg.mod:words"
    assert "directions" in language_vocabulary()


def test_a_builtin_wins_over_an_entry_point_of_the_same_name(entry_points):
    entry_points(named=[_Entry("ascii", "pkg.mod:words", obj=_Words("a"))])
    language, source = resolve("ascii")
    assert language is BUILTIN_LANGUAGES["ascii"] and source == "built-in"


def test_a_broken_entry_point_warns_and_is_skipped(entry_points):
    entry_points(named=[_Entry("boom", "pkg.mod:boom",
                               error=ImportError("no such module"))])
    with pytest.warns(UserWarning, match="failed to load"):
        with pytest.raises(UnknownLanguage):
            resolve("boom")


def test_an_entry_point_failing_the_protocol_warns_and_is_skipped(entry_points):
    entry_points(named=[_Entry("half", "pkg.mod:half", obj=object())])
    with pytest.warns(UserWarning, match="does not satisfy"):
        with pytest.raises(UnknownLanguage):
            resolve("half")


def test_a_dotted_reference_goes_through_the_adaptors(entry_points):
    seen = []

    def adapt(obj):
        seen.append(obj)
        return _Words("1/2") if obj is fractions.Fraction else None

    entry_points(adaptors=[_Entry("fractions", "pkg.mod:adapt", obj=adapt)])
    language, source = resolve(LanguageRef("fractions.Fraction"))
    assert seen == [fractions.Fraction]
    assert language.contains("1/2") and source == "adaptor fractions"


def test_a_dotted_reference_no_adaptor_accepts_names_the_group(entry_points):
    entry_points(adaptors=[_Entry("none", "pkg.mod:decline",
                                  obj=lambda obj: None)])
    with pytest.raises(UnknownLanguage, match="no adaptor accepts"):
        resolve(LanguageRef("fractions.Fraction"))
    entry_points()
    with pytest.raises(UnknownLanguage, match="no language adaptor is installed"):
        resolve(LanguageRef("fractions.Fraction"))


def test_a_dotted_reference_that_does_not_import_says_so(entry_points):
    entry_points()
    with pytest.raises(UnknownLanguage, match="does not import"):
        resolve(LanguageRef("no_such_module_anywhere.Thing"))


def test_a_language_object_at_a_dotted_path_resolves_as_itself(monkeypatch):
    words = _Words("a", "b")
    monkeypatch.setattr(fractions, "mathema_test_language", words, raising=False)
    language, source = resolve(LanguageRef("fractions.mathema_test_language"))
    assert language is words and source == "object"


def test_describe_states_name_source_level_kind_and_schema(registered):
    described = describe_language(LanguageRef("answers"))
    assert described == {"name": "answers", "source": "registered",
                         "level": "finite", "kind": "string",
                         "schema": {"type": "string", "enum": ["yes", "no"]}}


def test_builtin_languages_all_satisfy_the_protocol():
    for language in BUILTIN_LANGUAGES.values():
        assert language_problems(language) == []
        assert isinstance(language.sample(random.Random(0)), str)
