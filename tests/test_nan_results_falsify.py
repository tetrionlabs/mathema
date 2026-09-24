# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A NaN returned at an in-domain, non-missing point is not a value the
claim's relation can hold for: an ordering over NaN is false, and NaN
equals no number. The probe route falsifies there with the NaN point
as its witness, and the corroboration kit reads the same point as a
genuine counterexample. A NaN that only propagates a missing INPUT
stays the missing-value axis's business."""
import math

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.gates import _point_evaluator


def nan_left(x: float) -> float:
    if x < 0:
        return float("nan")
    return x


def nan_everywhere(x: float) -> float:
    return float("nan")


def identity(x: float) -> float:
    return x


def test_an_ordering_over_a_nan_result_is_falsified_by_the_probe():
    (p,) = check_conjectures(
        nan_left, [claim("for x in [-1, 1], f(x) >= 0", route="probe")])
    assert p.verdict == "falsified"
    (x,) = p.meta["mathema.counterexample_args"]
    assert -1 <= x < 0
    assert math.isnan(nan_left(x))


def test_equality_to_a_number_is_falsified_by_a_nan_result():
    (p,) = check_conjectures(
        nan_everywhere, [claim("for x in [-1, 1], f(x) == 0", route="probe")])
    assert p.verdict == "falsified"
    (x,) = p.meta["mathema.counterexample_args"]
    assert -1 <= x <= 1


def test_the_corroboration_kit_reads_a_nan_result_as_a_counterexample():
    cj = claim("for x in [-1, 1], f(x) >= 0")
    kit = _point_evaluator(cj, nan_left, analyze_source(nan_left),
                           cj.domain, {})
    assert kit["evaluate"]({"x": -0.5}) is False
    assert kit["evaluate"]({"x": 0.5}) is True


def test_a_nan_that_propagates_a_missing_input_is_not_a_counterexample():
    cj = claim("for x in [-1, 1], f(x) >= 0")
    kit = _point_evaluator(cj, identity, analyze_source(identity),
                           cj.domain, {})
    assert kit["evaluate"]({"x": float("nan")}) is None
