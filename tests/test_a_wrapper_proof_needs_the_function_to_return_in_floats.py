# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim is proven through a wrapper that only catches when no
step of the wrapped function can raise in Python's float arithmetic over
the claim's domain. derive proves a value claim over real numbers, where
`math.exp(x * 1000)` is positive everywhere; in floats the call raises
OverflowError from x = 1, a wrapper catching it returns its constant,
and the claim is false there. A body of arithmetic that cannot fail, and
`math.exp` of an argument bounded well inside the float range, is still
proven."""
import functools
import math

import pytest

from mathema.conjecture import check_conjectures, claim




def _catching_arithmetic(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ArithmeticError:
            return 0
    return catching


def _catching_exception(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            return 0
    return catching


def _catching_overflow(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except OverflowError:
            return 0
    return catching


def _catching_zero_division(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ZeroDivisionError:
            return 0
    return catching


_WRAPPERS = [_catching_arithmetic, _catching_exception, _catching_overflow]


def exp_thousand(x):
    return math.exp(x * 1000)


def exp_hundred(x):
    return math.exp(x * 100)


def exp_five_hundred(x):
    return math.exp(x * 500)


def ten_to_the_thousand(x):
    return 10.0 ** (x * 1000)


def x_to_the_thousand(x):
    return x ** (x * 1000)


def exp_small(x):
    return math.exp(x)


def square_plus_one(x):
    return x * x + 1


def reciprocal_shifted(x):
    return 1 / (x - 1)


def half_is_refused(x):
    return x if x != 0.5 else 1 / 0


def _outcome(fn, x):
    try:
        return fn(x)
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__


def _holds(fn, x, relation):
    value = _outcome(fn, x)
    return not isinstance(value, str) and relation(value)


_FALSE = [
    (exp_thousand, "for x in [0, 3], f(x) > 0", 1.0, lambda v: v > 0),
    (exp_thousand, "for x in [0, 3], f(x) * 2 > f(x)", 1.0, lambda v: v * 2 > v),
    (exp_hundred, "for x in [0, 8], f(x) >= 1", 8.0, lambda v: v >= 1),
    (exp_five_hundred, "for x in [0, 3], f(x) > 0", 2.0, lambda v: v > 0),
    (ten_to_the_thousand, "for x in [1, 3], f(x) > 0", 1.0, lambda v: v > 0),
    (x_to_the_thousand, "for x in [1, 3], f(x) > 0", 2.0, lambda v: v > 0),
]


@pytest.mark.parametrize("wrap", _WRAPPERS, ids=lambda w: w.__name__)
@pytest.mark.parametrize("inner,text,point,relation", _FALSE,
                         ids=[f"{fn.__name__}: {text}" for fn, text, _, _ in _FALSE])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_an_overflow_the_wrapper_catches_is_not_proven_away(wrap, inner, text, point,
                                                            relation, route):
    fn = wrap(inner)
    assert _outcome(inner, point) == "OverflowError"
    assert _outcome(fn, point) == 0 and not relation(0)
    (row,) = check_conjectures(fn, [claim(text, route=route)])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("inner,text,point", [
    (exp_thousand, "for x in [0, 3], f(x) > 0", 1.0),
    (ten_to_the_thousand, "for x in [1, 3], f(x) > 0", 1.0),
], ids=["exp", "power"])
def test_an_overflow_the_wrapper_lets_through_is_not_proven_either(inner, text, point):
    fn = _catching_zero_division(inner)
    assert _outcome(fn, point) == "OverflowError"
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("wrap", _WRAPPERS, ids=lambda w: w.__name__)
@pytest.mark.parametrize("inner,text,relation", [
    (exp_small, "for x in [0, 3], f(x) >= 1", lambda v: v >= 1),
    (square_plus_one, "for x in [0, 3], f(x) >= 1", lambda v: v >= 1),
], ids=["exp of a small argument", "arithmetic that cannot fail"])
def test_a_body_that_cannot_raise_in_floats_is_proven(wrap, inner, text, relation):
    fn = wrap(inner)
    assert all(_holds(fn, x, relation) for x in (0.0, 0.5, 1.0, 2.0, 3.0))
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
    assert "no step of its body can raise in float arithmetic" in row.sketch, row.sketch


@pytest.mark.parametrize("inner,text,point,got", [
    (reciprocal_shifted, "for x in [-3, 3], f(x) * (x - 1) == 1", 1.0, 0),
    (half_is_refused, "for x in [-3, 3], f(x) == x", 0.5, 0),
], ids=["a pole inside the domain", "one refused point"])
def test_the_point_where_the_function_raises_is_run_on_the_wrapper(inner, text, point, got):
    fn = _catching_zero_division(inner)
    assert _outcome(inner, point) == "ZeroDivisionError" and _outcome(fn, point) == got
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict == "falsified", (row.verdict, row.sketch, row.note)


def test_a_point_where_the_wrappers_constant_satisfies_the_claim_is_no_counterexample():
    fn = _catching_zero_division(reciprocal)
    assert _outcome(fn, 0.0) == 0
    (row,) = check_conjectures(fn, [claim("for x in [-3, 3], f(x) * x * x == x",
                                          route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def reciprocal(x):
    return 1 / x
