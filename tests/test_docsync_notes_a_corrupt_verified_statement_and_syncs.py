# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""docsync notes a verified statement that does not read, and syncs.

A verified record whose stored statement for an authored claim does not
parse (here the text an earlier release's quoting wrote for a literal
holding both quote kinds) records nothing: docsync prints one note
naming the function and the claim, saying the next verify checks the
claim again and replaces the row, materializes every function, and
exits 0. Nothing the author wrote is wrong, so nothing is reported
UNREADABLE and the record is left as it is for verify to replace.
"""
import os
import subprocess
import sys
import textwrap

import yaml

from mathema.spec import save_verified_entry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "kpkg.mod.one"

_MOD = '''
def one(x: float) -> float:
    """One more than x."""
    return x + 1


def two(x: float) -> float:
    """Two more than x."""
    return x + 2
'''

_CLAIMS = """
kpkg.mod.one:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
kpkg.mod.two:
  claims:
    - name: above
      statement: "for x in [0, 1], f(x) > x"
"""

CORRUPT = "for x in [0, 1], f(x, 'a\"b\\\"c\") = 1"


def _run(tmp_path, env, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def test_a_corrupt_verified_statement_is_noted_and_the_functions_synced(tmp_path):
    pkg = tmp_path / "kpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "k.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    first = _run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    path = tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"
    entry = yaml.safe_load(path.read_text())[KEY]
    for row in entry["claims"]:
        if row.get("name") == "above":
            row["statement"] = CORRUPT
    save_verified_entry(KEY, entry, root=str(tmp_path))
    corrupt = path.read_text()
    run = _run(tmp_path, env, "docsync", "kpkg.mod")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "UNREADABLE" not in run.stdout and "FAIL" not in run.stdout, run.stdout
    notes = [ln for ln in run.stdout.splitlines() if ln.startswith("note ")]
    assert notes == [
        f"note {KEY}: the stored text of claim 'above' could not be read; "
        f"the next verify checks the claim again and replaces it"], run.stdout
    assert "materialized 2 declared entries" in run.stdout, run.stdout
    assert path.read_text() == corrupt
