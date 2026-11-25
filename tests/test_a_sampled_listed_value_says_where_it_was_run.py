# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Beside an interval a listed missing value is run at sampled points;
where no run there was decided (an unguarded raise, or a mix of None
and nan), the note says at how many sampled points of the other
parameters it was run and what it did there, rather than reading as
true of every point. A None or nan the return type admits (here there
is no return annotation) leaves the value out of the printed domain."""
from mathema.conjecture import check_conjectures, claim


def raises_when_absent(x, y):
    return float(x) * 0.0 * y


def none_or_nan_when_absent(x, y):
    if x is None:
        if y < 0.5:
            return None
        return float("inf") - float("inf")
    return 0.0 * y


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_a_raise_at_every_sampled_point_is_counted_in_the_note():
    row = _row(raises_when_absent, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert "the listed value x = None was run at" in row.note, row.note
    assert "drawn points of y and raised TypeError at each" in row.note, row.note


def test_mixed_outcomes_at_the_sampled_points_are_counted_in_the_note():
    row = _row(none_or_nan_when_absent, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert row.statement.startswith("for x in {1}, "), row.statement
    assert "the listed value x = None was run at" in row.note, row.note
    assert "drawn points of y" in row.note, row.note
    assert "f returned None at" in row.note and " and nan at " in row.note, row.note
