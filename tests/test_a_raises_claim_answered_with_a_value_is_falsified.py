# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`raises(f(None), E)` where the call returns a value is falsified at
that call: the function returned a value instead of raising."""
from typing import Optional

from mathema.conjecture import check_conjectures, claim


def zero_when_absent(x: Optional[float]) -> float:
    if x is None:
        return 0.0
    return x


def test_a_value_where_a_raise_was_claimed_falsifies():
    (row,) = check_conjectures(zero_when_absent, [claim("raises(f(None), ValueError)")])
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert "returned 0.0 instead of raising ValueError" in row.note, row.note
