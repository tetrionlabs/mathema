# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A project compendium entry for a function the bundled files state
replaces the bundled entry whole, so a bundled row the project file does
not restate (numpy.sqrt's `is_defined` guard) is no longer used. The
loader records which rows each entry shadows, and `mathema verify` names
them for every library key it adjudicates, so the drop is never
silent."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "spkg" / "__init__.py", "")
    _write(tmp_path / "spkg" / "mod.py", '''
        import numpy as np


        def root(x: float) -> float:
            """The square root of x."""
            return float(np.sqrt(x))
    ''')
    _write(tmp_path / "claims" / "spkg.claims.yaml", """
        spkg.mod.root:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
    """)
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24"
        numpy.sqrt:
          claims:
            - name: grows
              statement: "for x in [1, 4], f(x) <= x"
    """)
    return tmp_path


def test_the_loader_records_the_rows_an_entry_shadows(project):
    from mathema.compendium import load_library_claims
    info = load_library_claims(str(project))["numpy.sqrt"]
    assert info["source"] == "claims/numpy.claims.yaml"
    (shadowed,) = info["shadowed"]
    assert shadowed["source"] == "mathema/compendium/numpy/scalars.claims.yaml"
    assert "is_defined" in shadowed["rows"]


def test_verify_names_the_shadowed_rows(project):
    env = dict(os.environ, PYTHONPATH=str(project))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(project)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(project),
                       capture_output=True, text=True, env=env)
    notes = [ln for ln in r.stdout.splitlines()
             if ln.startswith("note numpy.sqrt") and "shadows" in ln]
    assert len(notes) == 1, r.stdout + r.stderr
    assert "claims/numpy.claims.yaml" in notes[0]
    assert "is_defined" in notes[0]
    assert "mathema/compendium/numpy/scalars.claims.yaml" in notes[0]
