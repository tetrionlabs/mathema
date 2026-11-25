# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise at a named missing value that a stated policy row covers
(`absent(f, x) raises(TypeError)`) leaves the value out of the claim's
printed domain, as the function's own raising guard does: the note
names the stated row, and that row holds."""
from typing import Optional

import mathema
from mathema.conjecture import claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"
STATED = "absent(f, x) raises(TypeError)"


def scaled(x: Optional[float], y: float) -> float:
    return (x - 1) * y  # type: ignore[operator]


def test_a_stated_raise_leaves_the_value_out_and_its_row_holds():
    rec = mathema.check(scaled, claims=[claim(TEXT, name="c"), claim(STATED)])
    rows = {p.name: p for p in rec.probes}
    main = rows["c"]
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert ("x = None raises TypeError, as the stated row absent(f, x) "
            "raises(TypeError) says") in main.note, main.note
    stated = [p for p in rec.probes if p.statement.startswith("absent(f, x)")]
    assert stated and all(p.verdict in ("proven", "holds") for p in stated), \
        [(p.name, p.verdict, p.note) for p in stated]
