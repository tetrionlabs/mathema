# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A definition row is revoked as a wrong model only by a failure at an
ordinary draw. A failure only at a magnitude corner (an overflow where
the exact value is finite) is a finding about the library's computation:
the row stays an axiom, and no proof through it is weakened. A wrong row
still falls at an ordinary draw."""
import os
import tempfile
import textwrap

import numpy as np
import pandas as pd
import pytest
import yaml

import mathema
from mathema import compendium
from mathema.compendium import _bundled_dir

LAW = ("for returns in {dom}, let s = mathema.f.shift_seq, let c be [0.1, 10], "
       "assuming dim(returns) >= 2, f(s(returns, c)) ~= f(returns)")
NORM = ("for returns in {dom}, let s = mathema.f.scale_seq, let c be [0.1, 10], "
        "f(s(returns, c)) ~= c * f(returns)")


def pd_vol(returns: pd.Series):
    return returns.std() * np.sqrt(252)


def np_vol(returns: np.ndarray):
    return np.std(returns, ddof=1) * np.sqrt(252)


def l2(returns: np.ndarray):
    return np.linalg.norm(returns)


CASES = [(pd_vol, LAW, "pandas.Series.std"), (np_vol, LAW, "numpy.std"),
         (l2, NORM, "numpy.linalg.norm")]


def _lines(fn, law):
    rows = {p.name: p for p in mathema.check(
        fn, claims=[mathema.claim(law, name="c")]).probes}
    float_row = next(p for n, p in rows.items() if n.startswith("c[float"))
    used = {u["key"]: u for u in rows["c"].meta.get("mathema.definitions", [])}
    return rows["c"], float_row, used


@pytest.mark.parametrize("fn, law, key", CASES)
def test_a_bounded_claim_through_the_row_is_proven(fn, law, key):
    main, computation, used = _lines(fn, law.format(dom="[-0.1, 0.1]^n"))
    assert main.verdict == "proven"
    assert computation.verdict == "holds"
    assert used[key]["standing"] == "axiom"


@pytest.mark.parametrize("fn, law, key", CASES)
def test_the_claim_over_the_reals_keeps_its_proof(fn, law, key):
    main, computation, used = _lines(fn, law.format(dom="R^n"))
    assert main.verdict == "proven"
    assert used[key]["standing"] == "axiom"
    if computation.verdict == "falsified":
        assert "e+30" in computation.counterexample or "inf" in computation.counterexample


@pytest.fixture
def verified_here():
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "claims"))
    files = [os.path.join(_bundled_dir(), "pandas", "series.claims.yaml"),
             os.path.join(_bundled_dir(), "numpy", "reductions.claims.yaml"),
             os.path.join(_bundled_dir(), "numpy", "linalg.claims.yaml")]
    from mathema.verify import verify_project
    compendium.uninstall()
    verify_project(root, files=files)
    compendium.uninstall()
    yield root
    compendium.uninstall()


@pytest.mark.parametrize("fn, law, key", CASES)
def test_a_corner_finding_on_the_row_leaves_the_proof_and_the_axiom(
        verified_here, fn, law, key):
    compendium.install(verified_here)
    main, _computation, used = _lines(fn, law.format(dom="[-0.1, 0.1]^n"))
    assert main.verdict == "proven", (main.verdict, main.note)
    assert used[key]["standing"] == "axiom"


def test_a_wrong_row_falls_at_an_ordinary_draw(tmp_path):
    (tmp_path / "claims").mkdir()
    rows = tmp_path / "claims" / "pandas.claims.yaml"
    rows.write_text(textwrap.dedent("""\
        compendium: pandas
        versions: ">=2"
        pandas.Series.std:
          claims:
            - name: definition
              statement: "for a in R^n, assuming dim(a) >= 2, f(a) ~= std(a, ddof=0)"
        """))
    from mathema.verify import verify_project
    compendium.uninstall()
    verify_project(str(tmp_path), files=[str(rows)])
    compendium.uninstall()
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / "pandas.Series.std.yaml").read_text())
    (row,) = [c for c in record["pandas.Series.std"]["claims"]
              if c["name"] == "definition"]
    assert row["verdict"] == "falsified"
    witness = row["counterexample"].split("]")[0].split("[")[1]
    assert all(abs(float(v)) < 1e6 for v in witness.split(","))


def test_the_corner_finding_is_recorded_on_the_row_and_its_line(tmp_path):
    from mathema.verify import verify_project
    (tmp_path / "claims").mkdir()
    compendium.uninstall()
    result = verify_project(str(tmp_path), files=[os.path.join(
        _bundled_dir(), "pandas", "series.claims.yaml")])
    compendium.uninstall()
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / "pandas.Series.std.yaml").read_text())
    (row,) = [c for c in record["pandas.Series.std"]["claims"]
              if c["name"] == "definition"]
    assert row["verdict"] in ("holds", "proven"), row
    finding = row.get("meta", {}).get("mathema.computation_finding", "")
    assert finding.startswith("pandas.Series.std gives no value at "), row
    assert any("note definition: pandas.Series.std gives no value at" in line
               for line in result.lines), result.lines
