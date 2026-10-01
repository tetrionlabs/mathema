# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium update` adjudicates every pinned row against the
installed library before writing it, and writes only the rows that
hold or are proven over their stated domain. A pinned row the library
breaks (`np.mean(a, axis=1)` raises AxisError on a one-dimensional
`a`, so `let axis be 1, dim(a) >= 1` is false) is reported with its
verdict and left out, so the next `verify` has nothing new to
falsify."""
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


def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    env.pop("VIRTUAL_ENV", None)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


def _project(root, axis):
    _write(root / "upd.py", f'''
        import numpy as np


        def rows_mean(a):
            """The mean along one axis."""
            return np.mean(a, axis={axis})
    ''')
    _write(root / "claims" / "upd.claims.yaml", """
        upd.rows_mean:
          claims:
            - name: finite
              statement: 'for a in [0, 1]^n, f(a) >= 0'
    """)


def _rows(root):
    path = root / "claims" / "numpy.claims.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {c["name"]: c for c in (data.get("numpy.mean") or {})
            .get("claims") or []}


def test_a_pinned_row_the_library_breaks_is_not_written(tmp_path):
    _project(tmp_path, 1)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "is_defined@axis=1" not in _rows(tmp_path), r.stdout
    line = next(ln for ln in r.stdout.splitlines()
                if "is_defined@axis=1" in ln)
    assert "falsified" in line and "not added" in line, r.stdout
    v = _cli(tmp_path, "verify", "--root", str(tmp_path))
    assert "is_defined@axis=1" not in v.stdout, v.stdout


def test_a_pinned_row_that_holds_is_written(tmp_path):
    _project(tmp_path, 0)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rows = _rows(tmp_path)
    assert rows["is_defined@axis=0"]["statement"] == \
        "let axis be 0, dim(a) >= 1", r.stdout
    added = next(ln for ln in r.stdout.splitlines()
                 if "add is_defined@axis=0" in ln)
    assert "holds" in added or "proven" in added, added
    v = _cli(tmp_path, "verify", "--root", str(tmp_path))
    numpy_line = next(ln for ln in v.stdout.splitlines()
                      if "numpy.mean" in ln)
    assert numpy_line.startswith("ok") and " 0 falsified" in numpy_line, \
        v.stdout
