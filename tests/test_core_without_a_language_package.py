# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Core works with no language package installed. With the language,
adaptor and family registries emptied (so this holds in a venv that has
the package too): finite sets of strings adjudicate under the plain
`mathema` grammar, `is_language_defined` runs on core's own string
corpus, the suggestions for a `str` parameter name none of the
package's families, nothing names the package unless the claim writes
`L[...]`, a written `L[unicode]` is unknown (never falsified) with the
unresolved-language gap and the install hint, and a `str` parameter
infers no language, only the type fact `: str`."""
import pytest

import mathema.families as families
import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims

RANK = {"red": 1, "green": 2, "blue": 3}
PACKAGE_NAMES = ("mathema-language", "mathema[language]")
PACKAGE_FAMILIES = ("is_encoding_safe", "is_length_safe", "output_in_language")


def shout(s: str) -> str:
    """Stripped and upper-cased."""
    return s.strip().upper()


def rank(c: str) -> int:
    """The colour's rank."""
    return RANK[c]


def first(s: str) -> str:
    """The first character."""
    return s[0]


@pytest.fixture(autouse=True)
def no_language_package(monkeypatch):
    monkeypatch.setattr(languages, "_discovered_languages", lambda: {})
    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: ())
    monkeypatch.setattr(families, "_discovered_external", lambda: {})
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()
    yield
    languages._load_language.cache_clear()
    languages._loaded_adaptors.cache_clear()


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def _text(p):
    return f"{p.statement} {p.note} {p.counterexample} {p.meta}"


@pytest.mark.parametrize("fn, law, verdict, witness", [
    (shout, 'for s in {"a", " b ", ""}, f(f(s)) == f(s)', "proven", None),
    (rank, 'for c in {"red", "green", "blue"}, 1 <= f(c) <= 3', "proven", None),
    (rank, 'for c in {"red", "mauve"}, f(c) >= 1', "falsified", "c = 'mauve'"),
])
def test_finite_sets_of_strings_adjudicate(fn, law, verdict, witness):
    p = _one(fn, law)
    assert (p.verdict, p.grammar) == (verdict, "mathema"), (p.verdict, p.note)
    if witness is not None:
        assert witness in p.counterexample
    assert "L[" not in p.note


def test_arbitrary_input_safety_runs_on_core_s_own_corpus():
    crash = _one(first, "is_language_defined(s)")
    assert crash.verdict == "falsified", crash.note
    assert crash.counterexample.startswith("s = '' raised IndexError")
    assert _one(shout, "is_language_defined(s)").verdict == "holds"


def test_the_suggestions_name_no_package_family():
    names = [c.name for c in suggest_claims(shout)]
    assert "is_language_defined[s]" in names
    assert not [n for n in names if n.split("[")[0] in PACKAGE_FAMILIES]
    for c in suggest_claims(shout):
        assert not any(name in f"{c.raw} {c.meta}" for name in PACKAGE_NAMES)


@pytest.mark.parametrize("fn, law", [
    (shout, 'for s in {"a", " b ", ""}, f(f(s)) == f(s)'),
    (rank, 'for c in {"red", "mauve"}, f(c) >= 1'),
    (first, "is_language_defined(s)"),
])
def test_nothing_names_the_package_unless_the_claim_writes_a_language(fn, law):
    p = _one(fn, law)
    assert not any(name in _text(p) for name in PACKAGE_NAMES), _text(p)


def test_a_written_language_is_unknown_with_the_install_hint():
    p = _one(shout, "for s in L[unicode], f(f(s)) == f(s)")
    assert p.verdict == "unknown"
    assert p.counterexample is None
    assert p.meta["mathema.probe_gap"] == "language-unresolved"
    assert "needs mathema-language" in p.note
    assert 'pip install "mathema[language]"' in p.note
    assert p.grammar == "mathema/language"


def test_a_str_parameter_infers_no_language():
    p = _one(shout, 'for s in {"a"}, f(s) == f(s)')
    assert "L[" not in p.note and "inferred" not in p.note
    assert "mathema.language" not in (p.meta or {})
