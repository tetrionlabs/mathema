# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema verify <claims file>`: the up-front route. A bare sweep is
lazy about the bundled library claims (only the library functions the
project calls are adjudicated); naming a claims file adjudicates every
entry in it, compendium or not, and records them like any sweep. A
compendium file whose library is not importable says so on one line
and adjudicates nothing; one installed outside the file's `versions`
range says so on one line and is adjudicated against the installed
version, its rows recorded but never used as facts there."""
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


def _recorded(root) -> set:
    store = root / ".mathema" / "verified"
    if not store.exists():
        return set()
    return {p.name[:-len(".yaml")] for p in store.iterdir()
            if p.name.endswith(".yaml")}


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "vpkg" / "__init__.py", "")
    _write(tmp_path / "vpkg" / "mod.py", '''
        import numpy as np


        def root_of(x: float) -> float:
            """The square root of x."""
            return float(np.sqrt(x))


        def doubled(x: float) -> float:
            """Twice x."""
            return 2.0 * x
    ''')
    _write(tmp_path / "claims" / "vpkg.claims.yaml", """
        vpkg.mod.root_of:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
    """)
    _write(tmp_path / "claims" / "more.claims.yaml", """
        vpkg.mod.doubled:
          claims:
            - name: grows
              statement: 'for x in [0, 4], f(x) >= x'
    """)
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24,<3"
        numpy.sqrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
        numpy.tanh:
          claims:
            - name: tanh_bounded
              statement: "for x in [-10, 10], -1 <= f(x) <= 1"
    """)
    return tmp_path


def test_a_bare_sweep_adjudicates_only_the_library_functions_called(project):
    r = _verify(project)
    recorded = _recorded(project)
    assert "numpy.sqrt" in recorded, r.stdout + r.stderr
    assert "numpy.cos" not in recorded


def test_naming_a_compendium_file_adjudicates_every_entry(project):
    r = _verify(project, "claims/numpy.claims.yaml")
    recorded = _recorded(project)
    assert {"numpy.sqrt", "numpy.tanh"} <= recorded, r.stdout + r.stderr
    # only the file's entries: the project's own functions wait for a sweep
    assert "vpkg.mod.root_of" not in recorded
    assert "numpy.tanh: library claims from claims/numpy.claims.yaml" in \
        r.stdout, r.stdout


def test_the_bundled_file_by_path(project):
    r = _verify(project, "mathema/compendium/numpy/bounds.claims.yaml")
    recorded = _recorded(project)
    assert {"numpy.sin", "numpy.cos", "numpy.tanh", "numpy.abs"} <= \
        recorded, r.stdout + r.stderr


def test_naming_an_ordinary_claims_file_adjudicates_its_entries(project):
    r = _verify(project, "claims/more.claims.yaml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _recorded(project) == {"vpkg.mod.doubled"}, r.stdout


def test_a_file_outside_its_versions_range_says_so_on_one_line(project):
    _write(project / "claims" / "future.claims.yaml", """
        compendium: numpy
        versions: ">=99"
        numpy.cos:
          claims:
            - name: cos_bounded
              statement: "for x in [-1, 1], -1 <= f(x) <= 1"
    """)
    r = _verify(project, "claims/future.claims.yaml")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.startswith("note claims/future.claims.yaml")]
    assert len(lines) == 1, r.stdout
    assert "outside the file's range >=99" in lines[0]
    assert "never used as facts" in lines[0]


def test_a_named_file_outside_its_range_is_adjudicated_against_the_installed_version(project):
    import yaml
    _write(project / "claims" / "future.claims.yaml", """
        compendium: numpy
        versions: ">=99"
        numpy.cos:
          claims:
            - name: cos_within_one
              statement: "for x in [-1, 1], -1 <= f(x) <= 1"
    """)
    r = _verify(project, "claims/future.claims.yaml")
    assert "numpy.cos" in _recorded(project), r.stdout + r.stderr
    doc = yaml.safe_load((project / ".mathema" / "verified"
                          / "numpy.cos.yaml").read_text())
    row = {c["name"]: c for c in doc["numpy.cos"]["claims"]}["cos_within_one"]
    assert row["verdict"] in ("proven", "holds"), row
    assert row["meta"]["mathema.outside_versions"] == ">=99"


def test_a_row_outside_its_range_is_never_a_fact_after_its_file_is_verified(project):
    from mathema.compendium import load_library_claims
    _write(project / "claims" / "future.claims.yaml", """
        compendium: numpy
        versions: ">=99"
        numpy.cos:
          claims:
            - name: cos_within_one
              statement: "for x in [-1, 1], -1 <= f(x) <= 1"
    """)
    _verify(project, "claims/future.claims.yaml")
    claims = load_library_claims(str(project))
    rows = (claims.get("numpy.cos") or {}).get("entry", {}).get("claims") or []
    assert "cos_within_one" not in [r.get("name") for r in rows]


def test_a_file_whose_library_is_not_importable_says_so(project):
    _write(project / "claims" / "gone.claims.yaml", """
        compendium: nosuchlib_mathema
        versions: "*"
        nosuchlib_mathema.f:
          claims:
            - name: nonneg
              statement: "for x in [0, 1], f(x) >= 0"
    """)
    r = _verify(project, "claims/gone.claims.yaml")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines() if "gone.claims.yaml" in ln]
    assert len(lines) == 1, r.stdout
    assert "nosuchlib_mathema is not importable here" in lines[0]
