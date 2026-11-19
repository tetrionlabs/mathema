# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A string in a domain set reads its escapes as an expression literal does.

`for s in {"\\t"}` binds `s` to a tab, the value `f("\\t")` passes: a
backslash escape names the character Python's string literal names, in
a domain value and in an expression alike. A backslash itself is
written doubled (`"\\\\t"` is a backslash and a t). An escape that
names no character is an error naming the member. The stored text
writes each value so it reads back as the same value.

A record an earlier release wrote read each escape as its two
characters: the claim is checked again on the values it now names, with
a note saying how a domain value's escape now reads.
"""
import ast
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.conjecture import InvalidConjecture, claim
from mathema.domain import _as_domain
from mathema.spec import canonical_claim_text

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _members(statement: str) -> set:
    bound = claim(statement).domain["s"]
    return {v for p in _as_domain(bound).pieces if isinstance(p, frozenset)
            for v in p}


@pytest.mark.parametrize("written, value", [
    ('"\\t"', "\t"),
    ('"\\n"', "\n"),
    ('"\\""', '"'),
    ("'\\''", "'"),
    ('"\\\\"', "\\"),
    ('"\\\\t"', "\\t"),
    ('"\\u0000"', "\x00"),
    ('"\\x41"', "A"),
    ('"{\\"op\\": \\"new\\"}"', '{"op": "new"}'),
    ('"plain"', "plain"),
    ('"é→"', "é→"),
])
def test_a_domain_value_names_what_the_expression_literal_names(written, value):
    statement = f"for s in {{{written}}}, f(s) == 1"
    assert _members(statement) == {value}
    assert ast.literal_eval(written) == value
    stored = canonical_claim_text(claim(statement))
    assert _members(stored) == {value}, stored
    assert canonical_claim_text(claim(stored)) == stored


def test_a_doubled_backslash_is_one_backslash_in_both_places():
    domain = _members('for s in {"a\\\\b"}, f(s) == 1')
    assert domain == {"a\\b"}
    expression = claim('f("a\\\\b") == 1')
    stored = canonical_claim_text(expression)
    assert stored == 'f("a\\\\b") = 1'


def test_a_member_with_no_escape_is_stored_as_before():
    assert canonical_claim_text(claim('for s in {"a", "b c"}, f(s) == 1')) \
        == 'for s in {"a", "b c"}, f(s) = 1'


@pytest.mark.parametrize("member", ['"\\q"', '"a\\zb"', '"\\N{NO SUCH NAME}"'])
def test_an_escape_naming_no_character_is_an_error_naming_the_member(member):
    with pytest.raises(InvalidConjecture) as caught:
        claim(f"for s in {{{member}}}, f(s) == 1")
    assert member in str(caught.value), str(caught.value)
    assert "escape" in str(caught.value), str(caught.value)


_MOD = '''
def width(s: str) -> int:
    """The number of characters in s."""
    return len(s)
'''

_CLAIMS = r"""
epkg.mod.width:
  claims:
    - name: one_character
      statement: 'for s in {"\t", "\n"}, f(s) == 1'
    - name: plain
      statement: 'for s in {"ab"}, f(s) == 2'
"""
KEY = "epkg.mod.width"


def _run(tmp_path, env, *args, old=False):
    setup = ("from mathema._scan import _LEGACY_DOMAIN_ESCAPES; "
             "_LEGACY_DOMAIN_ESCAPES.set(True); ") if old else ""
    return subprocess.run(
        [sys.executable, "-c",
         f"import sys; {setup}from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _rows(tmp_path):
    record = tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"
    return {r.get("name"): r for r in yaml.safe_load(record.read_text())[KEY]["claims"]}


def test_a_claim_recorded_under_the_raw_reading_is_checked_again(tmp_path):
    pkg = tmp_path / "epkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "e.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    old = _run(tmp_path, env, "verify", old=True)
    assert _rows(tmp_path)["one_character"]["verdict"] == "falsified", old.stdout
    run = _run(tmp_path, env, "verify")
    assert "re-authored" not in run.stdout and "could not be read" not in run.stdout, run.stdout
    notes = [ln for ln in run.stdout.splitlines() if "backslash escape" in ln]
    assert len(notes) == 1 and "'one_character'" in notes[0], run.stdout
    assert '"\\\\t"' in notes[0], notes[0]
    rows = _rows(tmp_path)
    assert rows["one_character"]["verdict"] in ("proven", "holds"), rows["one_character"]
    assert rows["plain"]["verdict"] in ("proven", "holds"), rows["plain"]
    again = _run(tmp_path, env, "verify")
    assert again.returncode == 0, again.stdout + again.stderr
    assert "backslash escape" not in again.stdout, again.stdout
