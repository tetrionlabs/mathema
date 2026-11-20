# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Review-three cases, batch 7: policy rows through a wrapper and a lambda default."""
import functools
from typing import Optional

VALUE = "for x in [0, 1], y in [-1, 1], f(x, y) == x * y"


def rare_swallow(fn):
    @functools.wraps(fn)
    def w(x, y):
        if y == 0.123456:
            return 0.0
        return fn(x, y)
    return w


@rare_swallow
def pol_wrap_rare(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_lam_kw(x: Optional[float], y: float) -> float:
    g = lambda *, a=1 / (y - 0.123456): a  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_lam_plain(x: Optional[float], y: float) -> float:
    g = lambda: 1 / (y - 0.123456)  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


CASES = [
    (pol_wrap_rare, [VALUE, "absent(f, x) raises(TypeError)"]),
    (pol_wrap_rare, [VALUE]),
    (pol_lam_kw, [VALUE, "absent(f, x) raises(TypeError)"]),
    (pol_lam_plain, [VALUE, "absent(f, x) raises(TypeError)"]),
]
