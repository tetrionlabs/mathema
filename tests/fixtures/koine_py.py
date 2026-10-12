# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The Python functions whose bodies the golden KOINE documents in
`tests/data/koine` hold, one document per function."""
import math

HALF = 0.5


def growth(x: float, r: float) -> float:
    if r < -1:
        raise ValueError("rate below -1")
    g = 1 + r
    return x * g


def ema(xs: list[float], alpha: float) -> float:
    if alpha < 0:
        raise ValueError("alpha must be nonnegative")
    acc = xs[0]
    for v in xs[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def tax(x: float, r: float) -> float:
    if x < 0:
        return 0
    elif x < HALF:
        return r * x
    else:
        return r * HALF + (x - HALF) * (2 * r)


def mean(xs: list[float]) -> float:
    total = 0.0
    for v in xs:
        total += v
    return total / len(xs)


def dot(a: list[float], b: list[float]) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def quotient(a: int, b: int) -> int:
    return a // b


def remainders(a: float, b: float) -> float:
    q = math.fmod(a, b)
    h = math.hypot(a, b)
    return q + h + round(a) + math.pi
