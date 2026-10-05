# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A definition row states what a function computes at its defaults
(`numpy.std`: `std(a, ddof=0)`), so a copy with a different argument
pinned would state the wrong value. `mathema compendium update` writes
no such copy: for a call whose arguments no definition row covers it
says so, with a template to state one last on the line."""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_no_pinned_definition_without_a_stated_one(tmp_path):
    _write(tmp_path / "upd.py", '''
        import numpy as np


        def spread(a):
            """The spread of a with two degrees of freedom removed."""
            return np.std(a, ddof=2)
    ''')
    _write(tmp_path / "claims" / "upd.claims.yaml", """
        upd.spread:
          claims: []
    """)
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    env.pop("VIRTUAL_ENV", None)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['compendium', 'update', '--root', "
              f"{str(tmp_path)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env)
    lines = [ln for ln in r.stdout.splitlines()
             if "no definition row covers ddof=2" in ln]
    assert len(lines) == 1, r.stdout + r.stderr
    assert "to state one" in lines[0]
    assert lines[0].rstrip().endswith('~= ..."}') and "f(a, ddof=2)" in lines[0]
    path = tmp_path / "claims" / "numpy.claims.yaml"
    if path.exists():
        rows = (yaml.safe_load(path.read_text()).get("numpy.std") or {}
                ).get("claims") or []
        assert not any(r["name"].startswith("definition@ddof=2")
                       for r in rows), rows
