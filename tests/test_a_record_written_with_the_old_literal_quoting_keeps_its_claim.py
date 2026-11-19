# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record written with the old literal quoting still records its claim.

Releases up to 0.6.6.1 re-quoted the string literals of a stored
statement with one pattern over the whole text, so a statement with two
literals in different quote styles could be stored with its quotes
paired wrongly: `f(x, body="a: {\\"c\\":\\"\\"}", t="s") == 1` was
stored as `f(x, body='a: {"c":""}", t="s') = 1`, which reads as a
different claim, and `f(x, 'a"b\\'c') == 1` as text that does not read
at all. A record holding that text is the record of the authored claim:
the next run checks the claim as written and records it under the
current text, with no supersession and no unreadable record.
"""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "qpkg.mod.tag"

_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)
'''

_CLAIMS = r"""
qpkg.mod.tag:
  claims:
    - name: two_literals
      statement: 'for x in {"a"}, f(x, body="a: {\"c\":\"\"}", t="s") == 1'
    - name: both_quotes
      statement: "for x in {\"a\"}, f(x, 'a\"b\\'c') == 0"
    - name: plain
      statement: 'for x in {"a"}, f(x, t="ab") == 2'
"""


def _project(tmp_path, names=("two_literals", "both_quotes", "plain")):
    pkg = tmp_path / "qpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    data = yaml.safe_load(_CLAIMS)
    data[KEY]["claims"] = [c for c in data[KEY]["claims"] if c["name"] in names]
    (tmp_path / "claims" / "q.claims.yaml").write_text(yaml.safe_dump(data))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _run(tmp_path, env, *args, old_quoting=False):
    """`mathema <args>` in its own process; with `old_quoting`, every
    statement it writes is quoted the way releases up to 0.6.6.1 wrote
    it, so the run leaves the store such a release left."""
    setup = ("from mathema._scan import _LEGACY_QUOTING; "
             "_LEGACY_QUOTING.set(True); ") if old_quoting else ""
    return subprocess.run(
        [sys.executable, "-c",
         f"import sys; {setup}from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _record_path(tmp_path):
    return tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"


def _rows(tmp_path):
    entry = yaml.safe_load(_record_path(tmp_path).read_text())[KEY]
    return {c.get("name"): c for c in entry["claims"]}


def _statements(tmp_path):
    return {n: r.get("statement") for n, r in _rows(tmp_path).items()}


def _old_and_current(tmp_path, env):
    """The rows an old-quoting run writes, then the rows a run of this
    release writes into an empty store."""
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    current = _rows(tmp_path)
    _record_path(tmp_path).unlink()
    old = _run(tmp_path, env, "verify", old_quoting=True)
    assert old.returncode == 0, old.stdout + old.stderr
    return _rows(tmp_path), current


def test_the_old_quoting_wrote_a_different_claim_or_unreadable_text(tmp_path):
    env = _project(tmp_path)
    old, current = _old_and_current(tmp_path, env)
    assert old["two_literals"]["statement"] == (
        '''for x in {"a"}, f(x, body='a: {"c":""}", t="s') = 1''')
    assert current["two_literals"]["statement"] == (
        '''for x in {"a"}, f(x, body='a: {"c":""}', t="s") = 1''')
    assert old["both_quotes"]["statement"] == (
        '''for x in {"a"}, f(x, 'a"b\\"c") = 0''')
    assert current["both_quotes"]["statement"] == (
        '''for x in {"a"}, f(x, 'a"b\\'c') = 0''')
    assert old["plain"]["statement"] == current["plain"]["statement"]


@pytest.mark.parametrize("names", [
    ("two_literals", "both_quotes", "plain"),
    ("two_literals", "plain"),
])
def test_a_record_with_the_old_quoting_is_rechecked_as_written(tmp_path, names):
    env = _project(tmp_path, names)
    _, current = _old_and_current(tmp_path, env)
    for _ in range(2):
        run = _run(tmp_path, env, "verify")
        assert run.returncode == 0, run.stdout + run.stderr
        assert "re-authored" not in run.stdout, run.stdout
        assert "does not parse" not in run.stdout, run.stdout
    rows = _rows(tmp_path)
    for name in names:
        assert rows[name]["statement"] == current[name]["statement"]
        assert rows[name]["verdict"] == current[name]["verdict"]
        assert "mathema.pending_supersession" not in (rows[name].get("meta") or {})


def test_docsync_reads_a_record_with_the_old_quoting(tmp_path):
    env = _project(tmp_path)
    _old_and_current(tmp_path, env)
    run = _run(tmp_path, env, "docsync", "qpkg.mod")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "SUPERSESSION" not in run.stdout, run.stdout
    declared = yaml.safe_load((tmp_path / ".mathema" / "declared"
                               / f"{KEY}.yaml").read_text())[KEY]
    statements = {c["name"]: c["statement"] for c in declared["claims"]}
    assert 't="s")' in statements["two_literals"], statements
