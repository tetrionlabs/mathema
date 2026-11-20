# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each claim row states the statement text rules it was written under.

A row written by this release carries `mathema.statement_text` in its
meta. A row kept from the record on disk (a claim mathema could not
store this run) keeps the stamp it had, or none when an earlier release
wrote it, and the record's `lineage.statement_text` is the earliest
rules among its rows (absent when a row states none). The next run
reads a kept row of an earlier release under that release's rules, so
its old text is not mistaken for a re-authored claim.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.spec import STATEMENT_TEXT_RELEASE

KEY = "rbpkg.mod.tag"

_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)
'''

_CLAIMS = r"""
rbpkg.mod.tag:
  claims:
    - name: two_literals
      statement: "for x in {\"a\"}, f(x, '}\"', t='s') == 1"
    - name: plain
      statement: 'for x in {"a"}, f(x, t="ab") == 2'
"""


def _forget():
    for name in [m for m in sys.modules if m == "rbpkg" or m.startswith("rbpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "rbpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _entry(root):
    path = root / ".mathema" / "verified" / f"{KEY}.yaml"
    return yaml.safe_load(path.read_text())[KEY]


def _rows(root):
    return {r["name"]: r for r in _entry(root)["claims"]}


def _stamp(row):
    return (row.get("meta") or {}).get("mathema.statement_text")


def test_a_fresh_record_stamps_each_row_and_its_lineage(project):
    from mathema.verify import verify_project
    assert not verify_project(root=str(project)).problems
    rows = _rows(project)
    assert _stamp(rows["two_literals"]) == STATEMENT_TEXT_RELEASE
    assert _stamp(rows["plain"]) == STATEMENT_TEXT_RELEASE
    assert _entry(project)["lineage"]["statement_text"] == STATEMENT_TEXT_RELEASE


def test_a_kept_row_of_an_earlier_release_is_read_under_its_rules(project,
                                                                monkeypatch):
    from mathema import grammar
    from mathema._scan import legacy_quoting
    from mathema.verify import verify_project
    with legacy_quoting():
        verify_project(root=str(project))
    old = _rows(project)["two_literals"]
    assert _stamp(old) is None
    with monkeypatch.context() as m:
        m.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
        verify_project(root=str(project), all=True)
    rows = _rows(project)
    assert rows["two_literals"]["statement"] == old["statement"]
    assert _stamp(rows["two_literals"]) is None
    assert _stamp(rows["plain"]) == STATEMENT_TEXT_RELEASE
    assert "statement_text" not in _entry(project)["lineage"]
    out = verify_project(root=str(project))
    assert not any("re-authored" in p for p in out.problems), out.problems
    rows = _rows(project)
    assert "mathema.pending_supersession" not in (rows["two_literals"].get("meta") or {})
    assert rows["two_literals"]["verdict"] == "proven", rows["two_literals"]
    assert _stamp(rows["two_literals"]) == STATEMENT_TEXT_RELEASE
    assert _entry(project)["lineage"]["statement_text"] == STATEMENT_TEXT_RELEASE


def test_a_kept_row_of_this_release_keeps_its_stamp(project, monkeypatch):
    from mathema import grammar
    from mathema.verify import verify_project
    assert not verify_project(root=str(project)).problems
    with monkeypatch.context() as m:
        m.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
        verify_project(root=str(project), all=True)
    rows = _rows(project)
    assert _stamp(rows["two_literals"]) == STATEMENT_TEXT_RELEASE
    assert _entry(project)["lineage"]["statement_text"] == STATEMENT_TEXT_RELEASE


def test_the_row_stamp_decides_lenient_reading_for_that_row():
    from mathema.sync import written_under_earlier_text
    entry = {"lineage": {"statement_text": STATEMENT_TEXT_RELEASE}}
    stamped = {"meta": {"mathema.statement_text": STATEMENT_TEXT_RELEASE}}
    unstamped = {"meta": {}}
    assert written_under_earlier_text(entry, stamped) is False
    assert written_under_earlier_text(entry, unstamped) is False
    assert written_under_earlier_text({"lineage": {}}, unstamped) is True
    assert written_under_earlier_text({"lineage": {}}, stamped) is False
    earlier = {"meta": {"mathema.statement_text": "0.6.6.1"}}
    assert written_under_earlier_text(entry, earlier) is True
