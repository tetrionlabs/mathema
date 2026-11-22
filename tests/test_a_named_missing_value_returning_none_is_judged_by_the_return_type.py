# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where the function returns None or nan at a named missing value, its
return annotation judges the result: a return type that does not admit
it falsifies, with that point as the witness; one that admits it (or
no annotation) leaves the point out of the claim's printed domain, the
claim holds over the rest, and the note says what was returned."""
import math
from typing import Optional

from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def none_under_float(x: Optional[float], y: float) -> float:
    if x is None:
        return None
    return (x - 1) * y


def none_under_optional(x: Optional[float], y: float) -> "float | None":
    if x is None:
        return None
    return (x - 1) * y


def none_unannotated(x: Optional[float], y: float):
    if x is None:
        return None
    return (x - 1) * y


def root(x: float) -> float:
    return math.sqrt(x)


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_none_under_a_float_return_falsifies():
    row = _row(none_under_float, TEXT)
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = None"), row.counterexample
    assert "return type float does not admit" in (row.sketch or ""), row.sketch


def test_none_under_an_optional_return_holds_over_the_rest():
    row = _row(none_under_optional, TEXT)
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "absent" not in row.statement, row.statement
    assert "x = None is left out of the domain: f returned None there" in row.note, \
        row.note


def test_none_with_no_return_annotation_holds_over_the_rest():
    row = _row(none_unannotated, TEXT)
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "absent" not in row.statement, row.statement


def test_a_propagated_nan_under_a_float_return_holds_over_the_rest():
    row = _row(root, "for x in [0, 1] | {nan}, f(x) >= 0")
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "nan" not in row.statement, row.statement
    assert "x = nan is left out of the domain: f returned nan there" in row.note, \
        row.note
