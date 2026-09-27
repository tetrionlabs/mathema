# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema.f.finite_no_error`, the helper `is_numerically_stable`
claims bind as `g`: 1 when the call returns a finite value, 0 when it
raises an arithmetic error or returns a non-finite value,
whether that value is a Python float, a numpy scalar, or an array. A
domain error (`ValueError`) propagates, and the probe route reads it as
a raise at that point."""
import math

import pytest

from mathema.f import finite_no_error


def _raise(exc):
    def fn(*_args):
        raise exc
    return fn


def test_a_finite_python_result_is_one():
    assert finite_no_error(lambda x: x + 1.0, 2.0) == 1
    assert finite_no_error(lambda x: [x, 2 * x], 2.0) == 1


def test_a_python_nan_or_inf_is_zero():
    assert finite_no_error(lambda x: float("nan"), 1.0) == 0
    assert finite_no_error(lambda x: [1.0, float("inf")], 1.0) == 0


@pytest.mark.parametrize("exc", [ZeroDivisionError, OverflowError,
                                 FloatingPointError])
def test_an_arithmetic_error_is_zero(exc):
    assert finite_no_error(_raise(exc("boom")), 1.0) == 0


def test_a_domain_error_propagates_as_a_raise():
    # the probe route reads the raise itself, which keeps its type and
    # the floating-point boundary diagnosis in the witness
    with pytest.raises(ValueError):
        finite_no_error(math.sqrt, -1.0)


def test_numpy_scalars_and_arrays_are_read_for_finiteness():
    np = pytest.importorskip("numpy")
    assert finite_no_error(lambda x: np.float32("nan"), 1.0) == 0
    assert finite_no_error(lambda x: np.float32(2.0), 1.0) == 1
    assert finite_no_error(lambda x: np.array([1.0, np.inf]), 1.0) == 0
    assert finite_no_error(lambda x: np.array([1.0, 2.0]), 1.0) == 1
    assert finite_no_error(lambda x: [np.float32(1.0), np.float16("inf")],
                           1.0) == 0
