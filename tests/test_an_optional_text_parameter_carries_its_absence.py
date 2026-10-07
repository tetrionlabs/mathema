# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The absence of a text parameter reads the same with and without a
language package. In core `Optional[str]` is `: str|absent`. With a
language adaptor installed, the adaptor is handed the annotation
without its `None` and the absence is added back: `Optional[str]` reads
`L[letters]|absent`. A language domain spells absence as `absent`, the
word every other domain uses. A claim naming a language no package
serves is unknown, with the package named, never falsified."""
import textwrap
from typing import Optional

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import domain_contains, parse_binding, render_domain
from mathema.languages import StringLanguage, register_language, unregister_language

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ")


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def str_adaptor(monkeypatch):
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


@pytest.fixture
def no_language_package(monkeypatch):
    monkeypatch.setattr(languages, "_discovered_languages", lambda: {})
    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: ())
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()
    yield
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_LABEL = '''
    from typing import Optional

    def label(s: Optional[str]) -> str:
        """The text in capitals, or the word none."""
        return "none" if s is None else s.upper()
'''


def label(s: Optional[str]) -> str:
    return "none" if s is None else s.upper()


def test_a_language_domain_spells_absence_as_absent():
    for text in ("L[letters]|absent", "L[letters]|None"):
        name, bound = parse_binding(f"s in {text}")
        assert render_domain(bound, ascii_mode=True) == "L[letters]|absent"
        assert render_domain(bound, ascii_mode=False) == "L[letters]|absent"
        assert domain_contains(None, bound)
    name, bound = parse_binding("s in L[letters]")
    assert render_domain(bound, ascii_mode=True) == "L[letters]"


def test_a_path_bound_spells_absence_as_absent():
    _name, bound = parse_binding("o.note in [0, 1]|None")
    shown = render_domain(bound, ascii_mode=True, words=True)
    assert "|absent" in shown and "None" not in shown, shown


def test_optional_str_completes_to_the_language_with_its_absence(tmp_path, str_adaptor):
    mod = _load(tmp_path, _LABEL, "opt_text_adaptor")
    (p,) = check_conjectures(mod.label, [claim("f(s) == f(s)")])
    assert ("inferred s in L[letters]|absent from its own Optional[str] "
            "annotation (adaptor text)") in (p.note or ""), p.note
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_optional_str_in_core_is_str_with_its_absence(no_language_package):
    (p,) = check_conjectures(label, [claim("f(s) == f(s)")])
    assert "inferred s in : str|absent from its own Optional[str] annotation" \
        in (p.note or ""), p.note
    assert "L[" not in (p.note or "")


def test_a_claim_naming_a_package_language_without_the_package_is_unknown(
        no_language_package):
    (p,) = check_conjectures(label, [claim("for s in L[unicode], f(f(s)) == f(s)")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "mathema-language" in (p.note or ""), p.note
    assert p.counterexample is None
