# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One reading of two executed values, whatever form they arrive in.

A Python float, a numpy scalar, a 0-d array, a one-element list and a
one-element array holding the same numbers compare alike under `==`,
`~=` and `!=`: a NaN agrees with nothing and fails every relation,
another NaN and `!=` included; two sides at the same infinity agree;
complex values compare by `abs(a - b)`; a numpy scalar of a narrower
type (float32) gets the same tolerance a float does, never exact
equality. The corroboration kit reads an array-valued result
elementwise with the same rules.
"""
import math

import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.gates import _point_evaluator
from mathema.probing import _close, relation_holds_elementwise

np = pytest.importorskip("numpy")

_NAN, _INF = float("nan"), float("inf")
_PAIRS = [(1.0, 1.0), (1.0, 1.0 + 1e-12), (1.0, 2.0), (0.0, -0.0),
          (_NAN, _NAN), (_NAN, 1.0), (_INF, _INF), (-_INF, -_INF),
          (_INF, -_INF), (_INF, 1e308), (1 + 2j, 1 + 2j),
          (1 + 2j, 1 + 2.5j), (complex(_NAN, 0), complex(_NAN, 0))]


def _forms(x):
    return [x, np.asarray(x), [x], np.array([x]), [[x]]] + (
        [np.float64(x)] if isinstance(x, float) else [np.complex128(x)])


@pytest.mark.parametrize("relation", ["==", "~=", "!="])
@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("a,b", _PAIRS)
def test_every_form_of_the_same_numbers_compares_alike(a, b, relation,
                                                       exact):
    expected = relation_holds_elementwise(a, b, relation, 1e-9,
                                          exact_inequality=exact)
    for fa, fb in zip(_forms(a), _forms(b)):
        got = relation_holds_elementwise(fa, fb, relation, 1e-9,
                                         exact_inequality=exact)
        assert got == expected, (a, b, relation, type(fa), got, expected)


@pytest.mark.parametrize("relation", ["==", "~=", "!=", "<=", ">=", "<", ">"])
def test_a_nan_fails_every_relation(relation):
    for a, b in ((_NAN, _NAN), (_NAN, 1.0), (1.0, _NAN),
                 ([1.0, _NAN], [1.0, _NAN]), (np.array([_NAN]), 0.0)):
        assert relation_holds_elementwise(a, b, relation, 1e-9) is False, \
            (a, b, relation)
        assert relation_holds_elementwise(
            a, b, relation, 1e-9, exact_inequality=True) is False, \
            (a, b, relation)


def test_close_reads_nan_as_no_value_and_the_same_infinity_as_one_point():
    assert _close(_NAN, _NAN) is False
    assert _close(np.float64(_NAN), _NAN) is False
    assert _close(_INF, _INF) is True
    assert _close(-_INF, _INF) is False
    assert _close([1.0, _INF], (1.0, _INF)) is True
    assert _close([1.0, 2.0], [1.0]) is False


def test_a_float32_compares_with_the_tolerance_a_float_gets():
    assert float(np.float32(0.1)) != 0.1
    assert _close(np.float32(0.1), 0.1) is True
    assert _close(np.int64(3), 3) is True
    assert _close(np.asarray(0.1, dtype=np.float32), 0.1) is True
    assert relation_holds_elementwise(np.float32(0.1), 0.1, "==", 1e-9)


def tenth32(x: float) -> float:
    return np.float32(x) / np.float32(10)


def pair(x: float):
    return np.array([x, 2 * x])


def test_a_float32_result_holds_on_the_probe():
    (p,) = check_conjectures(
        tenth32, [claim("for x in [-1, 1], f(x) == x / 10", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_the_corroboration_kit_compares_a_float32_result_with_tolerance():
    cj = claim("for x in [-1, 1], f(x) == x / 10")
    kit = _point_evaluator(cj, tenth32, analyze_source(tenth32),
                           cj.domain, {})
    assert float(tenth32(0.5)) != 0.05
    assert kit["evaluate"]({"x": 0.5}) is True
    assert kit["probe_finite"]({"x": 0.5}) is None


def test_the_corroboration_kit_compares_array_results_elementwise():
    cj = claim("for x in [-1, 1], f(x) == f(x)")
    kit = _point_evaluator(cj, pair, analyze_source(pair), cj.domain, {})
    assert kit["evaluate"]({"x": 0.5}) is True
    assert kit["probe_finite"]({"x": 0.5}) is None
    cj = claim("for x in [-1, 1], f(x) != f(x)")
    kit = _point_evaluator(cj, pair, analyze_source(pair), cj.domain, {})
    assert kit["evaluate"]({"x": 0.5}) is False
    cj = claim("for x in [-1, 1], f(x) == f(-x)")
    kit = _point_evaluator(cj, pair, analyze_source(pair), cj.domain, {})
    assert kit["evaluate"]({"x": 0.5}) is False
    assert kit["evaluate"]({"x": 0.0}) is True
    assert kit["probe_finite"]({"x": 0.5}) is not None


def nan_pair(x: float):
    return np.array([x, math.nan])


def test_an_array_result_holding_a_nan_is_no_value_to_the_kit():
    cj = claim("for x in [-1, 1], f(x) == f(x)")
    kit = _point_evaluator(cj, nan_pair, analyze_source(nan_pair),
                           cj.domain, {})
    assert kit["evaluate"]({"x": 0.5}) is False
    assert "NaN" in (kit["probe_finite"]({"x": 0.5}) or "")
