# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A project's own compendium file (`compendium: numpy` in its claims
directory) states library rows, adjudicated in full by every sweep while
its `versions:` range admits the installed library: each key is gated
as a library key (named with the file it comes from, the library's own
unresolved internal names not held against it). Once the range no
longer admits the installed version (an upgrade, an edit), the sweep
says so for each key it recorded, keeps the record as it is, and does
not re-adjudicate the library function as if it were the project's
own."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _verify(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(root)!r}"
              + "".join(f", {a!r}" for a in args) + "]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


_FILE = """
    compendium: numpy
    versions: "{versions}"
    numpy.round:
      claims:
        - name: same_length
          statement: "for a in R^n, len(f(a)) == len(a)"
"""


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "rpkg" / "__init__.py", "")
    _write(tmp_path / "rpkg" / "mod.py", '''
        import numpy as np


        def total(xs: list[float]) -> float:
            """The sum of xs, each rounded."""
            return float(np.sum(np.round(np.asarray(xs, dtype=float))))
    ''')
    _write(tmp_path / "claims" / "numpy.claims.yaml",
           _FILE.format(versions=">=1.24"))
    return tmp_path


def _line(out: str, key: str) -> str:
    return next((ln for ln in out.splitlines()
                 if f" {key}:" in ln or ln.startswith(f"{key}:")), "")


def test_a_project_compendium_key_is_gated_as_a_library_key(project):
    r = _verify(project)
    line = _line(r.stdout, "numpy.round")
    assert line.startswith("ok"), r.stdout + r.stderr
    assert "library claims from claims/numpy.claims.yaml" in line
    assert "unresolved names" not in r.stdout


def test_a_record_whose_file_left_its_range_is_kept_and_stated(project):
    import yaml
    _verify(project)
    path = project / ".mathema" / "verified" / "numpy.round.yaml"
    before = yaml.safe_load(path.read_text())
    _write(project / "claims" / "numpy.claims.yaml",
           _FILE.format(versions=">=99"))
    r = _verify(project)
    assert r.returncode == 0, r.stdout + r.stderr
    notes = [ln for ln in r.stdout.splitlines()
             if ln.startswith("note numpy.round")]
    assert len(notes) == 1, r.stdout
    assert "no claims file about numpy.round applies" in notes[0]
    assert "kept as it is" in notes[0]
    assert "claims/numpy.claims.yaml states it for >=99" in notes[0]
    assert "bounds.claims.yaml" not in notes[0]
    assert yaml.safe_load(path.read_text()) == before
