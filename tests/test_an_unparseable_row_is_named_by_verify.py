# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A row that does not parse fails its key in `mathema verify`, and the
failure names the row as well as the file, so the person fixing it goes
straight to it: in a project compendium file as in any claims file."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_the_failure_names_the_row_that_does_not_parse(tmp_path):
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
            - name: broken
              statement: "for x in [0, 4], f(x) >=> 0"
    """)
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env)
    fails = [ln for ln in r.stdout.splitlines()
             if ln.startswith("FAIL numpy.sqrt")]
    assert len(fails) == 1, r.stdout + r.stderr
    assert "'broken'" in fails[0]
    assert "claims/numpy.claims.yaml" in fails[0]
    assert r.returncode != 0
