# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Raise-reading cases: missing-value policies read from a guard."""
import functools
import math
from math import isinf as isnan
from typing import Optional

VALUE = "for x in [0, 1], y in [-1, 1], f(x, y) == x * y"


def p(fn, text):
    return (fn, [VALUE, text])


def pol_lam(x: Optional[float], y: float) -> float:
    g = lambda a=1 / (y - 0.123456): a  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_lam_inner(x: Optional[float], y: float) -> float:
    if x is None:
        g = lambda a=1 / (y - 0.123456): a  # noqa: E731,F841
        raise TypeError("x is required")
    return x * y


def pol_alias_isnan(x: float, y: float) -> float:
    if isnan(x):
        raise ValueError("x is nan")
    return x * y


def pol_alias_isnan_gate(x: float, y: float) -> float:
    if isnan(x):
        raise ValueError("x is nan")
    return x * y


def pol_gen(x: Optional[float], y: float):
    if x is None:
        raise TypeError("x is required")
    yield x * y


def swallow(fn):
    @functools.wraps(fn)
    def swallowing(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeError:
            return 0.0
    return swallowing


@swallow
def pol_wrapped(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_second(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        raise KeyError("rare")
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_second_sub(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def pol_not(x: Optional[float], y: float) -> float:
    if not (x is not None):
        raise TypeError("x is required")
    return x * y


def pol_eq_none(x: Optional[float], y: float) -> float:
    if x == None:  # noqa: E711
        raise TypeError("x is required")
    return x * y


def pol_nan_ne(x: float, y: float) -> float:
    if x != x:
        raise ValueError("nan")
    return x * y


def pol_nan_or(x: float, y: float) -> float:
    if y > 0.5 or x != x:
        raise ValueError("nan")
    return x * y


def pol_absent_or_isnan(x: Optional[float], y: float) -> float:
    if x is None or math.isnan(x):
        raise ValueError("missing")
    return x * y


def pol_nested_raise(x: Optional[float], y: float) -> float:
    if x is None:
        if y == 0.123456:
            return 0.0
        raise TypeError("x is required")
    return x * y


def pol_try(x: Optional[float], y: float) -> float:
    try:
        if x is None:
            raise TypeError("x is required")
    except TypeError:
        return 0.0
    return x * y


def pol_after_return(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        return 0.0
    if x is None:
        raise TypeError("x is required")
    return x * y


class Holder:
    pass


def pol_ctor_meta(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError(Holder)
    return x * y


CASES = [
    p(pol_lam, "absent(f, x) raises(TypeError)"),
    p(pol_lam_inner, "absent(f, x) raises(TypeError)"),
    p(pol_alias_isnan, "missing(f, x) raises(ValueError)"),
    p(pol_alias_isnan, "missing(f, x) raises"),
    p(pol_gen, "absent(f, x) raises(TypeError)"),
    p(pol_wrapped, "absent(f, x) raises(TypeError)"),
    p(pol_wrapped, "absent(f, x) raises"),
    p(pol_second, "absent(f, x) raises(TypeError)"),
    p(pol_second_sub, "absent(f, x) raises(ArithmeticError)"),
    p(pol_not, "absent(f, x) raises(TypeError)"),
    p(pol_eq_none, "absent(f, x) raises(TypeError)"),
    p(pol_nan_ne, "missing(f, x) raises(ValueError)"),
    p(pol_nan_or, "missing(f, x) raises(ValueError)"),
    p(pol_absent_or_isnan, "missing(f, x) raises(ValueError)"),
    p(pol_absent_or_isnan, "absent(f, x) raises(ValueError)"),
    p(pol_nested_raise, "absent(f, x) raises(TypeError)"),
    p(pol_try, "absent(f, x) raises(TypeError)"),
    p(pol_after_return, "absent(f, x) raises(TypeError)"),
    p(pol_ctor_meta, "absent(f, x) raises(TypeError)"),
]
