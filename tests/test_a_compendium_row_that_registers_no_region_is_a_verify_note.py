# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A project compendium row whose region cannot be stated over the
call's arguments registers no guard. `mathema verify` says so on one
note line naming the key, the row and the reason, rather than through a
Python warning; a row that does not parse is named by the key's own
failure line and gets no second report."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_the_row_is_a_note_and_never_a_python_warning(tmp_path):
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "y >= 0"
            - name: broken
              statement: "for x in [0, 4], f(x) >=> 0"
            - name: grows
              statement: "for x in [1, 4], f(x) <= x"
    """)
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env)
    assert "UserWarning" not in r.stderr, r.stderr
    notes = [ln for ln in r.stdout.splitlines()
             if ln.startswith("note numpy.sqrt") and "registers no" in ln]
    assert len(notes) == 1, r.stdout
    assert "'is_defined'" in notes[0] and "y is not a parameter" in notes[0]
    assert "claims/numpy.claims.yaml" in notes[0]
