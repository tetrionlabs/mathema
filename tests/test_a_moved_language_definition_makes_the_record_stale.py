# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verified record of a claim over a language is stale once the
language's definition moves. Each row of such a claim carries the hash
of the regular-language definition each named language stated when the
row was written; verify compares them with the hashes the languages
state now and names the language whose definition moved. A language
stating no definition is not stamped."""
import re
import textwrap

import pytest

from mathema import regular
from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

ALL = [[0, 0x10FFFF]]
LOWER = {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]}, "min": 1, "max": None}
LOWER_OR_DIGIT = {"op": "repeat", "arg": {"op": "chars", "ranges": [[48, 57], [97, 122]]},
                  "min": 1, "max": None}


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


class Defined:
    """A language of strings whose persisted form states `definition`
    (none when it is None)."""

    def __init__(self, name, pattern, definition):
        self._base = StringLanguage(name, char_ok=str.isalnum, pool="ab1")
        self.name, self._pattern, self.definition = name, re.compile(pattern), definition

    def __getattr__(self, attr):
        return getattr(self._base, attr)

    def contains(self, value):
        return isinstance(value, str) and self._pattern.fullmatch(value) is not None

    def sample(self, rng):
        return "".join(rng.choice("ab") for _ in range(rng.randint(1, 4)))

    def to_json(self):
        out = {"name": self.name}
        if self.definition is not None:
            out["definition"] = self.definition
        return out


@pytest.fixture
def slugdef():
    language = Defined("slugdef", r"[a-z]+", _exact(LOWER))
    register_language("slugdef", language)
    register_language("plainlang", StringLanguage("plainlang", char_ok=str.isalpha, pool="ab"))
    try:
        yield language
    finally:
        unregister_language("slugdef")
        unregister_language("plainlang")


def _same(s):
    return s


def test_a_row_over_a_defined_language_carries_the_definitions_hash(slugdef):
    (row,) = check_conjectures(_same, [claim("for s in L[slugdef], f(s) == s")])
    assert row.meta["mathema.language_definitions"] == {
        "L[slugdef]": regular.term_hash(_exact(LOWER))}
    (related,) = check_conjectures(_same, [claim("L[slugdef] subset L[slugdef]")])
    assert related.meta["mathema.language_definitions"] == {
        "L[slugdef]": regular.term_hash(_exact(LOWER))}


def test_a_language_stating_no_definition_is_not_stamped(slugdef):
    (row,) = check_conjectures(_same, [claim("for s in L[plainlang], f(s) == s")])
    assert "mathema.language_definitions" not in (row.meta or {})


def _project(tmp_path):
    (tmp_path / "lmod.py").write_text(textwrap.dedent('''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "lmod.claims.yaml").write_text(textwrap.dedent("""
        lmod.same:
          claims:
            - name: unchanged
              statement: 'for s in L[slugdef], f(s) == s'
    """))


def _entry(result, key):
    return {entry["key"]: entry for entry in result.keys}[key]


def test_a_moved_definition_makes_the_record_stale_and_names_the_language(
        tmp_path, monkeypatch, slugdef):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    verify_project(str(tmp_path))
    assert _entry(verify_project(str(tmp_path)), "lmod.same")["why"] == "fresh"
    slugdef.definition = _exact(LOWER_OR_DIGIT)
    moved = _entry(verify_project(str(tmp_path)), "lmod.same")
    assert moved["why"] == "the definition of L[slugdef] moved"
    assert _entry(verify_project(str(tmp_path)), "lmod.same")["why"] == "fresh"
    slugdef.definition = None
    gone = _entry(verify_project(str(tmp_path)), "lmod.same")
    assert gone["why"] == "the definition of L[slugdef] moved"


def test_a_moved_definition_is_one_of_the_triggers_that_invalidate_a_record():
    from mathema.transitions import OWN_TRIGGERS
    from mathema.verify import _fired_triggers
    quiet = dict(form=False, claims=False, defaults=False, pseudo_infinity=False,
                 definitions=False, provenance=None, library_version=None, premises=False,
                 dependency=False)
    assert _fired_triggers(**quiet, language_definition=None) == []
    assert _fired_triggers(**quiet, language_definition="L[slugdef]") == ["language-definition"]
    assert "language-definition" in OWN_TRIGGERS
