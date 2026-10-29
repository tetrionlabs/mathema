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
the context's rounding can account for (`beyond_rounding`). A function
that installs a decimal context of its own (`localcontext`,
`setcontext`, a `Context` it builds or one of the module's contexts)
rounds where no flag is read, so every point it computes is not
counted (`OWN_CONTEXT`, `installs_context`).
"""
from __future__ import annotations

import contextlib
import decimal
import inspect
import math
import types
from fractions import Fraction

__all__ = ["OWN_CONTEXT", "REASONS", "ROUNDED", "RoundingWatch",
           "beyond_rounding", "installs_context", "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"
#: why a point a function with a decimal context of its own computes is
#: not counted
OWN_CONTEXT = ("the function installs a decimal context of its own, whose "
               "rounding is not read; the exact reading declined")
#: every reason a point is not counted for its Decimal arithmetic
REASONS = (ROUNDED, OWN_CONTEXT)
#: the names through which a function reaches a decimal context other
#: than the current one
_CONTEXT_NAMES = frozenset({"localcontext", "setcontext", "Context",
                            "DefaultContext", "BasicContext",
                            "ExtendedContext"})


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the context's `Inexact` or
    `Rounded` flag, or when a function it ran installs a context of its
    own; `precision` is the context's precision in digits, None for a
    context of the function's own; `reason` is why the point is not
    counted (`REASONS`), None while it is."""

    def __init__(self) -> None:
        self.rounded = False
        self.precision: "int | None" = decimal.getcontext().prec
        self.reason: "str | None" = None


@contextlib.contextmanager
def watched(own: bool = False):
    """Intent:
        Run the block in a copy of the current decimal context with its
        flags cleared, and yield a `RoundingWatch` whose `rounded` is
        set when the block ends (by a return or a raise) if a `Decimal`
        operation in it rounded, or if `own` (a function the block runs
        installs a context of its own, `installs_context`), where the
        flags are not this context's.
        The copy keeps the precision, the rounding mode and the traps,
        so the block computes as it would outside.
    """
    watch = RoundingWatch()
    with decimal.localcontext() as context:
        context.clear_flags()
        watch.precision = context.prec
        try:
            yield watch
        finally:
            if own:
                watch.rounded, watch.precision = True, None
                watch.reason = OWN_CONTEXT
            elif context.flags[decimal.Inexact] \
                    or context.flags[decimal.Rounded]:
                watch.rounded, watch.reason = True, ROUNDED


def _functions_in(value):
    """The Python functions `value` stands for: itself, what it wraps
    (`__wrapped__`, a bound method's function), and the functions its
    closure holds."""
    seen: list = []
    stack = [value]
    while stack:
        v = stack.pop()
        if any(v is s for s in seen):
            continue
        if isinstance(v, types.MethodType):
            stack.append(v.__func__)
            continue
        if isinstance(v, types.FunctionType):
            seen.append(v)
            stack.extend(c.cell_contents for c in (v.__closure__ or ())
                         if _filled(c))
        wrapped = getattr(v, "__wrapped__", None)
        if wrapped is not None:
            stack.append(wrapped)
        if callable(v) and not isinstance(v, (types.FunctionType, type)):
            call = getattr(type(v), "__call__", None)
            if isinstance(call, types.FunctionType):
                stack.append(call)
    return [v for v in seen if isinstance(v, types.FunctionType)]


def _filled(cell) -> bool:
    try:
        cell.cell_contents
    except ValueError:
        return False
    return True


def _codes(code: types.CodeType):
    """`code` and every code object nested in it (a nested function, a
    lambda, a comprehension)."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _codes(const)


def _names_a_context(fn: types.FunctionType, names: set) -> bool:
    """Whether a name `fn`'s code reads reaches a decimal context other
    than the current one: a global bound to `localcontext`,
    `setcontext`, `Context` or a `Context` instance, or one of their
    names read as an attribute or imported where the code reads the
    `decimal` module."""
    targets = (decimal.localcontext, decimal.setcontext, decimal.Context)
    for name in names:
        value = fn.__globals__.get(name)
        if any(value is t for t in targets) \
                or isinstance(value, decimal.Context):
            return True
    reads_decimal = "decimal" in names or any(
        fn.__globals__.get(n) is decimal for n in names)
    return reads_decimal and bool(names & _CONTEXT_NAMES)


def installs_context(callee, depth: int = 4) -> bool:
    """Intent:
        Whether `callee`, or a Python function it reaches through its
        globals within `depth` calls, reads a decimal context other
        than the current one (`_names_a_context`): one it installs or
        computes in, whose flags a `watched` block does not read.
        A callee with no Python code (a builtin) is read as installing
        none, and so is mathema's own code, a wrapper's closure read for
        the function it calls.
    """
    seen: set = set()
    todo = [(f, 0) for f in _functions_in(callee)]
    while todo:
        fn, level = todo.pop()
        if id(fn.__code__) in seen:
            continue
        seen.add(id(fn.__code__))
        if (fn.__module__ or "").split(".")[0] == "mathema":
            # the harness's own wrappers, whose closures hold the
            # function they call (`_functions_in`)
            continue
        names: set = set()
        for code in _codes(fn.__code__):
            names.update(code.co_names)
        if _names_a_context(fn, names):
            return True
        if level >= depth:
            continue
        for name in names:
            value = fn.__globals__.get(name)
            if value is not None and not inspect.ismodule(value):
                todo.extend((f, level + 1) for f in _functions_in(value)
                            if f is not fn)
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
