# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every draw of a table has one row count, shared by all its columns.

A table's columns are vectors of one length `n`. The draws that put a
column the claim binds at the corners of its own range (`for a.r in
[0, 1]^n` meets `[0, 1]`) lengthen a one-row table to two rows, and
then lengthen every other column with it, so the function always
receives a table, never columns of different lengths.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from mathema import _floor  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402


def rows_read(a: pd.DataFrame):
    return float(len(a)) + 0.0 * float(len(a["w"])) * float(len(a["k"]))


@pytest.mark.parametrize("text", [
    "for a.r in [0, 1]^n \\ {missing}, f(a) >= 1",
    "for a.r in [0, 1]^n \\ {missing}, a.w in {1, 2}^n \\ {missing}, f(a) >= 1",
    'for a.r in [0, 1]^n \\ {missing}, a.k in {"u", "v"}^n \\ {missing}, f(a) >= 1',
])
def test_a_table_bound_by_column_is_drawn_with_one_row_count(text):
    (p,) = check_conjectures(rows_read, [claim(text)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


@pytest.mark.parametrize("corners, own", [
    ([[-1.0, 1.0]], {}),
    ([], {"r": [[0.0, 1.0]]}),
    ([], {"r": [[0.0, 1.0]], "k": []}),
])
def test_a_corner_of_a_one_row_table_lengthens_every_column(corners, own):
    items = _floor.table_corner_floor(corners, own)
    base = {"r": [0.5], "w": [2], "k": ["u"]}
    for item in items:
        made = item(base)
        assert made is not None
        assert len({len(col) for col in made.values()}) == 1, made
    cornered = items[-1](base)
    assert len(cornered["r"]) == 2
    if own:
        assert cornered["w"] == [2, 2] and cornered["k"] == ["u", "u"]
