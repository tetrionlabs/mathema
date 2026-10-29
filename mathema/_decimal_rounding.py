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

The rounding is read from the contexts a point's computation runs in
(`watched`): the current context, and every context the computation
installs through `localcontext` or `setcontext`. A computation can
round in a context none of these is (one built earlier and used through
its own methods, `ctx.divide(a, b)`), so a side holding a `Decimal`
that has no exact reading is not counted either, though no watched
context rounded (`UNSEEN`), and no bound applies to it.
"""
from __future__ import annotations

import contextlib
import decimal
import math
import sys
from fractions import Fraction

__all__ = ["REASONS", "ROUNDED", "RoundingWatch", "UNSEEN",
           "beyond_rounding", "holds_decimal", "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"
#: why a point whose side holds a `Decimal` with no exact reading, where
#: no watched context rounded, is not counted
UNSEEN = ("a Decimal operation rounded in a context the reading did not "
          "see; the exact reading declined")
#: every reason a point is not counted for its Decimal arithmetic
REASONS = (ROUNDED, UNSEEN)


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the `Inexact` or `Rounded` flag
    of a watched context; `precision` is the smallest precision any
    watched context held, the one the rounding bound reads; `reason` is
    `ROUNDED` once it rounded, else None."""

    def __init__(self) -> None:
        self.rounded = False
        self.precision: "int | None" = decimal.getcontext().prec
        self.reason: "str | None" = None


class _Watched(decimal.Context):
    """The current context of a `watched` block: a decimal context that
    keeps the smallest precision it is given (`lowest`), so a body that
    lowers the precision and restores it is read at the lower one."""

    def __setattr__(self, name, value):
        if name == "prec" and isinstance(value, int):
            super().__setattr__("lowest",
                                min(getattr(self, "lowest", value), value))
        super().__setattr__(name, value)


#: the contexts the computations being watched installed, one list per
#: open `watched` block
_INSTALLED: list = []


def _from_mathema() -> bool:
    """Whether the call two frames up is mathema's own (its exact
    reading installs contexts of its own), the lexicon's examples
    aside."""
    name = sys._getframe(2).f_globals.get("__name__", "")
    return name.startswith("mathema.") and not name.startswith(
        "mathema.lexicon")


def _record(context) -> None:
    for installed in _INSTALLED:
        installed.append(context)


class _Entered:
    """A `localcontext` manager whose entered context is recorded."""

    def __init__(self, manager) -> None:
        self.manager = manager

    def __enter__(self):
        context = self.manager.__enter__()
        _record(context)
        return context

    def __exit__(self, *exc):
        return self.manager.__exit__(*exc)


_LOCALCONTEXT, _SETCONTEXT = decimal.localcontext, decimal.setcontext


def _localcontext(ctx=None, **kwargs):
    manager = _LOCALCONTEXT(ctx, **kwargs)
    return manager if _from_mathema() else _Entered(manager)


def _setcontext(context):
    _SETCONTEXT(context)
    if not _from_mathema():
        _record(context)


@contextlib.contextmanager
def watched():
    """Intent:
        Run the block in a copy of the current decimal context with its
        flags cleared (the same precision, rounding mode and traps), and
        yield a `RoundingWatch` set when the block ends (by a return or
        a raise): `rounded` if a `Decimal` operation in it raised the
        `Inexact` or `Rounded` flag of that context or of a context the
        block installed through `decimal.localcontext` or
        `decimal.setcontext`, and `precision` the smallest precision
        any of them held.

    Notes:
        A context reached otherwise (one built before the block and
        used through its own methods, `localcontext` bound under another
        name before the block) is not watched: a `Decimal` it rounded
        reads as unrounded here (`UNSEEN`).
    """
    watch = RoundingWatch()
    outer = decimal.getcontext()
    context = _Watched(prec=outer.prec, rounding=outer.rounding,
                       Emin=outer.Emin, Emax=outer.Emax,
                       capitals=outer.capitals, clamp=outer.clamp, flags=[],
                       traps=[s for s, on in outer.traps.items() if on])
    installed: list = [context]
    _INSTALLED.append(installed)
    saved = (decimal.localcontext, decimal.setcontext)
    decimal.localcontext, decimal.setcontext = (  # type: ignore[assignment]
        _localcontext, _setcontext)
    _SETCONTEXT(context)
    try:
        yield watch
    finally:
        _SETCONTEXT(outer)
        decimal.localcontext, decimal.setcontext = saved  # type: ignore[assignment]
        _INSTALLED.pop()
        watch.precision = min(getattr(c, "lowest", c.prec) if c is context
                              else c.prec for c in installed)
        if any(c.flags[decimal.Inexact] or c.flags[decimal.Rounded]
               for c in installed):
            watch.rounded, watch.reason = True, ROUNDED


def holds_decimal(value) -> bool:
    """Whether `value` is a finite `Decimal`, or a list, tuple or dict
    holding one at any depth. A NaN or an infinity is no value, read as
    such whatever its type."""
    if isinstance(value, decimal.Decimal):
        return value.is_finite()
    if isinstance(value, (list, tuple)):
        return any(holds_decimal(v) for v in value)
    if isinstance(value, dict):
        return any(holds_decimal(v) for v in value.values())
    return False


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


def beyond_rounding(lv, rv, relation: str, precision: "int | None",
                    holds) -> bool:
    """Intent:
        Whether the relation fails at the computed sides `lv` and `rv`
        however far within `rounding_bound` rounding moved them:
        `holds(a, b)` (the relation as the route judges it, True, False
        or None) is False with `lv` moved by the bound in the direction
        that favours the relation (toward `rv` for `==` and `~=`, but
        no further; away from it for `!=`; down for `<` and `<=`, up for
        `>` and `>=`). False for any other relation or side, and for a
        context of the function's own (`precision` None), whose
        precision is not known.
    """
    if precision is None:
        return False
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
