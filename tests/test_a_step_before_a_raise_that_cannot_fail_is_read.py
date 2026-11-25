# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Three things on the way to a `raise` are read where they cannot fail,
and not where they can. A float division, floor division or remainder by
a float literal that is not zero never raises, and a divisor that stays
away from zero (`y - 7` with `|y| <= 5`, `x - 0.0` with `x <= -1`) is not
zero. A builtin exception built with a keyword its constructor refuses
raises TypeError. The wrapper `functools.singledispatch` builds, with
nothing registered, calls the function it wraps. Each true claim has a
false one beside it, shown false by a call."""
import builtins
import functools

import pytest

from mathema._raise_reading import KEYWORD_REFUSING
from mathema.conjecture import check_conjectures, claim

_NEG = "for x in [-5, -1], "
_POINTS = (-5.0, -3.3, -1.0, -5, -1)


def remainder_then_divide(x: float) -> float:
    if x < 0:
        y = x % -1.5
        z = 1 / (y - 7)
        raise ValueError(z)
    return x


def remainder_then_divide_by_what_may_be_zero(x: float) -> float:
    if x < 0:
        y = x % -1.5
        z = 1 / (y + 1)
        raise ValueError(z)
    return x


def floor_by_a_half(x: float) -> float:
    if x < 0:
        y = x // 0.5
        raise ValueError(y)
    return x


def floor_by_zero(x: float) -> float:
    if x < 0:
        y = x // 0.0
        raise ValueError(y)
    return x


def divide_by_itself_less_zero(x: float) -> float:
    if x < 0:
        y = 1 / (x - 0.0)
        raise ValueError(y)
    return x


def divide_by_itself_plus_one(x: float) -> float:
    if x < 0:
        y = 1 / (x + 1.0)
        raise ValueError(y)
    return x


def keyword_refused(x: float) -> float:
    if x < 0:
        raise ValueError(msg="n")
    return x


def keyword_accepted(x: float) -> float:
    if x < 0:
        raise ImportError(name="n")
    return x


class _TakesAKeyword(ValueError):
    def __init__(self, msg=""):
        super().__init__(msg)


def keyword_of_its_own(x: float) -> float:
    if x < 0:
        raise _TakesAKeyword(msg="n")
    return x


@functools.singledispatch
def dispatched(x: float) -> float:
    if x < 0:
        raise TypeError("n")
    return x


@functools.singledispatch
def dispatched_with_a_float(x: float) -> float:
    if x < 0:
        raise TypeError("n")
    return x


@dispatched_with_a_float.register
def _(x: float) -> float:
    return x


def _raised(fn, x):
    try:
        fn(x)
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__
    return None


def _row(fn, exception, route):
    (row,) = check_conjectures(fn, [claim(_NEG + f"raises(f(x), {exception})", route=route)])
    return row


@pytest.mark.parametrize("fn,exception", [
    (remainder_then_divide, "ValueError"),
    (floor_by_a_half, "ValueError"),
    (divide_by_itself_less_zero, "ValueError"),
    (keyword_refused, "TypeError"),
    (dispatched, "TypeError"),
], ids=["remainder then a divisor away from zero", "floor division by a half",
        "a divisor at most -1", "a keyword the constructor refuses",
        "singledispatch with nothing registered"])
def test_a_step_that_cannot_fail_is_read(fn, exception):
    assert {_raised(fn, x) for x in _POINTS} == {exception}
    row = _row(fn, exception, "derive")
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,exception,at,raised", [
    (remainder_then_divide_by_what_may_be_zero, "ValueError", -1.0, "ZeroDivisionError"),
    (floor_by_zero, "ValueError", -2.0, "ZeroDivisionError"),
    (divide_by_itself_plus_one, "ValueError", -1.0, "ZeroDivisionError"),
    (keyword_refused, "ValueError", -2.0, "TypeError"),
    (keyword_accepted, "TypeError", -2.0, "ImportError"),
    (keyword_of_its_own, "TypeError", -2.0, "_TakesAKeyword"),
    (dispatched_with_a_float, "TypeError", -2.0, None),
], ids=["a divisor that reaches zero", "floor division by zero", "a divisor zero at -1",
        "the class written, where the constructor refuses", "a keyword the constructor takes",
        "a constructor of its own", "singledispatch with a float registered"])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_step_that_can_fail_is_not_read(fn, exception, at, raised, route):
    assert _raised(fn, at) == raised
    row = _row(fn, exception, route)
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def test_singledispatch_is_not_read_for_a_call_with_no_positional_argument():
    with pytest.raises(TypeError, match="requires at least 1 positional argument"):
        dispatched(x=-2.0)
    (row,) = check_conjectures(
        dispatched, [claim(_NEG + "raises(f(x=x), KeyError)", route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("name", sorted(KEYWORD_REFUSING))
def test_each_class_read_to_refuse_a_keyword_does(name):
    with pytest.raises(TypeError, match="keyword"):
        getattr(builtins, name)(msg="n")
