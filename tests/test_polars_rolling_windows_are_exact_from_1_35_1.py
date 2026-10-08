# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""polars' rolling sum and mean agree with the window's own sum from
polars 1.35.1 on.

Before 1.35.1 a large element leaving the window took the small
elements' digits with it:
`pl.Series([1e16, 1, 1, -1e16, 1, 1]).rolling_sum(2)` gave 1.0 at
the window `[1, 1]` on polars 1.0 to 1.34. The rolling rows therefore
apply from 1.35.1, and on an older polars they are adjudicated but
never used as facts.
"""
import os

import pytest
import yaml

from mathema.compendium import _bundled_dir, _version_in_range


def _rolling_rows() -> list:
    with open(os.path.join(_bundled_dir(), "polars",
                           "series_shape.claims.yaml")) as fh:
        data = yaml.safe_load(fh)
    return [(key, row) for key, entry in data.items()
            if key.startswith("polars.Series.rolling_")
            for row in entry["claims"]]


@pytest.mark.parametrize("version, applies", [
    ("1.0.0", False), ("1.20.0", False), ("1.34.0", False),
    ("1.35.1", True), ("1.44.2", True)])
def test_the_rolling_rows_apply_where_the_window_sum_is_exact(version,
                                                              applies):
    rows = _rolling_rows()
    assert rows
    for key, row in rows:
        assert _version_in_range(version, str(row.get("versions", "*"))) \
            is applies, (key, row["name"], version)


def test_the_installed_polars_sums_a_window_exactly_where_the_rows_apply():
    pl = pytest.importorskip("polars")
    (key, row), *_ = _rolling_rows()
    if not _version_in_range(pl.__version__, str(row["versions"])):
        pytest.skip(f"polars {pl.__version__} is outside {row['versions']}")
    got = pl.Series([1e16, 1.0, 1.0, -1e16, 1.0, 1.0]).rolling_sum(2)
    assert got.to_list()[2] == 2.0
