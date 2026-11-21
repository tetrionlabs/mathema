# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A proof lowered to holds because its listed missing value was run at
sampled points states what ran: `n` is the number of distinct points
the listed value was run at, the route names the sampled listed value
as a subroute of derive, and the note counts the domain's corners apart
from the drawn points."""
import re

from mathema.conjecture import check_conjectures, claim


def zero_everywhere(x, y):
    if x is None:
        return 0.0
    return 0.0


def test_the_lowered_row_counts_distinct_corners_and_draws():
    (row,) = check_conjectures(
        zero_everywhere, [claim("for x in {1, None}, y in [0, 1], f(x, y) == 0")])
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert row.route == "derive:listed_value_sampled", row.route
    found = re.search(r"x = None was run at (\d+) corners? and (\d+) drawn points? "
                      r"of y and held at (\d+)", row.note)
    assert found, row.note
    corners, drawn, held = map(int, found.groups())
    assert corners >= 1 and drawn >= 1, row.note
    assert row.n == corners + drawn == held, (row.n, row.note)
