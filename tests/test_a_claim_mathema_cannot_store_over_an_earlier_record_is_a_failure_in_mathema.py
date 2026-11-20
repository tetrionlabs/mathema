# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim mathema cannot store, over an earlier record, fails as mathema's.

When the stored text mathema writes for a claim does not read back as
the claim (`CanonicalTextError`), and a record of the claim already
exists, the run reports a defect in mathema: a summary line, then a
diagnostic naming the claims file and line, quoting the line, and
saying to report it. The author's claim is not blamed, the function's
other claims are still checked, the earlier row of the claim is kept
exactly as it was, and the run fails with exit status 1, not the 2 of
an authoring error. `docsync` reports the same defect, syncs the
function and exits 1.
"""
import os
import subprocess
import sys
import textwrap

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "cpkg.mod.tag"

_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)
'''

_CLAIMS = r"""
cpkg.mod.tag:
  claims:
    - name: two_literals
      statement: "for x in {\"a\"}, f(x, '}\"', t='s') == 1"
    - name: plain
      statement: 'for x in {"a"}, f(x, t="ab") == 2'
"""

#: every literal of a stored text re-quoted the way releases up to
#: 0.6.6.1 did, with no legacy context to say so: text that does not
#: read back as `two_literals`
_BROKEN = ("from mathema import grammar; "
           "grammar._double_quoted = grammar._legacy_double_quoted; ")


def _project(tmp_path):
    pkg = tmp_path / "cpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _run(tmp_path, env, *args, broken=False):
    return subprocess.run(
        [sys.executable, "-c",
         f"import sys; {_BROKEN if broken else ''}from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _record(tmp_path):
    return tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"


def _rows(tmp_path):
    entry = yaml.safe_load(_record(tmp_path).read_text())[KEY]
    return {c["name"]: c for c in entry["claims"]}


def _statement_line(tmp_path):
    lines = (tmp_path / "claims" / "c.claims.yaml").read_text().splitlines()
    at = next(i for i, ln in enumerate(lines) if "'}" in ln)
    return at + 1, lines[at].strip()


def test_verify_reports_the_defect_and_keeps_the_earlier_row(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    before = _rows(tmp_path)["two_literals"]
    run = _run(tmp_path, env, "verify", broken=True)
    assert "Traceback" not in run.stderr, run.stderr
    assert run.returncode == 1, run.stdout + run.stderr
    assert "correct it there" not in run.stdout, run.stdout
    assert "does not parse" not in run.stdout, run.stdout
    out = run.stdout.splitlines()
    summary = [i for i, ln in enumerate(out) if "two_literals" in ln]
    assert len(summary) == 1, run.stdout
    assert "defect in mathema's rendering" in out[summary[0]], run.stdout
    block = out[summary[0]:summary[0] + 8]
    line, text = _statement_line(tmp_path)
    where = os.path.join("claims", "c.claims.yaml")
    assert "Error: mathema cannot write this claim's stored text" in block, block
    assert f"  on {where} line {line}:" in block, block
    assert f"  {line}:   {text}" in block, block
    explanation = block[-1]
    assert "does not read back" in explanation and "report it" in explanation, block
    assert "unchecked this run" in explanation, block
    rows = _rows(tmp_path)
    assert rows["two_literals"] == before
    assert rows["plain"]["verdict"] in ("proven", "holds"), rows["plain"]


def test_docsync_reports_the_defect_and_syncs_the_function(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    record = _record(tmp_path).read_text()
    run = _run(tmp_path, env, "docsync", "cpkg.mod", broken=True)
    assert "Traceback" not in run.stderr, run.stderr
    assert run.returncode == 1, run.stdout + run.stderr
    assert "UNREADABLE" not in run.stdout, run.stdout
    failing = [ln for ln in run.stdout.splitlines() if ln.startswith("FAIL ")]
    assert len(failing) == 1 and "'two_literals'" in failing[0], run.stdout
    assert "defect in mathema's rendering" in failing[0], failing
    assert "Error: mathema cannot write this claim's stored text" in run.stdout
    assert (tmp_path / ".mathema" / "declared" / f"{KEY}.yaml").exists()
    assert _record(tmp_path).read_text() == record
