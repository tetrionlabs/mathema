# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The point evaluator reads an executed value per P4, whatever shape
the value has: a NaN computed from non-missing inputs is no value and
fails every relation, `==` and `!=` included, also inside an array; two
sides at the same infinity agree, and the exact recheck at derive's
witness reads them the same way."""
import math

import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import claim
from mathema.gates import _exact_witness_violation, _point_evaluator
from mathema.symbolic import ProofResult

np = pytest.importorskip("numpy")


def with_hole(x: float):
    return np.array([x, x - x + math.nan, 2.0 * x])


def scalar_hole(x: float) -> float:
    return x - x + math.nan


def overflowing(x: float) -> float:
    return x * 1e300 * 1e300


def _evaluate(fn, law, point):
    cj = claim(law)
    deps = _point_evaluator(cj, fn, analyze_source(fn), cj.domain, {})
    return deps["evaluate"](point)


@pytest.mark.parametrize("law", ["f(x) == f(x)", "f(x) != f(x)",
                                 "f(x) == x"])
def test_a_nan_in_an_array_from_values_is_no_value(law):
    assert _evaluate(with_hole, law, {"x": 1.5}) is False


@pytest.mark.parametrize("law", ["f(x) == f(x)", "f(x) != f(x)",
                                 "f(x) <= 1"])
def test_a_nan_from_values_is_no_value(law):
    assert _evaluate(scalar_hole, law, {"x": 1.5}) is False


def test_the_same_infinity_agrees_and_the_opposite_one_does_not():
    assert _evaluate(overflowing, "f(x) == f(x)", {"x": 2.0}) is True
    assert _evaluate(overflowing, "f(x) == f(-x)", {"x": 2.0}) is False


def test_the_exact_recheck_reads_the_same_infinity_as_agreement():
    facts = analyze_source(overflowing)
    proof = ProofResult("disproven", sketch="", witness={"x": 2.0})
    same = claim("for x in [1, 3], f(x) == f(x)")
    point, compared = _exact_witness_violation(
        same, overflowing, facts, same.domain, {}, (), proof, set())
    assert compared and point is None
    opposite = claim("for x in [1, 3], f(x) == f(-x)")
    point, compared = _exact_witness_violation(
        opposite, overflowing, facts, opposite.domain, {}, (), proof, set())
    assert compared and point == {"x": 2.0}
