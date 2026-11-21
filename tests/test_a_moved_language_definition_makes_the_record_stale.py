# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verified record of a claim over a language is stale once the
language's definition moves. Each row of such a claim carries the hash
of the regular-language definition each named language stated when the
row was written; verify compares them with the hashes the languages
state now and names the language whose definition moved. A language
stating no definition is not stamped."""
import importlib
import os
import re
import subprocess
import sys
import textwrap

import pytest

from mathema import regular
from mathema.conjecture import check_conjectures, claim
from mathema.languages import (StringLanguage, register_language, unregister_language,
                               unregister_predicate)

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


def test_a_verdict_resting_on_a_run_of_membership_is_never_fresh(
        tmp_path, monkeypatch, slugdef):
    pytest.importorskip("z3")
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    (tmp_path / "claims" / "lmod.claims.yaml").write_text(textwrap.dedent("""
        lmod.same:
          claims:
            - name: wider_than_one_word
              statement: 'L[slugdef] not subset {"a"}'
    """))
    first = _entry(verify_project(str(tmp_path)), "lmod.same")
    assert first["why"] == "no baseline record"
    again = _entry(verify_project(str(tmp_path)), "lmod.same")
    assert again["why"] == ("the verdict rests on running the membership of L[slugdef], "
                            "which the record does not stamp")


def test_a_moved_definition_is_one_of_the_triggers_that_invalidate_a_record():
    from mathema.transitions import OWN_TRIGGERS
    from mathema.verify import _fired_triggers
    quiet = dict(form=False, claims=False, defaults=False, pseudo_infinity=False,
                 definitions=False, provenance=None, library_version=None, premises=False,
                 dependency=False)
    assert _fired_triggers(**quiet, language_definition=None) == []
    assert _fired_triggers(**quiet, language_definition="L[slugdef]") == ["language-definition"]
    assert "language-definition" in OWN_TRIGGERS


#: a module a temporary project imports: it registers a base language of
#: every text and a made-up word, `reads as`, that reads `PAT.fullmatch`
#: for patterns of the form `[<ranges>]+` and states their definitions
_WORDS_MODULE = '''
import json
import re

from mathema.languages import (PredicateWord, StringLanguage, register_language,
                               register_predicate)

ALL = [[0, 0x10FFFF]]
ANY = {"op": "repeat", "arg": {"op": "chars", "ranges": ALL}, "min": 0, "max": None}


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


class Defined:
    def __init__(self, name, accepts, definition):
        self._base = StringLanguage(name, char_ok=lambda c: True, pool="ab1")
        self.name, self._accepts, self._definition = name, accepts, definition

    def __getattr__(self, attr):
        return getattr(self._base, attr)

    def contains(self, value):
        return isinstance(value, str) and bool(self._accepts(value))

    def to_json(self):
        return {"name": self.name, "definition": self._definition}


def _class_plus(pattern):
    """The node for a pattern `[a-z0-9]+`: one or more of its ranges."""
    ranges = [[ord(lo), ord(hi)] for lo, hi in re.findall(r"(.)-(.)", pattern[1:-2])]
    return {"op": "repeat", "arg": {"op": "chars", "ranges": ranges}, "min": 1, "max": None}


def _reads(callee):
    pattern = getattr(callee, "__self__", None)
    if isinstance(pattern, re.Pattern) and callee.__name__ == "fullmatch":
        return (json.dumps(pattern.pattern),)
    return None


def _refine(language, arguments, negated):
    pattern = re.compile(json.loads(arguments[0]))
    node = {"op": "inter", "args": [language.to_json()["definition"]["language"],
                                    _class_plus(pattern.pattern)]}
    return Defined(f"{language.name}, reads as ({arguments[0]})",
                   lambda s: language.contains(s) and pattern.fullmatch(s) is not None,
                   _exact(node))


register_language("anytext", Defined("anytext", lambda s: True, _exact(ANY)))
register_predicate(PredicateWord("reads as", _refine, reads_call=_reads))
'''

_VALIDATOR_MODULE = '''
import re

import stale_words  # noqa: F401

_PAT = re.compile(r"{pattern}")


def check(text: str) -> str:
    """Return text if it matches, else raise ValueError."""
    if not _PAT.fullmatch(text):
        raise ValueError(text)
    return text
'''

_CLAIM = 'for text in L[anytext], raises(f(text + "\\n"), ValueError)'


def _validator_project(root, pattern):
    (root / "stale_words.py").write_text(_WORDS_MODULE)
    (root / "stale_validator.py").write_text(_VALIDATOR_MODULE.replace("{pattern}", pattern))
    (root / "claims").mkdir(exist_ok=True)
    (root / "claims" / "stale_validator.claims.yaml").write_text(
        "stale_validator.check:\n  claims:\n    - name: refuses_a_newline\n"
        f"      statement: '{_CLAIM}'\n      route: derive\n")


def test_a_validator_decided_through_its_membership_statement_stamps_that_language(
        tmp_path, monkeypatch):
    pytest.importorskip("z3")
    monkeypatch.syspath_prepend(str(tmp_path))
    _validator_project(tmp_path, "[a-z]+")
    for name in ("stale_words", "stale_validator"):
        sys.modules.pop(name, None)
    try:
        module = importlib.import_module("stale_validator")
        (row,) = check_conjectures(module.check, [claim(_CLAIM, route="derive")])
        assert row.verdict == "proven", (row.verdict, row.note)
        assert set(row.meta["mathema.language_definitions"]) == {
            "L[anytext]", 'L[anytext, reads as ("[a-z]+")]'}
        assert row.meta["mathema.language_definitions"]['L[anytext, reads as ("[a-z]+")]'] \
            == row.meta["mathema.smt"]["definitions"]['L[anytext, reads as ("[a-z]+")]']
    finally:
        unregister_language("anytext")
        unregister_predicate("reads as")
        for name in ("stale_words", "stale_validator"):
            sys.modules.pop(name, None)


def _verify_in_a_new_process(root):
    """The output of `mathema verify` on `root`, run as its own process
    with the project and this repository on its path."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), repo])}
    run = subprocess.run(
        [sys.executable, "-c", "import sys; from mathema.cli import main; "
                               "sys.argv[0] = 'mathema'; raise SystemExit(main())",
         "verify", "--root", str(root), "--lenient"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=600)
    return run.stdout + run.stderr


def test_an_edited_pattern_makes_the_validators_record_stale_in_a_second_process(tmp_path):
    pytest.importorskip("z3")
    _validator_project(tmp_path, "[a-z]+")
    first = _verify_in_a_new_process(tmp_path)
    assert "stale_validator.check: no baseline record" in first, first
    second = _verify_in_a_new_process(tmp_path)
    assert "1 unchanged since the last run" in second, second
    _validator_project(tmp_path, "[a-z0-9]+")
    third = _verify_in_a_new_process(tmp_path)
    assert ('stale_validator.check: the definition of L[anytext, reads as ("[a-z]+")] moved'
            in third), third
