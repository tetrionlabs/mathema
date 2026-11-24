# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim mathema cannot store fails its function's row in the sweep.

When the stored text mathema writes for a claim does not read back as
the claim, the function's row in the structured report is not passed
and carries the defect as a problem, and the claim's earlier record
row, kept on disk as it was, appears in the row as unchecked this run
rather than at the verdict it was recorded with.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest

KEY = "cspkg.mod.tag"

_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)
'''

_CLAIMS = r"""
cspkg.mod.tag:
  claims:
    - name: two_literals
      statement: "for x in {\"a\"}, f(x, '}\"', t='s') == 1"
    - name: plain
      statement: 'for x in {"a"}, f(x, t="ab") == 2'
"""


def _forget():
    for name in [m for m in sys.modules if m == "cspkg" or m.startswith("cspkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "cspkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def test_the_key_row_fails_and_the_kept_row_reads_as_unchecked(project,
                                                              monkeypatch):
    from mathema import grammar
    from mathema.verify import verify_project
    first = verify_project(root=str(project))
    assert not first.problems, first.problems
    monkeypatch.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
    out = verify_project(root=str(project), all=True)
    row = {r["key"]: r for r in out.keys}[KEY]
    assert row["passed"] is False, row
    assert any("two_literals" in p and "defect in mathema" in p
               for p in row["problems"]), row["problems"]
    claims = {c["claim"]: c for c in row["claims"]}
    kept = claims["two_literals"]
    assert kept["verdict"] == "unchecked", kept
    assert kept["recorded_verdict"] == "proven", kept
    assert kept["stance"] != "supported", kept
    assert claims["plain"]["verdict"] == "proven"
