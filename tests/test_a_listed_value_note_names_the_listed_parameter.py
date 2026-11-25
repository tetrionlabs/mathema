# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The points a listed missing value is run at are called with each
argument in its own parameter's place, so the record names the
parameter that lists the value even when it comes first in the
signature."""
from mathema.conjecture import check_conjectures, claim


def zero_everywhere(x, y):
    if x is None:
        return 0.0
    return 0.0


def test_the_note_and_the_record_name_the_listed_parameter():
    (row,) = check_conjectures(
        zero_everywhere, [claim("for x in {1, None}, y in {0, 0.5, 1}, f(x, y) == 0")])
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "at x = None" in row.note, row.note
    assert "at y = None" not in row.note, row.note
    said = (row.meta or {}).get("mathema.missing", {}).get("said", {})
    assert "x" in said and "y" not in said, said
