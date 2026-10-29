# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Whether a `Decimal` operation rounded while a point was computed.

A `Decimal` operation rounds its result to the decimal context's
precision when the exact result has more digits than the context keeps
(a division such as `Decimal(1) / 3`, a square root, a product past the
precision). The rounded value is another number than the mathematics,
and it is no float64 value either, so neither the exact reading nor
float64's precision bound speaks for it: a point where one rounded is
not counted (`ROUNDED`), unless the relation fails there by more than
the context's rounding can account for (`beyond_rounding`).
"""
from __future__ import annotations

import contextlib
import decimal
import math
from fractions import Fraction

__all__ = ["ROUNDED", "RoundingWatch", "beyond_rounding", "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the context's `Inexact` or
    `Rounded` flag, and `precision` is the context's precision in
    digits."""

    def __init__(self) -> None:
        self.rounded = False
        self.precision = decimal.getcontext().prec


@contextlib.contextmanager
def watched():
    """Intent:
        Run the block in a copy of the current decimal context with its
        flags cleared, and yield a `RoundingWatch` whose `rounded` is
        set when the block ends (by a return or a raise) if a `Decimal`
        operation in it rounded. The copy keeps the precision, the
        rounding mode and the traps, so the block computes as it would
        outside.

    Notes:
        A body that installs a context of its own (`localcontext(ctx)`
        with a fresh `Context`) rounds in that context, whose flags the
        watch does not read.
    """
    watch = RoundingWatch()
    with decimal.localcontext() as context:
        context.clear_flags()
        watch.precision = context.prec
        try:
            yield watch
        finally:
            watch.rounded = bool(context.flags[decimal.Inexact]
                                 or context.flags[decimal.Rounded])


def _exact(value) -> "Fraction | None":
    """The exact rational a finite int, Fraction, float or `Decimal`
    stands for, else None (a non-finite value, anything else)."""
    if isinstance(value, bool):
        return Fraction(int(value))
    if isinstance(value, (int, Fraction)):
        return Fraction(value)
    if isinstance(value, float) and math.isfinite(value):
        return Fraction(value)
    if isinstance(value, decimal.Decimal) and value.is_finite():
        return Fraction(value)
    return None


#: float64's unit roundoff, 2^-53
_FLOAT64_U = Fraction(1, 2 ** 53)


def rounding_bound(lv, rv, precision: int) -> "Fraction | None":
    """Intent:
        The largest miss rounding can put between two computed sides:
        8u|side| summed over the sides, u = 10^(1-p)/2 the decimal
        context's unit roundoff at `precision` digits for a side that is
        not a float, and float64's unit roundoff 2^-53 for a float side,
        the same shape as float64's allowance. None when a side is no
        finite number.
    """
    total = Fraction(0)
    decimal_u = Fraction(1, 2 * 10 ** (precision - 1))
    for side in (lv, rv):
        exact = _exact(side)
        if exact is None:
            return None
        u = _FLOAT64_U if isinstance(side, float) else decimal_u
        total += 8 * max(u, decimal_u) * abs(exact)
    return total


def beyond_rounding(lv, rv, relation: str, precision: int, holds) -> bool:
    """Intent:
        Whether the relation fails at the computed sides `lv` and `rv`
        however far within `rounding_bound` rounding moved them:
        `holds(a, b)` (the relation as the route judges it, True, False
        or None) is False with `lv` moved by the bound in the direction
        that favours the relation (toward `rv` for `==` and `~=`, but
        no further; away from it for `!=`; down for `<` and `<=`, up for
        `>` and `>=`). False for any other relation or side.
    """
    bound = rounding_bound(lv, rv, precision)
    if bound is None:
        return False
    a, b = _exact(lv), _exact(rv)
    assert a is not None and b is not None
    if relation in ("==", "~="):
        moved = b if abs(a - b) <= bound else a - bound if a > b else a + bound
    elif relation == "!=":
        moved = a + bound if a >= b else a - bound
    elif relation in ("<", "<="):
        moved = a - bound
    elif relation in (">", ">="):
        moved = a + bound
    else:
        return False
    return holds(moved, b) is False
