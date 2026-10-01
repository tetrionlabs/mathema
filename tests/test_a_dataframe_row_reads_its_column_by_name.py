# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A DataFrame row reads the result's column `x` by name.

A pandas.DataFrame method answers per column, labelled by the column's
name, so a row reads the answer for column `x` as `f(a)["x"]`: it then
says the same thing whatever other columns the table has and in
whatever order. A table whose first column is `y` keeps its `x` entry
under `"x"`, never at position 0, so no row reads a result by position.
"""
from __future__ import annotations

import os
import re

import pandas as pd
import pytest
import yaml

from mathema.compendium import _bundled_dir


def _rows() -> dict:
    with open(os.path.join(_bundled_dir(), "pandas",
                           "dataframe.claims.yaml")) as fh:
        data = yaml.safe_load(fh)
    return {key.rsplit(".", 1)[1]: entry["claims"][0]
            for key, entry in data.items() if isinstance(entry, dict)}


def _with_y_first(method: str):
    """The DataFrame method called on the table with a column `y` put
    in front of its columns."""
    def g(a: pd.DataFrame):
        frame = a.copy()
        frame.insert(0, "y", [100.0 + 7.0 * i for i in range(len(frame))])
        return getattr(pd.DataFrame, method)(frame)
    g.__name__ = f"{method}_with_y_first"
    return g


def test_the_x_entry_is_not_the_first_entry_of_a_table_led_by_y():
    frame = pd.DataFrame({"y": [1.0, 2.0, 10.0], "x": [1.0, 1.0, 1.0]})
    assert frame.max()["x"] == 1.0 and frame.max().iloc[0] == 10.0
    assert frame.std()["x"] == 0.0 and frame.std().iloc[0] > 4.9


def test_no_dataframe_row_reads_a_result_by_position():
    for method, row in _rows().items():
        assert not re.search(r"f\(a\)\[\s*-?\d", row["statement"]), \
            (method, row["statement"])
        assert 'f(a)["x"]' in row["statement"], (method, row["statement"])


@pytest.mark.parametrize("method", sorted(_rows()))
def test_the_row_holds_for_a_table_whose_first_column_is_not_x(method):
    from mathema.conjecture import check_conjectures, claim
    row = _rows()[method]
    (p,) = check_conjectures(_with_y_first(method),
                             [claim(row["statement"], name=row["name"])])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)
