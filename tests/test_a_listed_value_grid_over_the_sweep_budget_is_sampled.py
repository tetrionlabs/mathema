# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Beside finite sets whose combinations would take longer to run than
the brute-force sweep's time budget, the listed missing value is run at
sampled combinations: the claim holds, and the note says how many
combinations there were and how many points were run."""
import pytest

from mathema.conjecture import check_conjectures, claim


def zero_of_four(a, b, c, x):
    if x is None:
        return 0.0 * a
    return 0.0


def test_a_grid_over_the_time_budget_is_sampled_and_holds(monkeypatch):
    import mathema._brute_force as B
    monkeypatch.setattr(B, "_SWEEP_SECONDS", 1e-9)
    text = ("for a in {0, 1, 2, 3}, b in {0, 1, 2}, c in {0, 1}, x in {1, None}, "
            "f(a, b, c, x) == 0")
    (row,) = check_conjectures(zero_of_four, [claim(text)])
    assert row.verdict == "holds", (row.verdict, row.route, row.note)
    assert "the 24 combinations of a, b, c are over the sweep's time budget" in row.note, \
        row.note


@pytest.mark.needs_full_proof_budget
def test_a_small_grid_is_still_run_whole_and_proven():
    text = ("for a in {0, 1, 2, 3}, b in {0, 1, 2}, c in {0, 1}, x in {1, None}, "
            "f(a, b, c, x) == 0")
    (row,) = check_conjectures(zero_of_four, [claim(text)])
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
