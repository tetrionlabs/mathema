# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A column whose binding excludes missing values never holds one.

`for a.r in [0, 1]^n \\ {missing}` says column `r` has a value in every
row, whatever the table's type admits; the other columns keep the
holes the type admits. A draw with a hole in `r` is outside the claim,
so it never falsifies it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402


def holes_in_r(a: pd.DataFrame):
    return float(a["r"].isna().sum()) + 0.0 * float(len(a["w"]))


def holes_in_w(a: pd.DataFrame):
    return float(a["w"].isna().sum()) + 0.0 * float(len(a["r"]))


_BOUND = "for a.r in [0, 1]^n \\ {missing}, a.w in [0, 1]^n, "


def test_the_excluding_column_has_no_hole():
    (p,) = check_conjectures(holes_in_r, [claim(_BOUND + "f(a) == 0")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


def test_the_other_column_keeps_the_holes_its_type_admits():
    (p,) = check_conjectures(holes_in_w, [claim(_BOUND + "f(a) == 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_column_excluding_one_member_keeps_the_others():
    def nan_in_r(a: pd.DataFrame):
        return float(sum(1 for v in a["r"].tolist()
                         if isinstance(v, float) and v != v))
    (p,) = check_conjectures(
        nan_in_r, [claim("for a.r in [0, 1]^n \\ {nan}, f(a) == 0")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


def test_a_string_column_excluding_missing_has_no_hole():
    def holes_in_k(a: pd.DataFrame):
        return float(a["k"].isna().sum())
    (p,) = check_conjectures(
        holes_in_k, [claim('for a.k in {"u", "v"}^n \\ {missing}, f(a) == 0')])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)
