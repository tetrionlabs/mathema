# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Review-three cases, batch 3: missing values in domains."""
import math
from typing import Optional


def raise_neg(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def raise_neg_opt(x: Optional[float]) -> float:
    if x is None:
        return 0.0
    if x < 0:
        raise ValueError("neg")
    return x


def two(x: Optional[float], y: float) -> float:
    if x is None:
        if y == 0.5:
            return 1.0
        raise ValueError("none")
    if x > 0:
        raise ValueError("pos")
    return 0.0


def zero_except_inside(x: Optional[float], y: float) -> float:
    if x is None:
        if y == 0.5:
            return 1.0
        return 0.0
    return 0.0


def nan_returns(x: float) -> float:
    if math.isnan(x):
        return 0.0
    if x < 0:
        raise ValueError("neg")
    return x


def negzero(x: float) -> float:
    if math.copysign(1.0, x) < 0:
        raise ValueError("neg")
    return x


def inf_raise(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


NEGR = "raises(f(x), ValueError)"
CASES = [
    (raise_neg, "for x in [-5, -1] : float|missing, " + NEGR, ("f(x)", "ValueError", None)),
    (nan_returns, "for x in [-5, -1] : float|missing, " + NEGR),
    (nan_returns, "for x in [-5, -1] : float|nan, " + NEGR),
    (nan_returns, "for x in {-1, -2, nan}, " + NEGR),
    (raise_neg_opt, "for x in [-5, -1] : float|absent, " + NEGR),
    (raise_neg_opt, "for x in {-1, -2, None}, " + NEGR),
    (two, "for x in {1, None}, y in [0, 1], raises(f(x, y), ValueError)"),
    (two, "for x in {1, 2}, y in [0, 1], raises(f(x, y), ValueError)"),
    (zero_except_inside, "for x in {1, None}, y in [0, 1], f(x, y) == 0"),
    (zero_except_inside, "for x in {1, None}, y in {0, 0.5, 1}, f(x, y) == 0"),
    (negzero, "for x in {-1.0, -0.0}, " + NEGR),
    (negzero, "for x in [-5, 0], " + NEGR),
    (inf_raise, "for x in {-inf, -1}, " + NEGR),
    (inf_raise, "for x in [-oo, -1], " + NEGR),
    (nan_returns, "for x in {-1, -2, nan}, y in [0, 1], " + NEGR),
]
