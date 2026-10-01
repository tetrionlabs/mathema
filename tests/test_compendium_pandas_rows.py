# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The pandas compendium: every bundled row holds against the
installed pandas.

The pandas rows beyond `pandas/series.claims.yaml` state the running
extrema, least and greatest elements, the methods that move elements
between positions, the arithmetic methods, the order statistics and
the DataFrame reductions. Each is an ordinary claim, and this suite
is where every one is adjudicated against the installed library, as
`mathema verify` does. A wrong row beside each kind of row is
falsified.
"""
from __future__ import annotations

import os
import textwrap

import pytest
import yaml

from mathema.compendium import _bundled_dir
from tests.test_definition_rows import _applies, _record_rows

_FILES = ["pandas/series_running.claims.yaml",
          "pandas/series_bounds.claims.yaml",
          "pandas/series_shape.claims.yaml",
          "pandas/series_arithmetic.claims.yaml",
          "pandas/series_statistics.claims.yaml",
          "pandas/dataframe.claims.yaml"]


def _rows(relative: str) -> list:
    with open(os.path.join(_bundled_dir(), relative)) as fh:
        data = yaml.safe_load(fh)
    return [(key, row["name"]) for key, entry in data.items()
            if isinstance(entry, dict)
            for row in entry.get("claims") or []]


def test_every_pandas_row_file_is_bundled():
    here = sorted(f"pandas/{name}" for name in os.listdir(
        os.path.join(_bundled_dir(), "pandas")) if name.endswith(".yaml"))
    assert here == sorted(_FILES + ["pandas/series.claims.yaml"])


@pytest.mark.library_rows
@pytest.mark.parametrize("relative", _FILES)
def test_every_pandas_row_holds_against_the_installed_pandas(tmp_path,
                                                             relative):
    from mathema import compendium
    from mathema.verify import verify_project
    rows = _rows(relative)
    assert rows, relative
    if not _applies(relative):
        pytest.skip(f"the installed pandas is outside {relative}'s versions")
    try:
        result = verify_project(str(tmp_path), files=[
            os.path.join(_bundled_dir(), relative)])
    finally:
        compendium.uninstall()
    assert not result.problems, result.lines
    for key, name in rows:
        row = _record_rows(tmp_path, key)[name]
        assert row["verdict"] in ("holds", "proven"), (key, name, row)


def test_the_numbers_of_pandas_rows():
    assert {relative: len(_rows(relative)) for relative in _FILES} == {
        "pandas/series_running.claims.yaml": 2,
        "pandas/series_bounds.claims.yaml": 3,
        "pandas/series_shape.claims.yaml": 7,
        "pandas/series_arithmetic.claims.yaml": 12,
        "pandas/series_statistics.claims.yaml": 4,
        "pandas/dataframe.claims.yaml": 2}


@pytest.mark.parametrize("key, name, statement", [
    ("pandas.Series.cummax", "definition",
     "for a in R^n \\\\ {∅}, f(a) == cummin(a)"),
    ("pandas.Series.min", "definition",
     "for a in R^n \\\\ {∅}, f(a) == max(a)"),
    ("pandas.Series.shift", "shifted",
     "for a in R^n \\\\ {∅}, assuming dim(a) >= 2, f(a)[1:] == a[1:]"),
    ("pandas.Series.sub", "definition",
     "for a in R^n \\\\ {∅}, other in R, f(a, other) ~= a + other"),
    ("pandas.Series.quantile", "definition",
     "for a in R^n \\\\ {∅}, f(a) ~= quantile(a, 0.25)"),
    ("pandas.DataFrame.sum", "column_sums",
     "for a in R^n \\\\ {∅}, f(a)[0] ~= mean(a.x)"),
])
def test_a_wrong_pandas_row_is_falsified(tmp_path, key, name, statement):
    from mathema import compendium
    from mathema.verify import verify_project
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "pandas.claims.yaml").write_text(textwrap.dedent(f"""\
        compendium: pandas
        versions: "*"
        {key}:
          claims:
            - name: {name}
              statement: "{statement}"
        """))
    try:
        verify_project(str(tmp_path),
                       files=[str(claims / "pandas.claims.yaml")])
    finally:
        compendium.uninstall()
    row = _record_rows(tmp_path, key)[name]
    assert row["verdict"] == "falsified", row
