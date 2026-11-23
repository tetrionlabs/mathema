# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A string member of a domain set is read as written, and a backslash
in it is reported.

`for s in {"\\t"}` binds `s` to the two characters between the quotes,
a backslash and a t, as it always has: a domain value's escapes are not
decoded. Where the same text read as an expression literal would name
something else (`f("\\t")` passes a tab), `mathema verify` says so in a
note naming the member and both readings. The stored text writes each
member so it reads back as the same value.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.conjecture import claim
from mathema.domain import _as_domain
from mathema.spec import canonical_claim_text
from mathema.verify import domain_escape_note


def _members(statement: str) -> set:
    bound = claim(statement).domain["s"]
    return {v for p in _as_domain(bound).pieces if isinstance(p, frozenset)
            for v in p}


@pytest.mark.parametrize("written, value", [
    ('"\\t"', "\\t"),
    ('"\\\\"', "\\\\"),
    ('"\\q"', "\\q"),
    ('"a\\nb"', "a\\nb"),
    ('"plain"', "plain"),
])
def test_a_domain_value_is_the_text_between_its_quotes(written, value):
    statement = f"for s in {{{written}}}, f(s) == 1"
    assert _members(statement) == {value}
    stored = canonical_claim_text(claim(statement))
    assert _members(stored) == {value}, stored
    assert canonical_claim_text(claim(stored)) == stored


@pytest.mark.parametrize("written, expression, shown", [
    ("\\t", "\t", "as an expression literal the same text reads as a tab (U+0009)"),
    ("\\q", None, "the same text does not read as an expression literal"),
])
def test_the_note_names_both_readings(written, expression, shown):
    note = domain_escape_note("k", "c", written, expression)
    assert f'the domain value "{written}" is read as written' in note, note
    assert "a backslash (U+005C)" in note, note
    assert note.endswith(shown), note


_MOD = '''
def width(s: str) -> int:
    """The number of characters in s."""
    return len(s)
'''

KEY = "dexpkg.mod.width"


def _forget():
    for name in [m for m in sys.modules if m == "dexpkg" or m.startswith("dexpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "dexpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "d.claims.yaml").write_text(yaml.safe_dump({KEY: {"claims": [
        {"name": "two_characters", "statement": 'for s in {"\\t"}, f(s) == 2'},
        {"name": "plain", "statement": 'for s in {"ab"}, f(s) == 2'}]}}))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def test_verify_reads_the_member_as_written_and_says_so(project):
    from mathema.verify import verify_project
    out = verify_project(root=str(project))
    assert not out.problems, out.problems
    notes = [ln for ln in out.lines if "is read as written" in ln]
    assert len(notes) == 1 and "'two_characters'" in notes[0], out.lines
    assert "a tab (U+0009)" in notes[0], notes[0]
    entry = yaml.safe_load((project / ".mathema" / "verified"
                            / f"{KEY}.yaml").read_text())[KEY]
    rows = {r["name"]: r for r in entry["claims"]}
    assert rows["two_characters"]["verdict"] in ("proven", "holds"), rows
