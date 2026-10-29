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
that has no exact reading is read as a rounded one, though no watched
context rounded (`UNSEEN`): not counted, unless it misses by more than
rounding to the smallest precision watched can account for, which the
executed values witness. A context's own method read during the run
(`ctx.divide(a, b)`) adds its precision; a `Decimal` method run beside
a context the block does not watch may compute in it (`context=ctx`),
and the point's rounding is then unbounded (`UNBOUND`).
"""
from __future__ import annotations

import contextlib
import decimal
import math
import sys
from fractions import Fraction

__all__ = ["REASONS", "ROUNDED", "RoundingWatch", "UNBOUND", "UNSEEN",
           "beyond_rounding", "holds_decimal", "may_touch_decimal",
           "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"
#: why a point whose side holds a `Decimal` with no exact reading, where
#: no watched context rounded, is not counted unless it misses past the
#: rounding bound
UNSEEN = ("a Decimal operation may have rounded in a context the reading "
          "did not see; the exact reading declined")
#: why a point where a Decimal method ran beside a decimal context the
#: reading does not watch is not counted, its rounding unbounded
UNBOUND = ("a Decimal operation may have rounded in a context the reading "
           "could not bound; the exact reading declined")
#: every reason a point is not counted for its Decimal arithmetic
REASONS = (ROUNDED, UNSEEN, UNBOUND)


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the `Inexact` or `Rounded` flag
    of a watched context, or once a `Decimal` method ran beside a
    context the block does not watch (`UNBOUND`); `precision` is the
    smallest precision any watched context, or any context whose own
    method the block called, held, 1 when unbounded: the one the
    rounding bound reads; `reason` is why the point is not counted,
    None while it is."""

    def __init__(self) -> None:
        self.rounded = False
        self.precision: "int | None" = decimal.getcontext().prec
        self.reason: "str | None" = None
        #: the precisions of the contexts whose own methods ran
        self.called: list = []
        self.unbound = False


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
def watched(hooked: bool = True):
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
        With `hooked` (`may_touch_decimal`), a profiler reads the block's
        calls for the decimal contexts' own methods (`_called`); it is
        set for the block only and the previous profiler is restored
        when the block ends. A context reached otherwise (one built before the block and
        used through its own methods, `localcontext` bound under another
        name before the block) is not watched: a `Decimal` it rounded
        reads as unrounded here (`UNSEEN`).
    """
    watch = RoundingWatch()
    reached: dict = {}

    def profile(frame, event, arg):
        if event == "c_call":
            _called(watch, installed, reached, frame, arg)
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
    previous = sys.getprofile()
    if hooked:
        sys.setprofile(profile)
    try:
        yield watch
    finally:
        if hooked:
            sys.setprofile(previous)
        _SETCONTEXT(outer)
        decimal.localcontext, decimal.setcontext = saved  # type: ignore[assignment]
        _INSTALLED.pop()
        watch.precision = min([getattr(c, "lowest", c.prec) if c is context
                               else c.prec for c in installed]
                              + watch.called)
        if watch.unbound:
            watch.rounded, watch.reason, watch.precision = True, UNBOUND, 1
        elif any(c.flags[decimal.Inexact] or c.flags[decimal.Rounded]
                 for c in installed):
            watch.rounded, watch.reason = True, ROUNDED


def _called(watch: RoundingWatch, installed: list, reached: dict, frame,
            function) -> None:
    """Intent:
        Read one call of a C function in a watched block: a method of a
        decimal context the block does not watch adds that context's
        precision to `watch.called`; a `Decimal` method called from a
        frame that reaches such a context (its locals, closure cells and
        arguments, or its module's globals) sets `watch.unbound`, since
        the method may compute in it (`context=ctx`). Calls made from
        mathema's own code are not read.
    """
    owner = getattr(function, "__self__", None)
    if isinstance(owner, decimal.Context):
        if not any(owner is c for c in installed):
            watch.called.append(owner.prec)
        return
    if not isinstance(owner, decimal.Decimal) or frame is None:
        return
    module = frame.f_globals.get("__name__", "") or ""
    if module.startswith("mathema.") and not module.startswith(
            "mathema.lexicon"):
        return

    def unwatched(values) -> bool:
        return any(isinstance(v, decimal.Context)
                   and not any(v is c for c in installed) for v in values)
    key = id(frame.f_globals)
    if key not in reached:
        reached[key] = unwatched(list(frame.f_globals.values()))
    if reached[key] or unwatched(list(frame.f_locals.values())):
        watch.unbound = True


#: the names through which code reaches decimal arithmetic
_DECIMAL_NAMES = frozenset({"decimal", "Decimal", "Context", "localcontext",
                            "setcontext", "getcontext"})
#: `may_touch_decimal`'s answer per code object
_TOUCHES: dict = {}


def may_touch_decimal(*callees) -> bool:
    """Intent:
        Whether running `callees` can reach decimal arithmetic: the
        decimal module is loaded, and a callee, or a Python function it
        reaches through its globals, closure cells and default arguments
        (six calls deep), lives in a module whose globals hold the
        decimal module or an object of it, or names one of
        `_DECIMAL_NAMES` in its code. A callee with no Python code is
        read as reaching none; mathema's own wrappers are read through
        their closures only. Answered once per code object.
    """
    if "decimal" not in sys.modules and "_decimal" not in sys.modules:
        return False
    return any(_reaches_decimal(c) for c in callees)


def _reaches_decimal(callee) -> bool:
    seen: set = set()
    todo = [(f, 0) for f in _functions_in(callee)]
    while todo:
        fn, level = todo.pop()
        code = fn.__code__
        if id(code) in seen:
            continue
        seen.add(id(code))
        known = _TOUCHES.get(code)
        if known is True:
            return True
        module = getattr(fn, "__module__", None) or ""
        if module.startswith("mathema.") and not module.startswith(
                "mathema.lexicon"):
            continue
        names: set = set()
        for nested in _codes(code):
            names.update(nested.co_names)
        if names & _DECIMAL_NAMES or _globals_hold_decimal(fn.__globals__):
            _TOUCHES[code] = True
            return True
        if level >= 6:
            continue
        reached = [fn.__globals__.get(n) for n in names]
        reached += list(fn.__defaults__ or ())
        reached += list((fn.__kwdefaults__ or {}).values())
        for value in reached:
            if value is not None and not isinstance(value, type(sys)):
                todo.extend((f, level + 1) for f in _functions_in(value))
    return False


_GLOBALS: dict = {}


def _globals_hold_decimal(env: dict) -> bool:
    """Whether a module's globals hold the decimal module or an object
    of it (`Decimal`, a context); a module found to is remembered."""
    key = id(env)
    if _GLOBALS.get(key) is env:
        return True
    held = any(v is decimal or getattr(type(v), "__module__", None)
               in ("decimal", "_decimal")
               or getattr(v, "__module__", None) in ("decimal", "_decimal")
               for v in list(env.values()))
    if held:
        _GLOBALS[key] = env
    return held


def _codes(code):
    """`code` and every code object nested in it."""
    yield code
    for const in code.co_consts:
        if hasattr(const, "co_consts"):
            yield from _codes(const)


def _functions_in(value) -> list:
    """The Python functions `value` stands for: itself, what it wraps
    (`__wrapped__`, a bound method's function, an object's `__call__`,
    a class's own methods), and the functions its closure holds."""
    import types
    found: list = []
    stack = [value]
    while stack:
        v = stack.pop()
        if any(v is f for f in found):
            continue
        if isinstance(v, types.MethodType):
            stack.append(v.__func__)
            continue
        if isinstance(v, types.FunctionType):
            found.append(v)
            for cell in v.__closure__ or ():
                try:
                    stack.append(cell.cell_contents)
                except ValueError:
                    pass
        elif isinstance(v, type):
            if getattr(v, "__module__", "") not in ("builtins",):
                stack.extend(f for f in vars(v).values()
                             if isinstance(f, (types.FunctionType,
                                               staticmethod, classmethod)))
            continue
        elif isinstance(v, (staticmethod, classmethod)):
            stack.append(v.__func__)
            continue
        elif callable(v):
            call = getattr(type(v), "__call__", None)
            if isinstance(call, types.FunctionType):
                stack.append(call)
        wrapped = getattr(v, "__wrapped__", None)
        if wrapped is not None:
            stack.append(wrapped)
    return found


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
