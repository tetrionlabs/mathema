# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Guards with compound conditions, two parameters, and endpoints %g rounds."""
import math

from mathema import enforce_domain
from mathema.conjecture import claim


def two_param_guard(x: float, y: float) -> float:
    if x > y:
        raise ValueError("x above y")
    return y - x


def two_param_sum(x: float, y: float) -> float:
    if x + y < 0:
        raise ValueError("negative total")
    return math.sqrt(x + y)


def mixed_guards(x: float, y: float) -> float:
    if x < 0:
        raise ValueError("x negative")
    if x * y > 4:
        raise ValueError("product too big")
    return x * y


def compound_one(x: float) -> float:
    if not (x >= -2 and x <= 3) or x == 1:
        raise ValueError("outside")
    return x / (x - 1)


def fine_upper(x: float) -> float:
    if x > 0.1234567:
        raise ValueError("above")
    if x < -1:
        raise ValueError("below")
    return x * x


def fine_lower(x: float) -> float:
    if x < 2.0000001:
        raise ValueError("below")
    if x > 9:
        raise ValueError("above")
    return x


def big_endpoint(x: float) -> float:
    if x > 1234567.5 or x < -1234567.5:
        raise ValueError("outside")
    return x


def strict_open(x: float) -> float:
    if x <= 0 or x >= 1:
        raise ValueError("outside")
    return math.log(x) + math.log(1 - x)


def guarded_nan(x: float) -> float:
    if math.isnan(x) or x < 0:
        raise ValueError("bad")
    return math.sqrt(x)


def abs_guard(x: float) -> float:
    if abs(x) > 2:
        raise ValueError("outside")
    return x * x


def sqrt_guard(x: float) -> float:
    if x * x > 2:
        raise ValueError("outside")
    return x


_OPEN = claim("for x in (0, 1], f(x) >= 0").domain["x"]
_OPEN_SPLIT = claim("for w in (-1, -0.5) ∪ (0.5, 3), f(w) >= -1").domain["w"]


@enforce_domain(domain={"x": _OPEN})
def open_left_cut(x: float) -> float:
    if x > 0.5:
        raise ValueError("above half")
    return x


@enforce_domain(domain={"w": _OPEN_SPLIT})
def open_split_mean(w: list) -> float:
    return sum(w) / len(w)


@enforce_domain(domain={"w": _OPEN_SPLIT})
def open_split_scalar(w: float) -> float:
    if w > 2:
        raise ValueError("above two")
    return w
@enforce_domain(domain={"x": (-1, 0.1234567)})
def declared_fine(x: float) -> float:
    return x * x
