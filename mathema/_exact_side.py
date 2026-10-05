# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's sides evaluated exactly at an executed point.

On a computation line the function runs in floats, as it does for its
callers, but the claim's own arithmetic is mathematics: its literals are
the numbers written and its words compute exactly. This evaluates both
sides with every float input read as the exact rational it holds, each
call of the function under test made with the original floats and its
result read back as the exact rational it returned, and the claim's own
`+ - * /`, `abs`, `min` and `max` carried out in rationals. A side that
any step leaves inexact (a square root, a logarithm, a float literal the
words could not keep exact) is not returned: the caller keeps the float
evaluation.
"""
from __future__ import annotations

from fractions import Fraction

#: what a successful exact evaluation returns per side: an int, a
#: Fraction, a bool, or a list of them
EXACT_TYPES = (int, Fraction, bool)


def _np():
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def to_exact(value):
    """A float read as the exact rational it holds, a float array or list
    as an object array (or list) of them; anything else unchanged."""
    np = _np()
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Fraction(value) if value == value and abs(value) != float("inf") else value
    if np is not None and isinstance(value, np.ndarray) and value.dtype.kind == "f":
        out = np.empty(value.shape, dtype=object)
        for idx, v in np.ndenumerate(value):
            out[idx] = to_exact(float(v))
        return out
    if np is not None and isinstance(value, np.floating):
        return to_exact(float(value))
    if isinstance(value, list) and value and all(isinstance(v, float) for v in value):
        if np is not None:
            return to_exact(np.asarray(value, dtype=float))
        return [to_exact(v) for v in value]
    return value


def to_float(value):
    """The inverse of `to_exact` for a call of the function under test:
    the floats the executed point held."""
    np = _np()
    if isinstance(value, Fraction):
        return float(value)
    if np is not None and isinstance(value, np.ndarray) and value.dtype == object:
        return value.astype(float)
    if isinstance(value, list):
        return [to_float(v) for v in value]
    return value


class _Inexact(Exception):
    """A callee run on exact values returned a value that is not exact."""


def wrap(callee, exact_calls: bool = False):
    """`callee` called with the executed floats, its result read back
    exactly; with `exact_calls`, called with the exact values themselves,
    its result kept only when it is exact (a float result raises
    `_Inexact`)."""
    def call(*args, **kwargs):
        if exact_calls:
            result = callee(*args, **kwargs)
            if _exact_value(result) is None:
                raise _Inexact(type(result).__name__)
            return result
        else:
            result = callee(*[to_float(a) for a in args],
                            **{k: to_float(v) for k, v in kwargs.items()})
        return to_exact(result)
    return call


def _exact_value(value):
    """`value` as a plain exact value (an int, Fraction or bool, or a
    nested list of them), or None when any part is inexact."""
    np = _np()
    if np is not None and isinstance(value, np.ndarray):
        value = value.tolist()
    if np is not None and isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, EXACT_TYPES):
        return value
    if isinstance(value, (list, tuple)):
        parts = [_exact_value(v) for v in value]
        if any(p is None for p in parts):
            return None
        return parts
    return None


def exact_literals(code):
    """`code` with every float literal replaced by the exact decimal it
    was written as (the shortest decimal that reads back as the float),
    nested code objects included."""
    import math
    import types
    if code is None:
        return None
    consts = []
    for c in code.co_consts:
        if isinstance(c, float) and not isinstance(c, bool) and math.isfinite(c):
            consts.append(Fraction(repr(c)))
        elif isinstance(c, types.CodeType):
            consts.append(exact_literals(c))
        else:
            consts.append(c)
    try:
        return code.replace(co_consts=tuple(consts))
    except (TypeError, ValueError):
        return code


def exact_sides(code_l, code_r, env: dict, callees: dict,
                exact_calls: bool = False) -> "tuple | None":
    """Intent:
        `(left, right)` evaluated exactly at the point `env` holds, the
        names in `callees` (the function under test and any function the
        claim binds) called with the executed floats and read back
        exactly, or None when either side is not exact. With
        `exact_calls` each callee runs on the exact values themselves
        (Fractions in place of floats), the mathematics of the point
        rather than its float computation.
    """
    exact_env = {k: (wrap(callees[k], exact_calls) if k in callees
                     else to_exact(v))
                 for k, v in env.items() if k != "__builtins__"}
    for k, v in callees.items():
        exact_env.setdefault(k, wrap(v, exact_calls))
    try:
        left = eval(exact_literals(code_l), {"__builtins__": {}}, exact_env)
        right = eval(exact_literals(code_r), {"__builtins__": {}}, exact_env) \
            if code_r is not None else None
    except Exception:
        return None
    left = _exact_value(left)
    right = _exact_value(right) if code_r is not None else None
    if left is None or (code_r is not None and right is None):
        return None
    return left, right
