# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A listed missing value at which no run could be decided (each run
raised) leaves the claim unknown, never holds, and the note counts the
points that were run."""
from mathema.conjecture import check_conjectures, claim


def plus_y(x, y):
    return 0.0 * x * y + y


def times_zero(x):
    return 0.0 * x


def curved_when_absent(x, y):
    if x is None:
        if 0.25 < y < 0.75:
            return y * y
        return y
    return y


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_a_listed_value_that_raises_at_every_point_beside_an_interval_is_unknown():
    row = _row(plus_y, "for x in {1, None}, y in [0, 1], f(x, y) == y")
    assert row.verdict == "unknown", (row.verdict, row.route, row.note)
    assert "run at 0 points" not in row.note, row.note
    assert "none could be decided" in row.note, row.note


def test_a_listed_value_with_no_other_parameter_that_raises_is_unknown():
    row = _row(times_zero, "for x in {1, None}, f(x) == 0")
    assert row.verdict == "unknown", (row.verdict, row.route, row.note)
    assert "points of  " not in row.note and "points of ," not in row.note, row.note
    assert "x = None was run and could not be decided" in row.note, row.note


def test_a_claim_that_cannot_be_run_at_a_point_is_unknown_at_the_listed_value():
    row = _row(curved_when_absent,
               "for x in {1, None}, y in [0, 1], d(f(x, y), y, y) == 0")
    assert row.verdict == "unknown", (row.verdict, row.route, row.note)
    assert "x = None was not run" in row.note, row.note
