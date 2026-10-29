# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Whether a `Decimal` operation rounded while a point was computed.

A `Decimal` operation rounds its result to the decimal context's
precision when the exact result has more digits than the context keeps
(a division such as `Decimal(1) / 3`, a square root, a product past the
precision). The rounded value is another number than the mathematics,
and it is no float64 value either, so neither the exact reading nor
float64's precision bound speaks for it: a point where one rounded is
not counted (`ROUNDED`).
"""
from __future__ import annotations

import contextlib
import decimal

__all__ = ["ROUNDED", "RoundingWatch", "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the context's `Inexact` or
    `Rounded` flag."""

    def __init__(self) -> None:
        self.rounded = False


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
        try:
            yield watch
        finally:
            watch.rounded = bool(context.flags[decimal.Inexact]
                                 or context.flags[decimal.Rounded])
