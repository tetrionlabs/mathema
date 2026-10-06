# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bundled compendium file verified by path outside its `versions:`
range (the route a user on an older or newer library takes before
exporting the rows that hold) reads its rows exactly as an in-range
verify does: a definition row whose library gives no value only at a
magnitude corner, where the exact value is finite, records a computation
finding and stands, and the function's defaulted parameters stay at
their defaults. No row is falsified by the corner alone."""
import os

import pytest
import yaml

pytest.importorskip("polars")

_FILE = os.path.join("mathema", "compendium", "polars",
                     "series_statistics.claims.yaml")


@pytest.mark.third_party_compendiums
def test_a_corner_is_a_finding_out_of_range_as_in_range(tmp_path, monkeypatch):
    import mathema.compendium as comp
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(
        comp, "_installed_version",
        lambda lib, aliases=(): "3.5.0" if lib == "polars" else real(lib, aliases))
    comp.uninstall()
    try:
        result = verify_project(str(tmp_path), files=[_FILE])
    finally:
        comp.uninstall()
    assert any("outside the file's range" in ln for ln in result.lines), \
        result.lines
    falsified = [ln for ln in result.lines if "falsified" in ln
                 and not ln.startswith("ok")]
    assert falsified == [], result.lines
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / "polars.Series.median.yaml").read_text())
    rows = {c["name"]: c for c in record["polars.Series.median"]["claims"]}
    definition = rows["definition"]
    assert definition["verdict"] in ("holds", "proven"), definition
    assert "mathema.computation_finding" in definition["meta"], definition
    assert definition["meta"]["mathema.outside_versions"] == ">=1,<3"
