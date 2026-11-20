# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each note for an earlier release's stored text says what it moved.

A domain value whose backslash escape now reads as the character it
names is shown with that character named (a tab, U+0009), not as a
second spelling of the same escape. A note with no values to show
prints no empty parentheses. A claim whose record moved in its
quoting, its negation and a domain escape at once gets every note that
applies, not the escape note alone.
"""
import importlib
import subprocess
import sys
import textwrap
from contextlib import ExitStack

import pytest
import yaml

from mathema.verify import domain_escapes_note

KEY = "qnpkg.mod.tag"

_MOD = '''
def tag(x: str, a: str = "", b: str = "") -> int:
    """Number of arguments given as non-empty."""
    return int(bool(a)) + int(bool(b))
'''

_CLAIM = ("for x in {\"\\t\", \"q\"}, f(x, '}\"', 's') - 1 "
          "== (not (x == \"z\" and x == \"r\"))")


@pytest.mark.parametrize("written, value, shown", [
    ('"\\t"', "\t", "a tab (U+0009)"),
    ('"\\n"', "\n", "a newline (U+000A)"),
    ('"\\u0000"', "\x00", "a null character (U+0000)"),
    ('"\\x41"', "A", "'A' (U+0041)"),
    ('"a\\tb"', "a\tb", "'a', a tab (U+0009), 'b'"),
])
def test_the_escape_note_names_the_character(written, value, shown):
    note = domain_escapes_note(KEY, "c", [(written, value)])
    assert f"{written} now reads as {shown}" in note, note


@pytest.mark.parametrize("escapes", [None, []])
def test_an_escape_note_with_no_values_has_no_empty_parentheses(escapes):
    note = domain_escapes_note(KEY, "c", escapes)
    assert "()" not in note and "( " not in note, note
    assert "is now read as the character it names" in note, note


def _forget():
    for name in [m for m in sys.modules if m == "qnpkg" or m.startswith("qnpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "qnpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "q.claims.yaml").write_text(yaml.safe_dump(
        {KEY: {"claims": [{"name": "three", "statement": _CLAIM}]}}))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def test_a_claim_moved_three_ways_gets_every_note(project):
    from mathema._scan import (legacy_domain_escapes, legacy_not_parentheses,
                               legacy_quoting)
    from mathema.verify import verify_project
    with ExitStack() as stack:
        for legacy in (legacy_quoting, legacy_not_parentheses,
                       legacy_domain_escapes):
            stack.enter_context(legacy())
        verify_project(root=str(project))
    out = verify_project(root=str(project))
    assert not any("re-authored" in p for p in out.problems), out.problems
    escape = [ln for ln in out.lines if "backslash escape" in ln]
    assert len(escape) == 1 and "a tab (U+0009)" in escape[0], out.lines
    assert any("string literal is corrected" in ln for ln in out.lines), out.lines
    assert any("negated relation is rewritten" in ln for ln in out.lines), out.lines

