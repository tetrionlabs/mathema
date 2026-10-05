# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium update` pins a call's arguments into the rows
that leave them at their defaults. A row whose domain already ranges
over an argument (`numpy.clip`'s definition binds `a_min` and `a_max`)
speaks for the call when the passed value lies in that range, so it is
not copied; a missing-value policy row takes no pinned arguments, and
the update says so in one line rather than reporting it as a claim that
does not read. The library's own unresolved internal names are not
reported as the project's."""
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


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "upd.py", '''
        import numpy as np


        def unit(x: float) -> float:
            """x clipped to the unit interval."""
            return float(np.clip(x, 0.0, 1.0))


        def col_means(a):
            """The mean down each column."""
            return np.mean(a, axis=0)
    ''')
    _write(tmp_path / "claims" / "upd.claims.yaml", """
        upd.unit:
          claims:
            - name: within
              statement: 'for x in [-5, 5], 0 <= f(x) <= 1'
        upd.col_means:
          claims: []
    """)
    return tmp_path


def test_a_row_ranging_over_the_argument_is_not_pinned(project):
    r = _cli(project, "compendium", "update", "--root", str(project))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "declared with both" not in r.stdout, r.stdout
    data = yaml.safe_load((project / "claims" / "numpy.claims.yaml")
                          .read_text())
    names = [c["name"] for c in data["numpy.clip"]["claims"]]
    assert "definition" in names
    assert not any(n.startswith("definition@") for n in names), names
    assert "clip_lower@a_max=1.0,a_min=0.0" in names


def test_a_policy_row_is_named_as_not_taking_pins(project):
    r = _cli(project, "compendium", "update", "--root", str(project),
             "--dry-run")
    assert "no relation" not in r.stdout, r.stdout
    lines = [ln for ln in r.stdout.splitlines()
             if "missing_propagates" in ln]
    assert len(lines) == 1, r.stdout
    assert "policy row" in lines[0]


def test_the_library_internal_names_are_not_reported(project):
    r = _cli(project, "compendium", "update", "--root", str(project),
             "--dry-run")
    assert "UNRESOLVED" not in r.stderr, r.stderr
