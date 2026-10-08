# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Definition rows: library claims that say what a function computes.

mathema bundles, for numpy, pandas.Series and polars.Series, one row
named `definition` per function (and `definition@ddof=1` where a call
pins a parameter), stated in the grammar's own words over inputs with
nothing missing: `pandas.Series.std` is `std(a, ddof=1)`. Each is an
ordinary claim, and `mathema verify` adjudicates it against the
installed library like any other; this suite is where every bundled
row is checked. A method's receiver is the row's first parameter `a`,
sampled as the method's own class. A wrong definition row is
falsified.
"""
from __future__ import annotations

import inspect
import os
import textwrap

import pytest
import yaml

from mathema.compendium import _bundled_dir
from mathema.conjecture import _resolve_func_ref

_FILES = ["numpy/reductions.claims.yaml", "numpy/definitions.claims.yaml",
          "numpy/definitions_2_4.claims.yaml", "pandas/series.claims.yaml",
          "polars/series.claims.yaml"]


def _applies(relative: str) -> bool:
    from mathema.compendium import _installed_version, _version_in_range
    with open(os.path.join(_bundled_dir(), relative)) as fh:
        data = yaml.safe_load(fh)
    installed = _installed_version(data["compendium"])
    return installed is not None and _version_in_range(
        installed, str(data["versions"]))


def _definition_rows(relative: str) -> list:
    with open(os.path.join(_bundled_dir(), relative)) as fh:
        data = yaml.safe_load(fh)
    return [(key, row["name"]) for key, entry in data.items()
            if isinstance(entry, dict)
            for row in entry.get("claims") or []
            if row["name"].split("@")[0] == "definition"]


def _expected_battery_skips(relative: str) -> list:
    """The `callable`-battery rows `verify` is expected to report skipped
    for a bundled file on the installed library, as `<key>: 1 skipped
    claim(s)`: none. `numpy.sum` before numpy 2.4 is a Python wrapper
    whose source writes to its `out` argument; its battery is judged at
    the default call (`out=None`), where nothing is written."""
    return []


def _record_rows(root, key: str) -> dict:
    path = os.path.join(root, ".mathema", "verified", f"{key}.yaml")
    with open(path) as fh:
        entry = yaml.safe_load(fh)[key]
    return {c["name"]: c for c in entry["claims"]}


@pytest.mark.third_party_compendiums
@pytest.mark.parametrize("relative", _FILES)
def test_every_bundled_definition_row_holds_against_the_installed_library(
        tmp_path, relative):
    from mathema import compendium
    from mathema.verify import verify_project
    rows = _definition_rows(relative)
    assert rows, relative
    if not _applies(relative):
        pytest.skip(f"the installed library is outside {relative}'s versions")
    try:
        result = verify_project(str(tmp_path), files=[
            os.path.join(_bundled_dir(), relative)])
    finally:
        compendium.uninstall()
    assert sorted(result.problems) == _expected_battery_skips(relative), result.lines
    for key, name in rows:
        row = _record_rows(tmp_path, key)[name]
        assert row["verdict"] in ("holds", "proven"), (key, name, row)
    for problem in _expected_battery_skips(relative):
        key = problem.split(":")[0]
        assert _record_rows(tmp_path, key)["purity"]["verdict"] == "skipped"


def test_the_numbers_of_bundled_definition_rows():
    counted = {relative: len(_definition_rows(relative))
               for relative in _FILES}
    assert counted == {"numpy/reductions.claims.yaml": 8,
                       "numpy/definitions.claims.yaml": 16,
                       "numpy/definitions_2_4.claims.yaml": 2,
                       "pandas/series.claims.yaml": 10,
                       "polars/series.claims.yaml": 11}


def test_a_method_key_is_a_function_of_its_receiver_a():
    for library in ("numpy", "pandas", "polars"):
        pytest.importorskip(library)
    import numpy as np
    import pandas as pd
    import polars as pl
    std = _resolve_func_ref("pandas.Series.std")
    params = inspect.signature(std).parameters
    assert list(params)[0] == "a"
    assert params["a"].annotation is pd.Series
    assert params["ddof"].default == 1
    assert std(pd.Series([1.0, 3.0])) == pytest.approx(2 ** 0.5)
    assert inspect.signature(
        _resolve_func_ref("polars.Series.std")).parameters["ddof"].default \
        == 1
    transpose = _resolve_func_ref("numpy.ndarray.T")
    assert list(inspect.signature(transpose).parameters) == ["a"]
    assert transpose(np.array([[1.0, 2.0]])).shape == (2, 1)
    assert _resolve_func_ref("numpy.ndarray.T") is transpose
    assert _resolve_func_ref("polars.Series.cum_sum")(
        pl.Series([1.0, 2.0])).to_list() == [1.0, 3.0]


@pytest.mark.parametrize("library, key, statement", [
    ("pandas", "pandas.Series.std",
     "for a in R^n \\\\ {∅}, f(a) ~= std(a, ddof=0)"),
    ("polars", "polars.Series.var",
     "for a in R^n \\\\ {∅}, f(a) ~= var(a, ddof=0)"),
    ("numpy", "numpy.ndarray.std",
     "for a in R^n \\\\ {∅}, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1)"),
])
def test_a_wrong_definition_row_is_falsified(tmp_path, library, key,
                                             statement):
    pytest.importorskip(library)
    from mathema import compendium
    from mathema.verify import verify_project
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / f"{library}.claims.yaml").write_text(textwrap.dedent(f"""\
        compendium: {library}
        versions: "*"
        {key}:
          claims:
            - name: definition
              statement: "{statement}"
        """))
    try:
        verify_project(str(tmp_path),
                       files=[str(claims / f"{library}.claims.yaml")])
    finally:
        compendium.uninstall()
    row = _record_rows(tmp_path, key)["definition"]
    assert row["verdict"] == "falsified", row
