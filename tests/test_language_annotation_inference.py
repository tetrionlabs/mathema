# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter's own annotation infers a language domain when a
registered language adaptor turns the annotation into a language: `str`
into the package's unicode language, a schema class into the language
of its rows. It fills a missing domain only, a stated binding always
wins, the note names the adaptor, and with no adaptor installed nothing
is inferred (today's behaviour)."""
import textwrap

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ")


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def str_adaptor(monkeypatch):
    """An adaptor that turns the `str` annotation into `letters`."""
    def adapt(obj):
        return LETTERS if obj is str else None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("text", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    register_language("letters", LETTERS)
    try:
        yield
    finally:
        unregister_language("letters")
        languages._loaded_adaptors.cache_clear()


def _load(tmp_path, body, name="infer_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_str_annotation_infers_the_adaptor_s_language(tmp_path, str_adaptor):
    mod = _load(tmp_path, '''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    ''')
    (p,) = check_conjectures(mod.same, [claim("f(s) == s")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "inferred s in L[letters] from its own str annotation (adaptor text)" in p.note


def test_a_stated_binding_wins(tmp_path, str_adaptor):
    mod = _load(tmp_path, '''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    ''')
    (p,) = check_conjectures(mod.same, [claim('for s in {"x", "y"}, f(s) == s')])
    assert "inferred" not in p.note


def test_without_an_adaptor_nothing_is_inferred(tmp_path, monkeypatch):
    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: ())
    languages._loaded_adaptors.cache_clear()
    try:
        mod = _load(tmp_path, '''
            def same(s: str) -> str:
                """The text, unchanged."""
                return s
        ''')
        (p,) = check_conjectures(mod.same, [claim("f(s) == s")])
        assert "inferred" not in p.note
        assert p.verdict != "holds"
    finally:
        languages._loaded_adaptors.cache_clear()


def test_a_literal_annotation_keeps_its_finite_set(tmp_path, str_adaptor):
    mod = _load(tmp_path, '''
        from typing import Literal

        def pick(mode: Literal["a", "b"]) -> str:
            """The mode, unchanged."""
            return mode
    ''')
    (p,) = check_conjectures(mod.pick, [claim("f(mode) == mode")])
    assert "from its own annotation's stated values" in p.note
    assert "adaptor" not in p.note
