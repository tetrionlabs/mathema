# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Within one exact reading, a call of a function the examination shows
pure is taken once per argument: a repeated call returns the value the
first one gave, its decisions checked against the computation's at the
place reached. A doubly recursive body then costs one call per distinct
argument, not one per path. A function that is not shown pure runs every
time it is called."""
import time
from fractions import Fraction

from mathema._exact_body import exact_callee, memo_key, shown_pure

CALLS = []


def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def counted(n):
    CALLS.append(n)
    if n <= 1:
        return n
    return counted(n - 1) + counted(n - 2)


def test_a_pure_double_recursion_is_read_once_per_argument():
    assert shown_pure(fib)
    started = time.monotonic()
    assert exact_callee(fib)(30) == 832040
    assert exact_callee(fib)(Fraction(61, 2)) == fib(30.5)
    assert time.monotonic() - started < 3


def test_a_function_not_shown_pure_runs_every_call():
    assert not shown_pure(counted)
    CALLS.clear()
    assert exact_callee(counted)(12) == 144
    # the computation's run and the exact reading's each make every call
    assert len(CALLS) == 2 * 465


def test_a_memo_key_tells_apart_what_a_call_tells_apart():
    assert memo_key(0.0) != memo_key(-0.0)
    assert memo_key(1) != memo_key(1.0) != memo_key(True)
    assert memo_key(Fraction(1, 3)) == memo_key(Fraction(2, 6))
    assert memo_key([1, 2]) is None
    assert memo_key((1, Fraction(1, 2))) is not None
