# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that cannot be run at a point (a derivative) is derived over
the real points; where the function returns an ordinary value at a
listed missing value, on a branch derive does not read, the claim holds
over the real points, the printed domain leaves the value out, and the
absent policy row for the parameter is in the record."""
import mathema
from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], d(f(x, y), y) == 1"


def slope_when_absent(x, y):
    if x is None:
        return 2 * y
    return y


def test_the_claim_holds_over_the_real_points_and_the_policy_row_is_kept():
    (row,) = check_conjectures(slope_when_absent, [claim(TEXT)])
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert ("the relation was derived over the real points; f returns a value "
            "at x = None, on a branch derive did not read") in row.note, row.note
    rec = mathema.check(slope_when_absent, claims=[claim(TEXT, name="c")])
    (main,) = [p for p in rec.probes if p.name == "c"]
    assert main.verdict == "holds", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert [p.name for p in rec.probes if p.name == "absent[x]"] == ["absent[x]"]
