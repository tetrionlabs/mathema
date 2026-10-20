# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A table column the claim binds is drawn, even when nothing else in
the claim or the body reads it.

`for a.r in [0, 1]^n, f(a) == 1` says the table has a column `r` of
numbers in `[0, 1]`; the function receives a table with that column,
never one with made-up columns in its place.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402


def width(a: pd.DataFrame):
    return float(len(a.columns))


def test_the_bound_column_is_the_tables_column():
    (p,) = check_conjectures(
        width, [claim("for a.r in [0, 1]^n \\ {missing}, f(a) == 1")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


def test_three_bound_columns_are_all_drawn():
    (p,) = check_conjectures(
        width, [claim("for a.r in [0, 1]^n \\ {missing}, "
                      "a.w in [-1, 1]^n \\ {missing}, "
                      "a.v in [1, 2]^n \\ {missing}, f(a) == 3")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)
