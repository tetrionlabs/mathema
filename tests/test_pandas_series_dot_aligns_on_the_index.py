# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""pandas.Series.dot pairs elements by index label, not by position.

`s.dot(t)` for two Series multiplies the elements that share a label,
so a reordered `t` gives the same answer as `t` itself and a different
index raises. The grammar's `dot(a, other)` pairs by position, so no
bundled row states `pandas.Series.dot` as `dot(a, other)`.
"""
from __future__ import annotations

import pandas as pd
import pytest


def test_a_reordered_series_is_paired_by_label():
    s = pd.Series([1.0, 2.0, 3.0])
    t = s.sort_values(ascending=False)
    assert s.dot(t) == 14.0
    assert sum(x * y for x, y in zip(s.tolist(), t.tolist())) == 10.0


def test_a_series_with_another_index_raises():
    with pytest.raises(ValueError):
        pd.Series([1.0, 2.0]).dot(pd.Series([1.0, 2.0], index=[5, 6]))


def test_no_bundled_row_states_series_dot_by_position():
    from mathema.compendium import compendium_functions
    rows = (compendium_functions().get("pandas.Series.dot") or {}).get(
        "claims") or []
    assert not [r for r in rows if "dot(a, other)" in r["statement"]], rows
