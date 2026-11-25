# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A wrapper whose whole body is `try: return fn(*args, **kwargs)` with
`except` clauses that each return a constant returns the wrapped
function's own value wherever that function returns. A value claim on
the wrapper is proven when derive proves two things about the function
it wraps, over the claim's whole domain: the same claim, and that the
function returns there. Where the function raises on part of the domain,
or the wrapper changes the arguments or the result, or an `except`
clause returns something other than a constant, the claim is not
proven."""
import functools

import pytest

from mathema.conjecture import check_conjectures, claim

_CLAIM = "for x in [0, 1], y in [-1, 1], f(x, y) == x * y"
_POINTS = [(0.0, -1.0), (0.5, 0.25), (1.0, 1.0), (1, -1), (0.25, 0.75)]


def _catches(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeError:
            return 0.0
    return catching


def _catches_two(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        """Hands the call on."""
        try:
            return fn(*args, **kwargs)
        except (TypeError, KeyError) as error:  # noqa: F841
            return 0.0
        except ValueError:
            return None
    return catching


def _negates(fn):
    @functools.wraps(fn)
    def negating(*args, **kwargs):
        try:
            return -fn(*args, **kwargs)
        except TypeError:
            return 0.0
    return negating


def _swaps(fn):
    @functools.wraps(fn)
    def swapping(*args, **kwargs):
        try:
            return fn(*args[::-1], **kwargs)
        except TypeError:
            return 0.0
    return swapping


def _returns_an_argument(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeError:
            return args[0]
    return catching


def _finally_returns(fn):
    @functools.wraps(fn)
    def catching(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeError:
            return 0.0
        finally:
            return 0.0  # noqa: B012
    return catching


def product(x: float, y: float) -> float:
    return x * y


def product_minus_y(x: float, y: float) -> float:
    return x * y - y


def raises_type_error_high(x: float, y: float) -> float:
    if y > 0.5:
        raise TypeError("high")
    return x * y


def raises_key_error_high(x: float, y: float) -> float:
    if y > 0.5:
        raise KeyError("high")
    return x * y


def _outcome(fn, x, y):
    try:
        return fn(x, y)
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__


def _row(fn, route="derive"):
    (row,) = check_conjectures(fn, [claim(_CLAIM, route=route)])
    return row


@pytest.mark.parametrize("fn", [_catches(product), _catches_two(product)],
                         ids=["one except clause", "three exceptions and a docstring"])
def test_the_claim_is_proven_through_a_wrapper_that_only_catches(fn):
    assert all(_outcome(fn, x, y) == x * y for x, y in _POINTS)
    row = _row(fn)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
    said = f"{row.sketch} {row.note}"
    assert "the same claim" in said and "returns on the whole domain" in said, said


@pytest.mark.parametrize("fn,point,got", [
    (_catches(raises_type_error_high), (1.0, 1.0), 0.0),
    (_catches(raises_key_error_high), (1.0, 1.0), "KeyError"),
    (_negates(product), (1.0, 1.0), -1.0),
    (_swaps(product_minus_y), (1.0, 0.5), -0.5),
    (_returns_an_argument(raises_type_error_high), (0.5, 0.75), 0.5),
    (_finally_returns(product), (1.0, 1.0), 0.0),
], ids=["the function raises what is caught", "the function raises something else",
        "the result is negated", "the arguments are swapped",
        "an except clause returns an argument", "a finally clause returns"])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_false_claim_through_a_wrapper_is_not_proven(fn, point, got, route):
    x, y = point
    assert _outcome(fn, x, y) == got and got != x * y
    row = _row(fn, route)
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def test_a_raises_claim_is_not_read_through_a_wrapper_that_catches():
    fn = _catches(raises_type_error_high)
    assert _outcome(fn, 1.0, 1.0) == 0.0
    (row,) = check_conjectures(fn, [claim(
        "for x in [0, 1], y in [0.75, 1], raises(f(x, y), TypeError)", route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def _returns_zero_on(caught):
    def wrapping(fn):
        @functools.wraps(fn)
        def catching(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except caught:
                return 0
        return catching
    return wrapping


def one_of(x):
    return x * 0 + 1


def one_unless_missing(x):
    if x is None:
        return 1 / 0
    return 1


def plus_one(x, y):
    return x + y


def plus_one_of_second(x, y):
    return x * 0 + y * 0 + 1


_MISSING_LISTED = [
    (_returns_zero_on(Exception)(one_of), "for x in {1.0, None}, f(x) > 0"),
    (_returns_zero_on(BaseException)(one_of), "for x in {1.0, None}, f(x) > 0"),
    (_returns_zero_on((TypeError, KeyError))(one_of), "for x in {1.0, None}, f(x) > 0"),
    (_returns_zero_on(ArithmeticError)(one_unless_missing), "for x in {1.0, None}, f(x) > 0"),
    (_returns_zero_on(Exception)(one_unless_missing), "for x in {1.0, None}, f(x) == 1"),
    (_returns_zero_on(Exception)(one_of), "for x in {1.0, 2.0, None}, f(x) > 0"),
    (_returns_zero_on(Exception)(one_of), "for x in {1.0, absent}, f(x) > 0"),
    (_returns_zero_on(Exception)(one_of), "for x in {1.0}|absent, f(x) > 0"),
    (_returns_zero_on(Exception)(one_of), "for x in {1.0, 2.0}|absent, f(x) > 0"),
    (_returns_zero_on(Exception)(plus_one), "for x in {1.0, None}, for y in [1, 2], f(x, y) > 0"),
    (_returns_zero_on(Exception)(plus_one_of_second),
     "for x in [1, 3], y in {2.0, None}, f(x, y) > 0"),
]


@pytest.mark.parametrize("fn,text", _MISSING_LISTED, ids=[t for _, t in _MISSING_LISTED])
def test_a_listed_missing_value_is_run_on_the_wrapper_itself(fn, text):
    # the wrapper returns the except clause's 0 at the listed missing value
    assert fn(*([None] if fn.__wrapped__.__code__.co_argcount == 1 else [1, None])) == 0
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict == "falsified", (row.verdict, row.sketch, row.note)
