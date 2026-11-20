# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose domain lists a missing value for one parameter
(`x in {1, None}`, `x in {1, nan}`) states the relation at that value
for every value of the other parameters. Derive proves the real points;
the listed value is then run. Where every other parameter is finite,
every combination is run and a proof stands when each one holds. Beside
an interval the listed value is run at sampled points, which is
evidence and not a proof: the claim holds rather than being proven, or
is falsified at the first point that fails."""
from mathema.conjecture import check_conjectures, claim


def spike_at_half(x, y):
    if x is None:
        if y == 0.5:
            return 1.0
        return 0.0
    return 0.0


def bump_when_absent(x, y):
    if x is None:
        if 0.25 < y < 0.75:
            return 1.0
        return 0.0
    return 0.0


def bump_when_nan(x, y):
    if x != x:
        if 0.25 < y < 0.75:
            return 1.0
        return 0.0
    return 0.0


def bump_when_second_absent(x, y):
    if y is None:
        if 0.25 < x < 0.75:
            return 1.0
        return 0.0
    return 0.0


def bump_of_three(x, y, z):
    if x is None:
        if 0.25 < y < 0.75 and 0.25 < z < 0.75:
            return 1.0
        return 0.0
    return 0.0


def curved_when_absent(x, y):
    if x is None:
        if 0.25 < y < 0.75:
            return y * y
        return y
    return y


def zero_but_rare(x, y):
    if x is None:
        if y == 0.123456:
            return 1.0
        return 0.0
    return 0.0


def zero_everywhere(x, y):
    if x is None:
        return 0.0
    return 0.0


def zero_of_three(x, y, z):
    if x is None:
        return 0.0
    return 0.0


def zero_of_one(x):
    if x is None:
        return 0.0
    return 0.0


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_the_reported_case_is_not_proven():
    assert spike_at_half(None, 0.5) == 1.0
    row = _row(spike_at_half, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert row.verdict in ("holds", "falsified"), (row.verdict, row.route, row.note)


def test_an_absent_value_failing_inside_an_interval_is_falsified_there():
    row = _row(bump_when_absent, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = None"), row.counterexample


def test_a_listed_nan_failing_inside_an_interval_is_falsified_there():
    row = _row(bump_when_nan, "for x in {1, nan}, y in [0, 1], f(x, y) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = nan"), row.counterexample


def test_the_listed_value_on_the_second_parameter_is_run_across_the_first():
    row = _row(bump_when_second_absent,
               "for x in [0, 1], y in {1, None}, f(x, y) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert "y = None" in row.counterexample, row.counterexample


def test_the_listed_value_is_run_across_two_other_parameters():
    row = _row(bump_of_three,
               "for x in {1, None}, y in [0, 1], z in [0, 1], f(x, y, z) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = None"), row.counterexample


def test_beside_a_finite_set_every_combination_is_run():
    row = _row(spike_at_half, "for x in {1, None}, y in {0, 0.5, 1}, f(x, y) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = None, y = 0.5", row.counterexample


def test_beside_a_finite_set_a_point_off_the_corners_is_run():
    row = _row(zero_but_rare,
               "for x in {1, None}, y in {0, 0.123456, 1}, f(x, y) == 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = None, y = 0.123456", row.counterexample


def test_beside_an_interval_a_rare_failing_point_is_never_proven():
    row = _row(zero_but_rare, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert row.verdict in ("holds", "falsified"), (row.verdict, row.route, row.note)


def test_a_chained_comparison_runs_the_listed_value_inside_the_interval():
    row = _row(bump_when_absent,
               "for x in {1, None}, y in [0, 1], f(x, y) in [0, 0.5]")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)


def test_a_claim_that_cannot_be_run_at_a_point_is_not_proven_at_the_listed_value():
    row = _row(curved_when_absent,
               "for x in {1, None}, y in [0, 1], d(f(x, y), y, y) == 0")
    assert row.verdict != "proven", (row.verdict, row.route, row.note)
    assert "x = None was not run" in row.note, row.note


def test_a_true_claim_beside_an_interval_holds_and_says_what_was_sampled():
    row = _row(zero_everywhere, "for x in {1, None}, y in [0, 1], f(x, y) == 0")
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "the real points were derived" in row.note, row.note
    assert "x = None was run at" in row.note, row.note
    assert "points of y" in row.note, row.note


def test_a_true_claim_beside_finite_sets_stays_proven():
    row = _row(zero_everywhere, "for x in {1, None}, y in {0, 0.5, 1}, f(x, y) == 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    row = _row(zero_of_three,
               "for x in {1, None}, y in {0, 1}, z in {2, 3}, f(x, y, z) == 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)


def test_a_true_claim_with_no_other_parameter_stays_proven():
    row = _row(zero_of_one, "for x in {1, None}, f(x) == 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
