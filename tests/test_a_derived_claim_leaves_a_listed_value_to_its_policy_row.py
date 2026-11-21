# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that cannot be run at a point (a derivative) is derived over
the real points, and a listed missing value is judged by its policy
row, not by the relation: the proof stands, its note says so, and the
absent policy row for the parameter is in the record."""
import mathema
from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], d(f(x, y), y) == 1"


def slope_when_absent(x, y):
    if x is None:
        return 2 * y
    return y


def test_the_proof_stands_and_the_listed_value_goes_to_its_policy_row():
    (row,) = check_conjectures(slope_when_absent, [claim(TEXT)])
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert ("the relation was derived over the real points; the listed value "
            "x = None is judged by its policy row") in row.note, row.note
    rec = mathema.check(slope_when_absent, claims=[claim(TEXT, name="c")])
    (main,) = [p for p in rec.probes if p.name == "c"]
    assert main.verdict == "proven", (main.verdict, main.note)
    assert [p.name for p in rec.probes if p.name == "absent[x]"] == ["absent[x]"]
