# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A listed missing value at which every run raised is not judged by the
proof: the raise is classified by the claim's missing-value rows, and
the proof of the real points stands with no count of held points. A
claim that cannot be run at a point at all is proven over the real
points and leaves the listed value to its policy row."""
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


def test_a_listed_value_that_raises_at_every_point_beside_an_interval_is_classified():
    row = _row(plus_y, "for x in {1, None}, y in [0, 1], f(x, y) == y")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "run at 0 points" not in row.note, row.note
    assert "at x = None f raised TypeError" in row.note, row.note


def test_a_listed_value_with_no_other_parameter_that_raises_is_classified():
    row = _row(times_zero, "for x in {1, None}, f(x) == 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "points of" not in row.note, row.note
    assert "at x = None f raised TypeError" in row.note, row.note


def test_a_claim_that_cannot_be_run_at_a_point_is_proven_and_names_the_policy_row():
    row = _row(curved_when_absent,
               "for x in {1, None}, y in [0, 1], d(f(x, y), y, y) == 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "the listed value x = None is judged by its policy row" in row.note, row.note
