# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium update`: brings the project's compendium files in
line with how its functions call libraries. A call that passes a
non-default literal argument no row covers gains rows pinning it (`let
axis be 1, ...`), copied from the key's existing rows, unverified until
`mathema verify` runs; a non-literal argument is reported, not pinned.
A row whose own `versions:` range excludes the installed version, and
which `verify` recorded as holding here, has its range widened to
include it; a row nobody uses keeps its range. Every change is printed,
and `--dry-run` writes nothing."""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

np = pytest.importorskip("numpy")


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


def _minor() -> str:
    return ".".join(np.__version__.split(".")[:2])


def _project(root, body):
    _write(root / "upd.py", body)
    _write(root / "claims" / "upd.claims.yaml", """
        upd.rows_mean:
          claims:
            - name: finite
              statement: 'for a in [0, 1]^n, f(a) >= 0'
    """)


_AXIS_ONE = '''
    import numpy as np


    def rows_mean(a):
        """The mean along the second axis."""
        return np.mean(a, axis=1)
'''


def test_a_non_default_literal_argument_gains_a_pinned_row(tmp_path):
    _project(tmp_path, _AXIS_ONE)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    path = tmp_path / "claims" / "numpy.claims.yaml"
    data = yaml.safe_load(path.read_text())
    assert data["compendium"] == "numpy"
    assert data["versions"] == f">={_minor()}"
    rows = {c["name"]: c for c in data["numpy.mean"]["claims"]}
    # the key's existing row is kept, and a pinned copy joins it
    assert rows["is_defined"]["statement"] == "dim(a) >= 1"
    pinned = rows["is_defined@axis=1"]
    assert pinned["statement"] == "let axis be 1, dim(a) >= 1"
    assert "upd.rows_mean" in pinned["note"]
    assert "numpy.mean" in r.stdout and "axis=1" in r.stdout, r.stdout
    assert "unverified" in r.stdout, r.stdout
    # a second run finds the call covered and changes nothing
    again = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert again.returncode == 0, again.stderr
    assert yaml.safe_load(path.read_text()) == data
    assert "nothing to change" in again.stdout, again.stdout


def test_a_non_literal_argument_is_reported_not_pinned(tmp_path):
    _project(tmp_path, '''
        import numpy as np


        def rows_mean(a, k=1):
            """The mean along axis k."""
            return np.mean(a, axis=k)
    ''')
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "axis" in r.stdout and "not a literal" in r.stdout, r.stdout
    assert not (tmp_path / "claims" / "numpy.claims.yaml").exists()


def test_dry_run_writes_nothing(tmp_path):
    _project(tmp_path, _AXIS_ONE)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path),
             "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "is_defined@axis=1" in r.stdout, r.stdout
    assert not (tmp_path / "claims" / "numpy.claims.yaml").exists()


def test_a_verified_row_is_widened_and_an_unused_one_is_not(tmp_path):
    _project(tmp_path, '''
        import numpy as np


        def rows_mean(a):
            """The mean."""
            return float(np.mean(a))
    ''')
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: ">=1.24,<3"
        numpy.mean:
          claims:
            - name: is_defined
              statement: "dim(a) >= 1"
              versions: ">=1.24,<2"
        numpy.std:
          claims:
            - name: is_defined
              statement: "dim(a) >= 1"
              versions: ">=1.24,<2"
    """)
    v = _cli(tmp_path, "verify", "--root", str(tmp_path))
    assert "numpy.mean" in v.stdout, (v.stdout, v.stderr)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    data = yaml.safe_load((tmp_path / "claims" / "numpy.claims.yaml")
                          .read_text())
    (mean_row,) = data["numpy.mean"]["claims"]
    (std_row,) = data["numpy.std"]["claims"]
    major, minor = (int(p) for p in _minor().split("."))
    assert mean_row["versions"] == f">=1.24,<{major}.{minor + 1}", mean_row
    assert std_row["versions"] == ">=1.24,<2", std_row
    assert "widened" in r.stdout, r.stdout


