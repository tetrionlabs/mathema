# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A named missing value is judged at every value of the other
parameters it was run at, not only where nothing held: a None its
return type does not admit at one combination falsifies the claim at
that combination, which is the witness printed. The float companion
prints the domain its claim prints."""
from typing import Optional

import mathema
from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in {0, 1, 2}, f(x, y) == 0"


def none_at_one(x: Optional[float], y: float) -> float:
    if x is None:
        return None if y == 1 else 0.0  # type: ignore[return-value]
    return 0.0 * y


def guarded(x: Optional[float]) -> float:
    if x is None:
        raise ValueError("x is required")
    return x


def test_a_none_at_one_value_of_the_others_is_the_witness():
    (row,) = check_conjectures(none_at_one, [claim(TEXT)])
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = None, y = 1"), row.counterexample


def test_the_headline_names_the_failing_combination():
    rec = mathema.check(none_at_one, claims=[claim(TEXT, name="c")])
    head = next(line for line in str(rec).splitlines() if line.startswith("  c  "))
    assert "falsified" in head and "y = 1" in head, head


def test_the_float_companion_is_restated_like_its_claim():
    rec = mathema.check(guarded, claims=[claim("for x in {0.5, 1, None}, f(x) >= 0",
                                               name="c")])
    rows = {p.name: p for p in rec.probes}
    assert "absent" not in rows["c"].statement, rows["c"].statement
    for name, row in rows.items():
        if (row.meta or {}).get("mathema.companion_of") == "c":
            assert "absent" not in row.statement, (name, row.statement)
