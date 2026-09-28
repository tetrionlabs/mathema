# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Exact arithmetic for the reductions a premise names.

A premise decides whether a point lies in a claim's domain, which is a
question about the mathematics: over R the standard deviation of a
constant sequence is zero, so `assuming std(xs, ddof=1) > 0` excludes
every constant sequence. Float arithmetic leaves a residue near 1e-17
there (the mean of three copies of -0.1 rounds to -0.10000000000000002),
which would admit the point and hand the computation an input the claim
never covered. The functions here compute `sum`, `prod`, `mean`, `var`,
`std` and `dot` of a flat sequence of real numbers with rational
arithmetic and return the float nearest the exact value; a standard
deviation is exactly `0.0` when the variance is exactly zero.

Anything the exact path does not cover (a matrix, an `axis`, a value
that is not a finite real number, fewer than `ddof + 1` elements) goes to
the float evaluator in `_linalg_eval`, so the premise vocabulary is the
same on both paths.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any, Callable

__all__ = ["premise_functions"]


def _flat_reals(value: Any) -> list[Fraction] | None:
    """Intent:
        The elements of `value` as exact rationals when `value` is a
        flat sequence of finite real numbers (a list or tuple, or a
        one-dimensional array-like with `tolist()`), else `None`.
    """
    if isinstance(value, (str, bytes)):
        return None
    if hasattr(value, "tolist") and getattr(value, "ndim", 1) == 1:
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return None
    out: list[Fraction] = []
    for e in value:
        if isinstance(e, bool) or not isinstance(e, (int, float)):
            return None
        if isinstance(e, float) and not math.isfinite(e):
            return None
        out.append(Fraction(e))
    return out


def _exact(name: str, fallback: Callable) -> Callable:
    """Intent:
        The reduction `name` computed exactly on a flat real sequence,
        delegating every other call (matrices, `axis`, non-real
        elements, too few elements for `ddof`) to `fallback`.
    """

    def reduce(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("axis") is not None or not args:
            return fallback(*args, **kwargs)
        xs = _flat_reals(args[0])
        if xs is None:
            return fallback(*args, **kwargs)
        n = len(xs)
        if name == "sum":
            return float(sum(xs, Fraction(0)))
        if name == "prod":
            p = Fraction(1)
            for x in xs:
                p *= x
            return float(p)
        if name == "dot":
            if len(args) < 2:
                return fallback(*args, **kwargs)
            ys = _flat_reals(args[1])
            if ys is None or len(ys) != n:
                return fallback(*args, **kwargs)
            return float(sum((x * y for x, y in zip(xs, ys)), Fraction(0)))
        if n == 0:
            return fallback(*args, **kwargs)
        mean = sum(xs, Fraction(0)) / n
        if name == "mean":
            return float(mean)
        ddof = kwargs.get("ddof", args[1] if len(args) > 1 else 0)
        if isinstance(ddof, bool) or not isinstance(ddof, int) or n - ddof <= 0:
            return fallback(*args, **kwargs)
        var = sum(((x - mean) ** 2 for x in xs), Fraction(0)) / (n - ddof)
        if name == "var":
            return float(var)
        return 0.0 if var == 0 else math.sqrt(float(var))

    reduce.__name__ = name
    return reduce


def premise_functions(float_functions: dict) -> dict:
    """The premise vocabulary: `float_functions` (the float evaluator's
    table, keyed by grammar word) with `sum`, `prod`, `mean`, `var`,
    `std` and `dot` replaced by their exact counterparts, each of which
    falls back to the float function it replaces outside the flat
    real-sequence case."""
    out = dict(float_functions)
    for name in ("sum", "prod", "mean", "var", "std", "dot"):
        if name in float_functions:
            out[name] = _exact(name, float_functions[name])
    return out
