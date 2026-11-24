# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each note for an earlier release's stored text says what it moved.

A character a note shows is named (a tab, U+0009), not written as a
second spelling of an escape. A claim whose record moved in its
quoting and its negation, and that holds a domain value with a
backslash, gets every note that applies.
"""
import importlib
import subprocess
import sys
import textwrap
from contextlib import ExitStack

import pytest
import yaml

from mathema.verify import _value_in_words

KEY = "qnpkg.mod.tag"

_MOD = '''
def tag(x: str, a: str = "", b: str = "") -> int:
    """Number of arguments given as non-empty."""
    return int(bool(a)) + int(bool(b))
'''

_CLAIM = ("for x in {\"\\t\", \"q\"}, f(x, '}\"', 's') - 1 "
          "== (not (x == \"z\" and x == \"r\"))")


@pytest.mark.parametrize("value, shown", [
    ("\t", "a tab (U+0009)"),
    ("\n", "a newline (U+000A)"),
    ("\x00", "a null character (U+0000)"),
    ("A", "'A' (U+0041)"),
    ("a\tb", "'a', a tab (U+0009), 'b'"),
    ("\\t", "a backslash (U+005C), 't'"),
])
def test_a_note_names_the_character(value, shown):
    assert _value_in_words(value) == shown


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
    from mathema._scan import legacy_not_parentheses, legacy_quoting
    from mathema.verify import verify_project
    with ExitStack() as stack:
        for legacy in (legacy_quoting, legacy_not_parentheses):
            stack.enter_context(legacy())
        verify_project(root=str(project))
    out = verify_project(root=str(project))
    assert not any("re-authored" in p for p in out.problems), out.problems
    escape = [ln for ln in out.lines if "is read as written" in ln]
    assert len(escape) == 1 and "a tab (U+0009)" in escape[0], out.lines
    assert any("string literal is corrected" in ln for ln in out.lines), out.lines
    assert any("negated relation is rewritten" in ln for ln in out.lines), out.lines

