# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where the function raises at a named missing value behind its own
guard, the claim's printed domain leaves that value out, the note names
the guard and the policy row that shows it is in place, and that row
holds. A raise no guard covers falsifies the policy row, as before."""
from typing import Optional

import mathema
from mathema.conjecture import claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def guarded(x: Optional[float], y: float) -> float:
    if x is None:
        raise ValueError("x is required")
    return (x - 1) * y


def unguarded(x: Optional[float], y: float) -> float:
    return (x - 1) * y  # type: ignore[operator]


def _rows(fn):
    rec = mathema.check(fn, claims=[claim(TEXT, name="c")])
    return {p.name: p for p in rec.probes}


def test_a_guarded_raise_leaves_the_value_out_and_its_row_holds():
    rows = _rows(guarded)
    main = rows["c"]
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert ("x = None raises ValueError, from the guard on line 2 (absent[x])"
            in main.note), main.note
    assert rows["absent[x]"].verdict == "proven", rows["absent[x]"].note


def test_an_unguarded_raise_falsifies_the_policy_row():
    rows = _rows(unguarded)
    assert rows["absent[x]"].verdict == "falsified", rows["absent[x]"].note
