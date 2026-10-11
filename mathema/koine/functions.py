# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE's operators and functions as Python callables.

`IMPLEMENTATIONS` maps every operator and function path to the callable
that computes it over Python numbers: exact integers stay exact, reals
are binary64. The quotient families are computed from the exact
quotient (a `Fraction`) and rounded once, so `division::floor(1.0,
0.1)` is 9.0, the floor of the true quotient of the two binary64
values, not 10.0, the floor of their rounded quotient.

A callable raises `ZeroDivisionError` at a singular point, `ValueError`
outside its real domain and `OverflowError` past binary64; the
interpreter reads those as the three non-value classes. The callables
that have no exact spelling in Python (`div_trunc`, `round_ties_up`,
...) carry their path as `__koine__`, which is how a function built
from them is read back into KOINE.
"""
from __future__ import annotations

import math
import operator
from fractions import Fraction


def koine(path: str):
    """Mark a callable as the Python realisation of `path`."""
    def mark(fn):
        fn.__koine__ = path
        return fn
    return mark


def _ints(a, b) -> bool:
    return isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool) \
        and not isinstance(b, bool)


def _quotient(a, b) -> Fraction:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return Fraction(a) / Fraction(b)


def _real(q: Fraction, like_int: bool):
    return int(q) if like_int else float(q)


@koine("operator::binary::division::truncation")
def div_trunc(a, b):
    """The quotient rounded toward zero."""
    return _real(Fraction(math.trunc(_quotient(a, b))), _ints(a, b))


@koine("operator::binary::division::floor")
def div_floor(a, b):
    """The quotient rounded toward minus infinity."""
    return _real(Fraction(math.floor(_quotient(a, b))), _ints(a, b))


@koine("operator::binary::division::euclidean")
def div_euclid(a, b):
    """The quotient that leaves a remainder in [0, |b|)."""
    q = _quotient(a, abs(b))
    whole = math.floor(q)
    return _real(Fraction(whole if b > 0 else -whole), _ints(a, b))


@koine("operator::binary::remainder::truncation")
def rem_trunc(a, b):
    """a - b * div_trunc(a, b): the sign of the dividend."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return _real(Fraction(a) - Fraction(b) * math.trunc(_quotient(a, b)), _ints(a, b))


@koine("operator::binary::remainder::floor")
def rem_floor(a, b):
    """a - b * div_floor(a, b): the sign of the divisor."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return _real(Fraction(a) - Fraction(b) * math.floor(_quotient(a, b)), _ints(a, b))


@koine("operator::binary::remainder::euclidean")
def rem_euclid(a, b):
    """a - |b| * floor(a / |b|): never negative."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return _real(Fraction(a) - abs(Fraction(b)) * math.floor(_quotient(a, abs(b))),
                 _ints(a, b))


