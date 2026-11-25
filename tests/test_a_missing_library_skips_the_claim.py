# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language or adaptor that cannot load because a library it needs
is not installed gives a claim the verdict `skipped`, with the library
and the extra that installs it in the reason; any other load failure
keeps the unknown-language message."""
import sys
import textwrap
import warnings

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.languages import LanguageRef, UnknownLanguage, resolve


class _NotInstalled(ImportError):
    def __init__(self, library, extra=None):
        super().__init__(f"No module named {library!r}")
        self.missing_library = library
        if extra is not None:
            self.extra = extra


class _Entry:
    def __init__(self, name, error):
        self.name, self.value, self._error = name, f"pkg.mod:{name}", error

    def load(self):
        raise self._error


def shout(s: str) -> str:
    """Upper-cased."""
    return s.upper()


def _reset():
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()
    for table in ("_UNLOADED_LANGUAGES", "_UNLOADED_ADAPTORS"):
        getattr(languages, table, {}).clear()


@pytest.fixture
def broken_language(monkeypatch):
    def install(error):
        monkeypatch.setattr(languages, "_discovered_languages",
                            lambda: {"yamlish": _Entry("yamlish", error)})
        monkeypatch.setattr(languages, "_discovered_adaptors", lambda: ())
        _reset()
    yield install
    _reset()


@pytest.fixture
def broken_adaptor(tmp_path, monkeypatch):
    pkg = tmp_path / "shopx"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(textwrap.dedent("SCHEMA = {'type': 'object'}\n"))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("shopx", "shopx.models"):
        sys.modules.pop(name, None)
    monkeypatch.setattr(languages, "_discovered_languages", lambda: {})

    def install(error):
        monkeypatch.setattr(languages, "_discovered_adaptors",
                            lambda: (_Entry("schema", error),))
        _reset()
    yield install
    _reset()
    for name in ("shopx", "shopx.models"):
        sys.modules.pop(name, None)


def _one(language):
    (p,) = check_conjectures(shout, [claim(f"for s in L[{language}], f(s) == f(s)")])
    return p


def test_a_language_missing_its_library_is_skipped_with_the_fix(broken_language):
    broken_language(_NotInstalled("ruamel.yaml", "yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one("yamlish")
    assert p.verdict == "skipped", p.note
    assert ("L[yamlish] needs ruamel.yaml, which is not installed; "
            "install mathema-language[yaml]") in p.note
    assert "unknown language" not in p.note


def test_without_an_extra_only_the_library_is_named(broken_language):
    broken_language(_NotInstalled("ruamel.yaml"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one("yamlish")
    assert p.verdict == "skipped"
    assert "L[yamlish] needs ruamel.yaml, which is not installed" in p.note
    assert "install mathema-language" not in p.note


def test_a_load_failure_without_the_attributes_keeps_today_message(broken_language):
    broken_language(ImportError("boom"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one("yamlish")
    assert p.verdict == "unknown"
    assert "needs mathema-language: unknown language L[yamlish]" in p.note
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(UnknownLanguage) as info:
            resolve(LanguageRef("yamlish"))
    assert not hasattr(info.value, "reason")


def test_an_adaptor_missing_its_library_is_skipped_with_the_fix(broken_adaptor):
    broken_adaptor(_NotInstalled("jsonschema", "schema"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one("shopx.models.SCHEMA")
    assert p.verdict == "skipped", p.note
    assert ("L[shopx.models.SCHEMA] needs jsonschema, which is not installed; "
            "install mathema-language[schema]") in p.note


def test_an_adaptor_failure_without_the_attributes_keeps_today_message(broken_adaptor):
    broken_adaptor(ImportError("boom"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one("shopx.models.SCHEMA")
    assert p.verdict == "unknown"
    assert "needs mathema-language: unknown language" in p.note


def test_nothing_extra_is_printed(broken_language, capsys):
    broken_language(_NotInstalled("ruamel.yaml", "yaml"))
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        _one("yamlish")
    out = capsys.readouterr()
    assert (out.out, out.err) == ("", "")
    assert [str(w.message) for w in seen if "failed to load" not in str(w.message)] == []
