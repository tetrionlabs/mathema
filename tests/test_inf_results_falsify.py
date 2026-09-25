# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An infinity returned for a finite input is "the computation did not
work": `math.exp(1000)` raises OverflowError and `numpy.exp(1000)`
returns inf with a warning, and both mean the function has no value
there. Like a NaN, such a result falsifies every relation at that
point, whichever sign the infinity has, with the executed point as the
witness. An overflow and a pole may read differently in the diagnosis,
never in the verdict."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def exp_np(x: float) -> float:
    return float(np.exp(x))


def log_np(x: float) -> float:
    return float(np.log(x))


def reciprocal_np(x: float) -> float:
    return float(np.divide(1.0, x))


def passes_inf_through(x: float) -> float:
    return x


def _probe(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="probe")])
    return p


def test_an_overflow_to_inf_falsifies_an_ordering_it_satisfies():
    p = _probe(exp_np, "for x in [700, 1000], f(x) >= 0")
    assert p.verdict == "falsified", p.note
    assert "f returned inf" in p.counterexample
    (x,) = p.meta["mathema.counterexample_args"]
    assert 700 <= x <= 1000
    assert math.isinf(exp_np(x))


def test_a_negative_infinity_at_a_pole_is_no_value():
    p = _probe(log_np, "for x in [0, 1], f(x) <= 0")
    assert p.verdict == "falsified", p.note
    assert "f returned -inf" in p.counterexample
    assert p.meta["mathema.counterexample_args"] == [0]


def test_a_division_by_zero_to_inf_is_no_value():
    p = _probe(reciprocal_np, "for x in [-1, 1], f(x) >= -1e9")
    assert p.verdict == "falsified", p.note
    assert "returned inf" in p.counterexample
    assert p.meta["mathema.counterexample_args"] == [0]


def test_inequality_to_a_number_is_falsified_by_an_inf_result():
    p = _probe(exp_np, "for x in [710, 800], f(x) != 5")
    assert p.verdict == "falsified", p.note


def test_an_inf_that_only_passes_an_infinite_input_through_is_a_value():
    p = _probe(passes_inf_through, "for x in R, f(x) == x")
    assert p.verdict == "holds", p.note
