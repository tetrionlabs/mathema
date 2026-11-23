# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Five raises that cannot fail on the way to their class are proven by
derive: a cause that is an exception class whose constructor takes no
argument; a chained comparison whose first link is false on the whole
domain, so the link after it never runs; an `ExceptionGroup` built from a
message and a list of exceptions built from read constructors; a
`functools.wraps` wrapper whose definition hands its arguments to the
wrapped function and returns its result; and a listed missing value on a
parameter the function never reads. Each has a near miss that is not
proven: an instance cause whose constructor refuses, a first link that is
true somewhere, a group member that is not an exception, a wrapper that
changes the arguments, and a listed missing value on a parameter the
raise reads."""
import builtins
import functools
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

_NEG = "for x in [-5, -1], "
_needs_groups = pytest.mark.skipif(not hasattr(builtins, "ExceptionGroup"),
                                   reason="Python 3.11 or later")


def cause_class(x: float) -> float:
    if x < 0:
        raise ValueError("n") from KeyError
    return x


def cause_refuses(x: float) -> float:
    if x < 0:
        raise ValueError("n") from UnicodeDecodeError
    return x


def chain_short_circuits(x: float) -> float:
    if x < 0:
        raise ValueError(0 < x < "a")
    return x


def chain_reaches_text(x: float) -> float:
    if x < 0:
        raise ValueError(-10 < x < "a")
    return x


def group(x: float) -> float:
    if x < 0:
        raise ExceptionGroup("g", [ValueError("a")])  # noqa: F821
    return x


def group_of_a_number(x: float) -> float:
    if x < 0:
        raise ExceptionGroup("g", [1])  # noqa: F821
    return x


def _pass_through(fn):
    @functools.wraps(fn)
    def handing_on(*args, **kwargs):
        return fn(*args, **kwargs)
    return handing_on


def _negating(fn):
    @functools.wraps(fn)
    def negated(x):
        return fn(-x)
    return negated


@_pass_through
def wrapped(x: float) -> float:
    if x < 0:
        raise ValueError("n")
    return x


@_negating
def wrapped_negated(x: float) -> float:
    if x < 0:
        raise ValueError("n")
    return x


def unused_second(x: float, y: Optional[float]) -> float:
    if x < 0:
        raise ValueError("n")
    return x


def used_second(x: float, y: Optional[float]) -> float:
    if x < 0:
        raise ValueError(y + 1)
    return x


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    return row


@pytest.mark.parametrize("fn,text", [
    (cause_class, _NEG + "raises(f(x), ValueError)"),
    (chain_short_circuits, _NEG + "raises(f(x), ValueError)"),
    pytest.param(group, _NEG + "raises(f(x), ExceptionGroup)", marks=_needs_groups),
    (wrapped, _NEG + "raises(f(x), ValueError)"),
    (unused_second, _NEG + "y in {1, None}, raises(f(x, y), ValueError)"),
], ids=["cause class", "short circuit", "group", "pass-through wrapper", "unused None"])
def test_a_raise_that_cannot_fail_on_the_way_is_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text", [
    (cause_refuses, _NEG + "raises(f(x), ValueError)"),
    (chain_reaches_text, _NEG + "raises(f(x), ValueError)"),
    pytest.param(group_of_a_number, _NEG + "raises(f(x), ExceptionGroup)",
                 marks=_needs_groups),
    (wrapped_negated, _NEG + "raises(f(x), ValueError)"),
    (used_second, _NEG + "y in {1, None}, raises(f(x, y), ValueError)"),
], ids=["cause refuses", "chain reaches text", "group of a number", "negating wrapper",
        "used None"])
def test_the_near_miss_is_not_proven(fn, text):
    if fn is wrapped_negated:
        assert fn(-2.0) == 2.0
    else:
        with pytest.raises(ValueError if fn is group_of_a_number else TypeError):
            fn(-2.0, None) if fn is used_second else fn(-2.0)
    row = _row(fn, text)
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)
