# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a call at a hole did is read by calling f again with the hole
filled by a value of its domain: a raise raises; a hole in the output
that stays when the input's hole is filled was introduced; a hole that
goes with it propagates, however far it spread; a value the fill leaves
the same was never read; a value the fill changes dropped the hole. A
container holding two members is filled one member at a time."""
import math

import pytest

from mathema._missing_policy import NOT_READ, refill

NAN = math.nan
UNIT = {"x": (0.0, 1.0), "y": (0.0, 1.0), "xs": (0.0, 1.0), "A": (0.0, 1.0)}


def _calls(fn):
    def call_at(point):
        try:
            return fn(**point), None
        except Exception as exc:
            return None, type(exc).__name__
    return call_at


def _behaviours(fn, **point):
    try:
        output, raised = fn(**point), None
    except Exception as exc:
        output, raised = None, type(exc).__name__
    return [b for _p, _o, _r, b in refill(_calls(fn), point, output, raised, UNIT)]


def clamp01(x):
    return max(0.0, min(1.0, x))


def root(x):
    return math.sqrt(x) if x == x else NAN


def second(x, y):
    return y


def strict(x):
    if x != x:
        raise ValueError("x is nan")
    return x


def zero_over_zero(xs):
    import numpy as np
    return float(np.float64(0.0) / np.float64(0.0)) + 0.0 * len(xs)


def test_a_raise_raises():
    assert _behaviours(strict, x=NAN) == ["raises"]


def test_a_hole_that_stays_after_the_fill_was_introduced():
    assert _behaviours(zero_over_zero, xs=[NAN, 0.5]) == ["introduces"]


def test_a_hole_that_goes_with_the_fill_propagates():
    assert _behaviours(root, x=NAN) == ["propagates"]


def test_a_value_the_fill_leaves_the_same_was_not_read():
    assert _behaviours(second, x=NAN, y=0.5) == [NOT_READ]


def test_a_value_the_fill_changes_dropped_the_hole():
    assert _behaviours(clamp01, x=NAN) == ["drops"]


def test_a_spread_is_propagation():
    np = pytest.importorskip("numpy")

    def running_total(xs):
        return np.cumsum(np.array(xs, dtype=float)).tolist()

    def gram(A):
        a = np.array(A, dtype=float)
        return (a.T @ a).tolist()

    def trace_of(A):
        return float(np.trace(np.array(A, dtype=float)))
    assert _behaviours(running_total, xs=[1.0, NAN, 0.5]) == ["propagates"]
    assert _behaviours(gram, A=[[NAN, 0.5], [0.25, 1.0]]) == ["propagates"]
    assert _behaviours(trace_of, A=[[NAN, 0.5], [0.25, 1.0]]) == ["propagates"]


def test_a_hole_off_the_diagonal_is_not_read_by_a_trace():
    np = pytest.importorskip("numpy")

    def trace_of(A):
        return float(np.trace(np.array(A, dtype=float)))
    assert _behaviours(trace_of, A=[[0.5, NAN], [0.25, 1.0]]) == [NOT_READ]


def test_an_entry_never_indexed_is_not_read():
    def coupling(A):
        return A[0][1]
    assert _behaviours(coupling, A=[[NAN, 0.5], [0.25, 1.0]]) == [NOT_READ]
    assert _behaviours(coupling, A=[[0.5, NAN], [0.25, 1.0]]) == ["propagates"]


def test_a_function_reading_every_slot_is_classified_as_before():
    np = pytest.importorskip("numpy")

    def mean(xs):
        return float(np.mean(np.array(xs, dtype=float)))

    def nansum(xs):
        return float(np.nansum(np.array(xs, dtype=float)))
    assert _behaviours(mean, xs=[NAN, 0.5]) == ["propagates"]
    assert _behaviours(nansum, xs=[NAN, 0.5]) == ["drops"]


def test_two_members_are_filled_one_at_a_time():
    pl = pytest.importorskip("polars")

    def mean_pl(xs):
        return pl.Series(xs, dtype=pl.Float64, nan_to_null=False).mean()
    point = {"xs": [None, NAN, 0.5]}
    out = refill(_calls(mean_pl), point, mean_pl(**point), None, UNIT)
    # the member each call still holds, and what f did with it
    assert {("null" if None in p["xs"] else "nan"): b
            for p, _o, _r, b in out} == {"null": "drops", "nan": "propagates"}


def test_an_absence_is_not_refilled():
    assert refill(_calls(root), {"x": None}, None, "TypeError", UNIT) is None

