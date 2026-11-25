# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing value the author writes into the claim is named whatever
the spelling: `[0, 1] | {None}`, `: float|absent` or `| {nan}` name it
as `{0.5, None}` does. Where the function returns an ordinary value at
a named value, the claim judges it, and a wrong value falsifies with
that point as the witness."""
import math
from typing import Optional

from mathema.conjecture import check_conjectures, claim


def minus_one_when_absent(x: Optional[float]) -> float:
    if x is None:
        return -1.0
    return x


def minus_one_when_absent_float(x: float) -> float:
    if x is None:
        return -1.0
    return x


def minus_one_when_nan(x: float) -> float:
    if x is None:
        return -1.0
    return -1.0 if x != x else x


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_a_union_with_none_is_judged_at_none():
    row = _row(minus_one_when_absent, "for x in [0, 1] | {None}, f(x) >= 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = None", row.counterexample


def test_a_type_clause_with_absent_is_judged_at_none():
    row = _row(minus_one_when_absent_float, "for x in [0, 1] : float|absent, f(x) >= 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = None", row.counterexample


def test_a_union_with_nan_is_judged_at_nan():
    row = _row(minus_one_when_nan, "for x in [0, 1] | {nan}, f(x) >= 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = nan", row.counterexample


def test_a_value_only_the_annotation_admits_is_not_judged():
    row = _row(minus_one_when_absent, "for x in [0, 1], f(x) >= 0")
    assert row.verdict != "falsified", (row.verdict, row.route, row.note)
    assert math.isfinite(minus_one_when_absent(0.5))
