# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sample of claims with a bare-number tolerance or none, over every
relation that reads a tolerance and each route, and the rows they give
(`records`), for tests/test_a_bare_tolerance_keeps_its_meaning.py."""
import math

import mathema
from mathema.conjecture import claim
from mathema.lexicon import exact_offset, sin3


def near_identity(x: float) -> float:
    return x + 1e-6


def scaled(x: float) -> float:
    return x * (1 + 1e-10)


def square(x: float) -> float:
    return x * x


def cancelling(x: float) -> float:
    return (x + 1e8) - 1e8


def identity(x: float) -> float:
    return x


def total(xs: list) -> float:
    return sum(xs)


SAMPLE = [
    (exact_offset, "for x in [0, 1], f(x) ~= x", None, None),
    (exact_offset, "for x in [0, 1], f(x) ~= x", 1e-7, None),
    (exact_offset, "for x in [0, 1], f(x) ~= x", 1e-13, None),
    (exact_offset, "for x in [0, 1], f(x) ~= x", 1e-7, "probe"),
    (sin3, "for x in [0, 0.5], f(x) ~= sin(x)", None, "probe"),
    (sin3, "for x in [0, 0.1], f(x) ~= sin(x)", 1e-4, "probe"),
    (near_identity, "for x in [0, 10], f(x) ~= x", 1e-5, None),
    (near_identity, "for x in [0, 10], f(x) ~= x", 1e-7, "probe"),
    (near_identity, "for x in [0, 10], f(x) == x", 1e-5, None),
    (scaled, "for x in [1, 1e6], f(x) ~= x", None, "probe"),
    (scaled, "for x in [1, 1e6], f(x) == x", 1e-3, None),
    (square, "for x in [-2, 2], f(x) <= 4", 1e-9, None),
    (square, "for x in [-2, 2], f(x) >= 0", 1e-3, "probe"),
    (cancelling, "for x in [0, 1], f(x) ~= x", 1e-8, "probe"),
    (cancelling, "for x in [0, 1], f(x) == x", None, None),
    (square, "for x in [0, 1], abs(f(x) - x * x) <= ε", None, None),
    (square, "for x in [0, 1], abs(f(x) - x * x) <= ε", 1e-6, "probe"),
    (square, "for x in [0, 3], assuming x ~= 2, f(x) ~= 4", 1e-3, "probe"),
    (identity, "for x in [0, 1], f =:= g", 1e-4, None),
    (total, "for xs in R^n, f(xs) ~= sum(xs)", None, "probe"),
    (total, "for xs in R^n, f(xs) ~= sum(xs)", 1e-6, "probe"),
]


def _plain(value):
    """`value` as JSON can hold it, floats by their repr."""
    if isinstance(value, float):
        return repr(value) if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return repr(value)


def records() -> list:
    out = []
    for fn, law, tolerance, route in SAMPLE:
        kwargs = {"tolerance": tolerance}
        if route:
            kwargs["route"] = route
        if "=:=" in law:
            kwargs["funcs"] = {"g": identity}
        rows = mathema.check(fn, claims=[claim(law, **kwargs)]).probes
        out.append({"law": law, "tolerance": tolerance, "route": route,
                    "rows": [{"name": p.name, "verdict": p.verdict,
                              "route": p.route,
                              "tolerance": _plain(p.tolerance),
                              "note": p.note,
                              "counterexample": _plain(p.counterexample),
                              "n": p.n, "meta": _plain(p.meta or {})}
                             for p in rows]})
    return out
