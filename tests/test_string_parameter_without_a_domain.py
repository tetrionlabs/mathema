# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim over a string parameter with no stated domain has no
honest sampling story, the same as the automatic probes: it is skipped
with the `string-domain-missing` gap, naming the parameter and the
spelling that fixes it, rather than falsified on numbers the function
was never meant to take. A finite set of strings, and the arbitrary
input family, still run."""
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    def label(s: str) -> str:
        """Upper case, stripped."""
        return s.strip().upper()

    def maybe_label(s: "str | None") -> str:
        """A dash for none, else upper case."""
        if s is None:
            return "-"
        return s.strip().upper()
'''


@pytest.fixture
def mod(tmp_path):
    import importlib.util
    import sys
    p = tmp_path / "string_domain_fns.py"
    p.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("string_domain_fns", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["string_domain_fns"] = m
    spec.loader.exec_module(m)
    return m


@pytest.mark.usefixtures("without_language_package")
@pytest.mark.parametrize("name", ["label", "maybe_label"])
def test_a_string_claim_with_no_domain_is_skipped_with_the_gap(mod, name):
    (p,) = check_conjectures(getattr(mod, name), [claim("f(f(s)) == f(s)", route="probe")])
    assert p.verdict == "skipped", (p.verdict, p.note, p.counterexample)
    assert p.meta.get("mathema.probe_gap") == "string-domain-missing"
    assert "'s'" in p.note and "for s in" in p.note


def test_a_finite_set_of_strings_still_runs(mod):
    (p,) = check_conjectures(mod.label, [claim('for s in {"a", " b "}, f(f(s)) == f(s)')])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)


def test_the_arbitrary_input_family_still_runs(mod):
    (p,) = check_conjectures(mod.label, [claim("is_arbitrary_input_safe(s)")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note, p.counterexample)


def _callable_row(fn):
    from mathema.analysis import analyze_source
    from mathema.probing import probe
    return next(p for p in probe(fn, analyze_source(fn)) if p.name == "callable")


def test_the_hint_offers_a_string_language_when_one_is_installed(mod):
    from mathema.languages import StringLanguage, register_language, unregister_language
    register_language("unicode", StringLanguage("unicode", char_ok=lambda c: True, pool="abé"))
    try:
        row = _callable_row(mod.label)
    finally:
        unregister_language("unicode")
    assert row.verdict == "skipped"
    assert "'for s in L[unicode], ...'" in row.note, row.note


def test_the_hint_names_a_finite_set_when_no_string_language_is_installed(mod):
    from mathema.languages import resolves
    if resolves("unicode"):
        pytest.skip("a string language is installed")
    row = _callable_row(mod.label)
    assert "L[unicode]" not in row.note and 'for s in {"a", "b"}' in row.note, row.note
