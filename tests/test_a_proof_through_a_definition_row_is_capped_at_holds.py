# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A trusted definition row is an axiom; a row only verified by
execution is evidence, and caps a proof through it at `holds`.

A `definition` row mathema bundles, read with the installed library
inside the row's version range, or one the user accepted `--as
trusted`, is taken at face value: a proof through it stays `proven`,
and its sketch names it ("taking numpy.sum as sum(a) (axiom, bundled
with mathema, numpy 2.0 to 2.x)"). A project row `mathema verify`
recorded as holding, and not accepted, is evidence: the proof is
`holds`, and its sketch says how to lift it ("accept the row as
trusted: mathema accept KEY ROW --as trusted"). So is a bundled row
whose version range excludes the installed library.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

import textwrap  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from mathema import compendium  # noqa: E402
from mathema.claims import check_conjectures, claim  # noqa: E402

_SCALE = ("let s = mathema.f.scale_seq, let c be [0.1, 10], "
          "for x in [-1, 1]^n, f(s(x, c)) ~= c * f(x)")

_MULTIPLY_ROW = textwrap.dedent("""\
    compendium: pandas
    versions: ">=2"

    pandas.Series.multiply:
      claims:
        - name: definition
          statement: "for a in R^n \\\\ {∅}, other in [-1e6, 1e6], f(a, other) == a * other"
    """)


def total(x: np.ndarray) -> float:
    """The sum of the elements."""
    return float(np.sum(x))


def doubled_mean(x: pd.Series) -> float:
    """Twice the mean, through Series.multiply."""
    return x.multiply(2.0).mean()


def _check(root, fn, law=_SCALE):
    compendium.uninstall()
    if root is not None:
        compendium.install(str(root))
    try:
        (p,) = check_conjectures(fn, [claim(law, route="derive")])
    finally:
        compendium.uninstall()
    return p


def _used(p) -> dict:
    return {u["key"]: u for u in (p.meta or {}).get("mathema.definitions", [])}


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "claims").mkdir()
    yield tmp_path
    compendium.uninstall()


@pytest.mark.needs_full_proof_budget
def test_a_bundled_row_is_an_axiom_and_the_proof_stays_proven():
    p = _check(None, total)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    row = _used(p)["numpy.sum"]
    assert row["standing"] == "axiom" and row["trusted_by"] == "mathema"
    assert row["versions"] and row["installed"]
    assert "taking numpy.sum as sum(a) (axiom, bundled with mathema, " \
           "numpy 2.0 to 2.x)" in (p.sketch or ""), p.sketch


def _verify_rows(root):
    from mathema.verify import verify_project
    compendium.uninstall()
    try:
        verify_project(str(root), files=[str(root / "claims"
                                             / "pandas.claims.yaml")])
    finally:
        compendium.uninstall()


@pytest.mark.needs_full_proof_budget
def test_a_verified_project_row_is_evidence_and_caps_the_proof(project):
    (project / "claims" / "pandas.claims.yaml").write_text(_MULTIPLY_ROW)
    _verify_rows(project)
    p = _check(project, doubled_mean)
    assert p.verdict == "holds", (p.verdict, p.sketch, p.note)
    row = _used(p)["pandas.Series.multiply"]
    assert row["standing"] == "evidence", row
    assert ("accept the row as trusted: mathema accept "
            "pandas.Series.multiply definition --as trusted") in \
        (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_the_same_row_accepted_as_trusted_is_an_axiom(project):
    (project / "claims" / "pandas.claims.yaml").write_text(_MULTIPLY_ROW)
    statement = yaml.safe_load(_MULTIPLY_ROW)["pandas.Series.multiply"][
        "claims"][0]["statement"]
    verified = project / ".mathema" / "verified"
    verified.mkdir(parents=True)
    (verified / "pandas.Series.multiply.yaml").write_text(yaml.safe_dump({
        "pandas.Series.multiply": {"claims": [
            {"name": "definition", "statement": statement,
             "verdict": "holds", "accepted": {
                 "as": "trusted", "statement": statement,
                 "versions": ">=2"}}]}}))
    p = _check(project, doubled_mean)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    row = _used(p)["pandas.Series.multiply"]
    assert row["standing"] == "axiom" and row["trusted_by"] == "user", row
    assert "(axiom, accepted as trusted" in (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_a_bundled_row_outside_its_versions_is_evidence(monkeypatch):
    from mathema import definitions
    from mathema.compendium import OUTSIDE_VERSIONS
    real = definitions._library_claims

    def outside(root, load):
        library = real(root, load)
        info = dict(library["numpy.sum"])
        entry = dict(info["entry"])
        entry["claims"] = [
            {**r, "versions": ">=99",
             "meta": {**(r.get("meta") or {}), OUTSIDE_VERSIONS: ">=99"}}
            for r in entry.get("claims") or []]
        info["entry"] = entry
        return {**library, "numpy.sum": info}
    monkeypatch.setattr(definitions, "_library_claims", outside)
    p = _check(None, total)
    assert p.verdict == "holds", (p.verdict, p.sketch, p.note)
    row = _used(p)["numpy.sum"]
    assert row["standing"] == "evidence" and row["versions"] == ">=99", row
    assert "accept the row as trusted" in (p.sketch or ""), p.sketch
