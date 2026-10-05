# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A closed `oo]` includes the point (ruling E2, 2026-10-01): the
mathematics is over the reals, so `1/x > 0` on [1, oo] is proven over
[1, oo); the computation executes x = inf, where 1/inf is 0.0 and the
claim fails, so the computation line is falsified there and the claim's
headline with it."""
import mathema


def reciprocal(x: float) -> float:
    return 1 / x


def _rows(fn, law):
    return {p.name: p for p in mathema.check(fn, claims=[law]).probes}


def test_the_computation_runs_at_a_closed_infinite_end():
    rows = _rows(reciprocal, "for x in [1, oo], f(x) > 0")
    assert rows["f_x_gt_0"].verdict == "proven"
    float_row = rows["f_x_gt_0[float]"]
    assert float_row.verdict == "falsified", float_row.note
    assert float_row.counterexample.startswith("x = inf"), float_row.counterexample


def test_an_open_infinite_end_is_not_executed():
    rows = _rows(reciprocal, "for x in [1, oo), f(x) > 0")
    assert rows["f_x_gt_0[float]"].verdict == "holds", rows["f_x_gt_0[float]"].note
