# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that cannot be run at a point (a derivative), over a named
missing value where the function returns ordinary values on its own
branch, is not proven over that value unless derive reads the branch:
the claim holds over the real points, the printed domain leaves the
value out, and the note says so. Where the function does not return an
ordinary value there, the proof over the real points stands and the
value is judged by its policy row, left out of the printed domain."""
from typing import Optional

from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], d(f(x, y), y) == 1"


def doubled_slope_when_absent(x: Optional[float], y: float) -> float:
    if x is None:
        return 2 * y
    return y + x


def raises_when_absent(x: Optional[float], y: float) -> float:
    if x is None:
        raise ValueError("x is required")
    return y + x


def _row(fn):
    (row,) = check_conjectures(fn, [claim(TEXT)])
    return row


def test_an_ordinary_branch_at_the_named_value_is_not_proven():
    row = _row(doubled_slope_when_absent)
    assert row.verdict in ("holds", "falsified"), (row.verdict, row.route, row.note)
    if row.verdict == "holds":
        assert "absent" not in row.statement, row.statement
        assert "derive did not read" in row.note, row.note


def test_a_raise_at_the_named_value_keeps_the_proof_and_leaves_it_out():
    row = _row(raises_when_absent)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "absent" not in row.statement, row.statement
    assert "x = None is judged by its policy row" in row.note, row.note