def test_a_row_outside_its_own_range_is_no_fact(tmp_path):
    from mathema.compendium import install, uninstall
    from mathema.symbolic._partiality import _PARTIALITY_LEMMAS
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        numpy.cbrt:
          claims:
            - name: is_defined
              statement: "x >= 0"
              versions: "<1"
        numpy.arctan:
          claims:
            - name: is_defined
              statement: "x >= 0"
              versions: ">=1"
    """)
    try:
        install(str(tmp_path))
        assert "numpy.cbrt" not in _PARTIALITY_LEMMAS
        assert "numpy.arctan" in _PARTIALITY_LEMMAS
    finally:
        uninstall()


def test_row_versions_are_validated():
    from mathema.spec import ClaimsFileError, validate_claims_file
    good = {"compendium": "numpy", "numpy.mean": {"claims": [
        {"name": "is_defined", "statement": "dim(a) >= 1",
         "versions": ">=1.24,<2"}]}}
    validate_claims_file(good, "numpy.claims.yaml")
    bad = {"compendium": "numpy", "numpy.mean": {"claims": [
        {"name": "is_defined", "statement": "dim(a) >= 1",
         "versions": "2.x"}]}}
    with pytest.raises(ClaimsFileError, match="versions"):
        validate_claims_file(bad, "numpy.claims.yaml")
    orphan = {"m.f": {"claims": [
        {"name": "c", "statement": "f(x) >= 0", "versions": ">=1"}]}}
    with pytest.raises(ClaimsFileError, match="versions"):
        validate_claims_file(orphan, "m.claims.yaml")


def test_a_pinned_row_leaves_the_smoke_call_at_the_defaults():
    import mathema
    from mathema.conjecture import claim
    from mathema.compendium import ensure_bundled
    ensure_bundled()
    rec = mathema.check(np.mean, claims=[
        claim("let axis be 0, dim(a) >= 1", name="is_defined@axis=0")])
    rows = {p.name: p for p in rec.probes}
    assert "callable" not in rows, rows["callable"].note
    assert rows["is_defined@axis=0"].verdict == "holds", \
        rows["is_defined@axis=0"].note


_COMMENTED = """\
    # numpy rows for this project
    compendium: numpy
    versions: ">=1.24"
    # the mean of an empty array is nan
    numpy.mean:
      claims:
        - name: is_defined
          statement: "dim(a) >= 1"  # needs one axis
"""


def test_rewriting_a_file_with_comments_warns_and_points_at_note(tmp_path):
    _project(tmp_path, _AXIS_ONE)
    _write(tmp_path / "claims" / "numpy.claims.yaml", _COMMENTED)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    (warning,) = [ln for ln in r.stdout.splitlines() if "WARN" in ln]
    assert os.path.join("claims", "numpy.claims.yaml") in warning, warning
    assert "comments" in warning and "note:" in warning, warning
    assert "would" not in warning, warning
    text = (tmp_path / "claims" / "numpy.claims.yaml").read_text()
    assert text.startswith("# numpy rows for this project"), text
    assert "the mean of an empty array" not in text, text


def test_dry_run_says_the_comments_would_be_lost(tmp_path):
    _project(tmp_path, _AXIS_ONE)
    path = tmp_path / "claims" / "numpy.claims.yaml"
    _write(path, _COMMENTED)
    before = path.read_text()
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path),
             "--dry-run")
    assert r.returncode == 0, r.stderr
    (warning,) = [ln for ln in r.stdout.splitlines() if "WARN" in ln]
    assert os.path.join("claims", "numpy.claims.yaml") in warning, warning
    assert "would" in warning and "note:" in warning, warning
    assert path.read_text() == before


def test_a_header_comment_alone_raises_no_warning(tmp_path):
    _project(tmp_path, _AXIS_ONE)
    _write(tmp_path / "claims" / "numpy.claims.yaml", """\
        # numpy rows for this project
        compendium: numpy
        versions: ">=1.24"
        numpy.mean:
          claims:
            - name: is_defined
              statement: "dim(a) >= 1"
    """)
    r = _cli(tmp_path, "compendium", "update", "--root", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "wrote" in r.stdout, r.stdout
    assert "WARN" not in r.stdout, r.stdout


def test_a_pinned_row_name_reads_its_family_before_the_at():
    from mathema.conjecture import region_row_kind
    from mathema.families import claim_base_name
    assert claim_base_name("is_defined@axis=0") == "is_defined"
    assert claim_base_name("is_defined@axis=0,ddof=1") == "is_defined"
    assert claim_base_name("is_defined[2]@axis=0") == "is_defined"
    assert claim_base_name("convex[x]") == "convex"
    assert region_row_kind("is_defined@axis=0") == "is_defined"
    assert region_row_kind("is_overflow_safe@axis=0") == "is_overflow_safe"


def test_a_pinned_row_name_passes_validation():
    from mathema.spec import validate_claims_file
    validate_claims_file({"compendium": "numpy", "numpy.mean": {"claims": [
        {"name": "is_defined@axis=0,ddof=1",
         "statement": "let axis be 0, let ddof be 1, dim(a) >= 1"}]}},
        "numpy.claims.yaml")
