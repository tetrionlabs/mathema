# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record row whose stored statement does not read is stale.

When the statement a verified record stores for an authored claim does
not parse, the row is no record of anything: the next `verify` checks
the claim again as authored and rewrites the row, saying the stored
text could not be read and was replaced. `docsync` syncs the function
as usual and says the next `verify` replaces the row.
"""
import os
import subprocess
import sys
import textwrap

import yaml

from mathema.spec import save_verified_entry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "upkg.mod.one"
MANGLED = "for x in [0, 1], f(x) > x ("

_MOD = '''
def one(x: float) -> float:
    """One more than x."""
    return x + 1
'''

_CLAIMS = """
upkg.mod.one:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
    - name: below
      statement: "for x in [0, 1], f(x) <= x + 1"
"""


def _project(tmp_path):
    pkg = tmp_path / "upkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "u.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _run(tmp_path, env, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _record(tmp_path):
    return tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"


def _rows(tmp_path):
    entry = yaml.safe_load(_record(tmp_path).read_text())[KEY]
    return {c.get("name"): c for c in entry["claims"]}


def _mangle(tmp_path):
    entry = yaml.safe_load(_record(tmp_path).read_text())[KEY]
    for row in entry["claims"]:
        if row.get("name") == "above":
            row["statement"] = MANGLED
    save_verified_entry(KEY, entry, root=str(tmp_path))


def test_an_unreadable_stored_statement_is_checked_again_and_replaced(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    before = _rows(tmp_path)
    _mangle(tmp_path)
    run = _run(tmp_path, env, "verify")
    assert run.returncode == 0, run.stdout + run.stderr
    said = [ln for ln in run.stdout.splitlines() if "could not be read" in ln]
    assert len(said) == 1 and "'above'" in said[0] and "was replaced" in said[0], run.stdout
    after = _rows(tmp_path)
    for name in ("above", "below"):
        assert after[name]["statement"] == before[name]["statement"]
        assert after[name]["verdict"] == before[name]["verdict"]
    again = _run(tmp_path, env, "verify")
    assert again.returncode == 0, again.stdout + again.stderr
    assert "could not be read" not in again.stdout, again.stdout


def test_docsync_syncs_a_function_whose_record_does_not_read(tmp_path):
    env = _project(tmp_path)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    _mangle(tmp_path)
    run = _run(tmp_path, env, "docsync", "upkg.mod")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "CONFLICT" not in run.stdout and "UNREADABLE" not in run.stdout, run.stdout
    said = [ln for ln in run.stdout.splitlines() if "could not be read" in ln]
    assert len(said) == 1 and "'above'" in said[0], run.stdout
    assert (tmp_path / ".mathema" / "declared" / f"{KEY}.yaml").exists()
