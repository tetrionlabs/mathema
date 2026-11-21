# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Raise-reading cases: a listed missing value beside an interval."""
from typing import Optional


def two_rare(x: Optional[float], y: float) -> float:
    if x is None:
        if y == 0.123456:
            return 1.0
        raise ValueError("none")
    if x > 0:
        raise ValueError("pos")
    return 0.0


def zero_rare(x: Optional[float], y: float) -> float:
    if x is None:
        if y == 0.123456:
            return 1.0
        return 0.0
    return 0.0


CASES = [
    (two_rare, "for x in {1, None}, y in [0, 1], raises(f(x, y), ValueError)"),
    (two_rare, "for x in {1, nan}, y in [0, 1], raises(f(x, y), ValueError)"),
    (zero_rare, "for x in {1, None}, y in [0, 1], f(x, y) == 0"),
    (zero_rare, "for x in {1, None}, y in {0, 0.123456, 1}, f(x, y) == 0"),
    (zero_rare, "for x in {1, None}, y in {0, 0.123456, 1}, f(x, y) == 0", ),
]
