# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium status`: for each third-party library the
project's functions call, its installed version, the claims files that
cover it (bundled or the project's, and whether each is in range), the
called functions with no claims at all, and for the called functions
that have rows how many are verified locally, trusted, falsified and
unsettled. The standard library is left out. It reads and never writes."""
import json
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("statusproj")
    _write(root / "spkg" / "__init__.py", "")
    _write(root / "spkg" / "mod.py", '''
        import math

        import numpy as np


        def root_of(x: float) -> float:
            """The square root of x."""
            return float(np.sqrt(x))


        def spread(x: float) -> float:
            """The square root of x, and its mean with a grid."""
            grid = np.linspace(0.0, 1.0, 5)
            return float(np.mean(grid)) + float(np.sqrt(x)) + math.sqrt(4.0)
    ''')
    _write(root / "claims" / "spkg.claims.yaml", """
        spkg.mod.root_of:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
        spkg.mod.spread:
          claims:
            - name: positive
              statement: 'for x in [0, 4], f(x) >= 0'
    """)
    _write(root / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24,<3"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
            - name: rising
              statement: 'for x in (0, 100], d(f(x), x) > 0'
              meta: {mathema.compendium_claimed: proven}
    """)
    _cli(root, "verify", "--root", str(root))
    from mathema.acceptance import apply_acceptance, plan_acceptance
    apply_acceptance(plan_acceptance(str(root), "numpy.sqrt", "rising",
                                     "trusted", by="test"))
    return root


def _snapshot(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            if "__pycache__" in path:
                continue
            with open(path, "rb") as fh:
                out[path] = fh.read()
    return out


def test_status_reports_each_library_the_project_calls(project):
    before = _snapshot(project)
    r = _cli(project, "compendium", "status", "--root", str(project))
    assert r.returncode == 0, r.stdout + r.stderr
    text = r.stdout
    import numpy
    assert f"numpy {numpy.__version__}" in text, text
    # the project's file and the bundled ones, each with its range
    assert "claims/numpy.claims.yaml (project, >=1.24,<3, in range)" in text
    assert ("mathema/compendium/numpy/reductions.claims.yaml "
            "(bundled, >=1.24,<3, in range)") in text
    # a called function no claims file states anything about
    assert "no claims: numpy.linspace" in text
    sqrt = next(ln for ln in text.splitlines() if "numpy.sqrt" in ln)
    assert "2 calls" in sqrt, sqrt
    assert "1 verified locally" in sqrt and "1 trusted (proven)" in sqrt
    assert "0 falsified" in sqrt and "0 unsettled" in sqrt
    mean = next(ln for ln in text.splitlines() if "numpy.mean" in ln)
    assert "1 call," in mean or "1 call " in mean, mean
    # the standard library is left out, and says so
    assert "math.sqrt" not in text
    assert "standard library" in text
    assert _snapshot(project) == before


def test_status_as_json_carries_the_same_data(project):
    r = _cli(project, "compendium", "status", "--root", str(project),
             "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    (lib,) = [x for x in data["libraries"] if x["library"] == "numpy"]
    assert lib["calls"] == 4
    assert "numpy.linspace" in lib["no_claims"]
    sqrt = lib["functions"]["numpy.sqrt"]
    assert sqrt["calls"] == 2
    assert sqrt["verified"] == 1 and sqrt["falsified"] == 0
    assert sqrt["trusted"] == {"proven": 1}
    assert sqrt["unsettled"] == 0
    assert any(f["source"] == "claims/numpy.claims.yaml"
               and f["origin"] == "project" and f["in_range"]
               for f in lib["files"])
    assert data["standard_library"] == "left out"


def test_status_for_one_library(project):
    r = _cli(project, "compendium", "status", "scipy", "--root",
             str(project))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "numpy" not in r.stdout
    assert "scipy" in r.stdout
