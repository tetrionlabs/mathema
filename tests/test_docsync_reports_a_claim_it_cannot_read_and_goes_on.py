# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""docsync reports a claim it cannot read and syncs every other function.

A verified claim re-authored as text that does not parse is reported
with the claims file and line that hold it, the function's name and
the claim's name. Every other function is still materialized, and
the run exits 2 once it has finished.
"""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MOD = '''
def one(x: float) -> float:
    """One more than x."""
    return x + 1


def two(x: float) -> float:
    """Two more than x."""
    return x + 2


def three(x: float) -> float:
    """Three more than x."""
    return x + 3
'''

_CLAIMS = """
dpkg.mod.one:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
dpkg.mod.two:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
dpkg.mod.three:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
"""


def _project(tmp_path):
    pkg = tmp_path / "dpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "d.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _run(tmp_path, env, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _declared(tmp_path, key):
    return tmp_path / ".mathema" / "declared" / f"{key}.yaml"


def _reauthor_unreadably(tmp_path, key):
    claims = tmp_path / "claims" / "d.claims.yaml"
    lines = claims.read_text().splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith(f"{key}:")) + 3
    lines[at] = "      statement: 'for x in [0, 1], f(x) <= <= x'"
    claims.write_text("\n".join(lines) + "\n")
    return at + 1


def test_an_unreadable_claim_is_reported_and_the_rest_synced(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    _reauthor_unreadably(tmp_path, "dpkg.mod.one")
    run = _run(tmp_path, env, "docsync", "dpkg.mod")
    assert run.returncode == 2, run.stdout + run.stderr
    assert not _declared(tmp_path, "dpkg.mod.one").exists()
    assert _declared(tmp_path, "dpkg.mod.two").exists()
    assert _declared(tmp_path, "dpkg.mod.three").exists()
    lines = [ln for ln in run.stdout.splitlines() if ln.startswith("UNREADABLE")]
    assert len(lines) == 1, run.stdout
    where = os.path.join("claims", "d.claims.yaml")
    assert f"{where}:" in lines[0], lines[0]
    assert "dpkg.mod.one" in lines[0] and "'above'" in lines[0], lines[0]
    assert "materialized 2 declared entries" in run.stdout, run.stdout


def test_the_reported_line_holds_the_statement(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    _reauthor_unreadably(tmp_path, "dpkg.mod.one")
    run = _run(tmp_path, env, "docsync", "dpkg.mod")
    line = next(ln for ln in run.stdout.splitlines() if ln.startswith("UNREADABLE"))
    where = line.split()[1]
    path, number = where.rsplit(":", 1)
    held = (tmp_path / path).read_text().splitlines()[int(number) - 1]
    assert "statement:" in held and "<= <=" in held, (line, held)


def test_a_verified_claim_reauthored_unreadably_is_reported_at_its_line(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    line = _reauthor_unreadably(tmp_path, "dpkg.mod.one")
    run = _run(tmp_path, env, "docsync", "dpkg.mod")
    assert run.returncode == 2, run.stdout + run.stderr
    found = [ln for ln in run.stdout.splitlines() if ln.startswith("UNREADABLE")]
    assert len(found) == 1, run.stdout
    assert found[0].split()[1] == os.path.join("claims", "d.claims.yaml") + f":{line}", found[0]
    assert _declared(tmp_path, "dpkg.mod.two").exists()
    assert _declared(tmp_path, "dpkg.mod.three").exists()
