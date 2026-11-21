# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sweep of a listed missing value over finite sets stops once it has
run for the brute-force sweep's time budget, whatever the estimate
before it said: the claim then holds, and the note says the time budget
stopped it after so many of its points. A grid over the sweep's point
budget says that budget instead."""
import time

from mathema.conjecture import check_conjectures, claim

_SLOW_SECONDS = 0.002


def slow_off_the_trial(a, x):
    if x is None:
        if a % 10 != 0:
            time.sleep(_SLOW_SECONDS)
        return 0.0
    return 0.0


def zero_of_two(a, x):
    if x is None:
        return 0.0 * a
    return 0.0


def test_a_sweep_slower_than_its_estimate_stops_at_the_time_budget(monkeypatch):
    import mathema._brute_force as B
    monkeypatch.setattr(B, "_SWEEP_SECONDS", 0.05)
    members = ", ".join(str(i) for i in range(200))
    text = f"for a in {{{members}}}, x in {{1, None}}, f(a, x) == 0"
    started = time.perf_counter()
    (row,) = check_conjectures(slow_off_the_trial, [claim(text)])
    spent = time.perf_counter() - started
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "the sweep's time budget stopped the listed value x = None after" \
        in row.note, row.note
    assert "of its 200 points of a" in row.note, row.note
    assert spent < 200 * _SLOW_SECONDS + 5, spent


def test_a_grid_over_the_point_budget_says_so(monkeypatch):
    import mathema._brute_force as B
    monkeypatch.setattr(B, "BRUTE_FORCE_POINT_BUDGET", 10)
    members = ", ".join(str(i) for i in range(20))
    text = f"for a in {{{members}}}, x in {{1, None}}, f(a, x) == 0"
    (row,) = check_conjectures(zero_of_two, [claim(text)])
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "the 20 combinations of a are over the sweep's point budget" in row.note, \
        row.note
