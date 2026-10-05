# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A project compendium row that replaces a bundled row of the same name
is named by `mathema verify` on one note line per bundled file, so the
replacement is never silent; the bundled rows it does not restate still
apply."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_verify_names_the_replaced_rows(tmp_path):
    from mathema.compendium import load_library_claims
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
              note: "the project's reading"
            - name: grows
              statement: "for x in [1, 4], f(x) <= x"
    """)
    info = load_library_claims(str(tmp_path))["numpy.sqrt"]
    assert info["replaced"] == [{
        "source": "mathema/compendium/numpy/scalars.claims.yaml",
        "rows": ["is_defined"]}]
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env)
    notes = [ln for ln in r.stdout.splitlines()
             if ln.startswith("note numpy.sqrt") and "replaces" in ln]
    assert notes == ["note numpy.sqrt: the project replaces the bundled row "
                     "is_defined of mathema/compendium/numpy/scalars.claims.yaml"
                     "; the other bundled rows still apply"], r.stdout