def div_real(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


def power(a, b):
    if a == 0 and b < 0:
        raise ZeroDivisionError("zero to a negative power")
    if not isinstance(a, complex) and not isinstance(b, complex) \
            and a < 0 and not float(b).is_integer():
        raise ValueError("a negative base to a non-integer power")
    return a ** b


@koine("function::rounding::ties_up")
def round_ties_up(x):
    """The nearest integer, ties toward plus infinity."""
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


@koine("function::rounding::ties_away")
def round_ties_away(x):
    """The nearest integer, ties away from zero."""
    r = round_ties_up(abs(x))
    return r if x >= 0 else -r


@koine("function::magnitude::sign")
def sign(x):
    return (x > 0) - (x < 0)


@koine("function::root::cube")
def cbrt(x):
    """The real cube root."""
    if hasattr(math, "cbrt"):
        return math.cbrt(x)
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


@koine("function::order::clamp")
def clip(x, lo, hi):
    return min(max(x, lo), hi)


@koine("function::complex::real_part")
def re(z):
    return complex(z).real


@koine("function::complex::imaginary_part")
def im(z):
    return complex(z).imag


@koine("function::complex::conjugate")
def conjugate(z):
    return complex(z).conjugate()


@koine("function::complex::argument")
def arg(z):
    return math.atan2(complex(z).imag, complex(z).real)


def _factorial(x):
    if isinstance(x, float):
        if not x.is_integer():
            raise ValueError("factorial of a non-integer")
        x = int(x)
    return math.factorial(x)


def _gamma(x):
    if x <= 0 and float(x).is_integer():
        raise ValueError("gamma at a non-positive integer")
    return math.gamma(x)


def _log_gamma(x):
    if x <= 0 and float(x).is_integer():
        raise ValueError("log gamma at a non-positive integer")
    return math.lgamma(x)


def _log1p(x):
    if x <= -1:
        raise ValueError("log1p at or below -1")
    return math.log1p(x)


IMPLEMENTATIONS = {
    "operator::unary::negation": operator.neg,
    "operator::unary::identity": operator.pos,
    "operator::binary::addition": operator.add,
    "operator::binary::subtraction": operator.sub,
    "operator::binary::multiplication": operator.mul,
    "operator::binary::power": power,
    "operator::binary::division::real": div_real,
    "operator::binary::division::truncation": div_trunc,
    "operator::binary::division::floor": div_floor,
    "operator::binary::division::euclidean": div_euclid,
    "operator::binary::remainder::truncation": rem_trunc,
    "operator::binary::remainder::floor": rem_floor,
    "operator::binary::remainder::euclidean": rem_euclid,
    "function::root::square": math.sqrt,
    "function::root::cube": cbrt,
    "function::exponential::natural": math.exp,
    "function::exponential::natural_minus_one": math.expm1,
    "function::logarithm::natural": math.log,
    "function::logarithm::binary": math.log2,
    "function::logarithm::decimal": math.log10,
    "function::logarithm::natural_one_plus": _log1p,
    "function::trigonometric::sine": math.sin,
    "function::trigonometric::cosine": math.cos,
    "function::trigonometric::tangent": math.tan,
    "function::trigonometric::arcsine": math.asin,
    "function::trigonometric::arccosine": math.acos,
    "function::trigonometric::arctangent": math.atan,
    "function::trigonometric::arctangent2": math.atan2,
    "function::hyperbolic::sine": math.sinh,
    "function::hyperbolic::cosine": math.cosh,
    "function::hyperbolic::tangent": math.tanh,
    "function::rounding::floor": math.floor,
    "function::rounding::ceiling": math.ceil,
    "function::rounding::truncation": math.trunc,
    "function::rounding::ties_even": round,
    "function::rounding::ties_away": round_ties_away,
    "function::rounding::ties_up": round_ties_up,
    "function::order::minimum": min,
    "function::order::maximum": max,
    "function::order::clamp": clip,
    "function::magnitude::absolute": abs,
    "function::magnitude::sign": sign,
    "function::magnitude::hypotenuse": math.hypot,
    "function::special::gamma": _gamma,
    "function::special::log_gamma": _log_gamma,
    "function::special::factorial": _factorial,
    "function::special::error": math.erf,
    "function::special::error_complement": math.erfc,
    "function::integer::gcd": lambda a, b: math.gcd(int(a), int(b)),
    "function::complex::real_part": re,
    "function::complex::imaginary_part": im,
    "function::complex::conjugate": conjugate,
    "function::complex::argument": arg,
}

#: the operations Python has no exact spelling for, which a rendered
#: function calls through a helper
HELPER_FUNCTIONS = (div_trunc, div_euclid, rem_euclid, round_ties_up, round_ties_away,
                    sign, cbrt, clip, re, im, conjugate, arg)


def helpers() -> dict:
    """Intent:
        `{alias: callable}` for every helper, named by the alias table.

    Raises:
        LookupError: a helper's path has no alias.
    """
    from .aliases import alias_of
    out = {}
    for fn in HELPER_FUNCTIONS:
        alias = alias_of(fn.__koine__)
        if alias is None:
            raise LookupError(f"{fn.__koine__} has no alias in aliases.yaml")
        out[alias] = fn
    return out
