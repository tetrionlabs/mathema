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
(`ctx.divide(a, b)`) adds its precision; a `Decimal` method given a
context at its call site (`d.sqrt(context=ctx)`) computes in it, and the
point's rounding is then unbounded (`UNBOUND`).
"""
from __future__ import annotations

import contextlib
import decimal
import functools
import math
import sys
from fractions import Fraction

__all__ = ["REASONS", "ROUNDED", "RoundingWatch", "UNBOUND", "UNSEEN",
           "beyond_rounding", "holds_decimal", "may_touch_decimal",
           "touched_decimal", "watched"]

#: why a point where a `Decimal` operation rounded is not counted
ROUNDED = "a Decimal operation rounded; the exact reading declined"
#: why a point whose side holds a `Decimal` with no exact reading, where
#: no watched context rounded, is not counted unless it misses past the
#: rounding bound
UNSEEN = ("a Decimal operation may have rounded in a context the reading "
          "did not see; the exact reading declined")
#: why a point where a Decimal method was given a decimal context is not
#: counted, its rounding unbounded
UNBOUND = ("a Decimal operation may have rounded in a context the reading "
           "could not bound; the exact reading declined")
#: every reason a point is not counted for its Decimal arithmetic
REASONS = (ROUNDED, UNSEEN, UNBOUND)


class RoundingWatch:
    """The outcome of one `watched` block: `rounded` is True once a
    `Decimal` operation inside it raised the `Inexact` or `Rounded` flag
    of a watched context, or once a `Decimal` method was given a
    context at its call site (`UNBOUND`); `precision` is the
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
        #: whether the profiler read the block's calls
        self.hooked = False

    def unread(self, *sides) -> bool:
        """Read a point whose sides hold a Decimal from a block the
        profiler did not read as unbounded: its contexts are unknown.
        True when it was such a point."""
        if not self.hooked and any(holds_decimal(s) for s in sides):
            self.rounded, self.reason, self.precision = True, UNBOUND, 1
            return True
        return False


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
        when the block ends. A function of the block that hands a value
        to a C callable which may carry a context into a `Decimal`
        method (a `functools.partial`, `map`, a callable argument) and
        reaches a context the block does not watch leaves the point
        unbounded (`_returned`). A context reached otherwise is not
        watched: a `Decimal` it rounded reads as unrounded here
        (`UNSEEN`).
    """
    watch = RoundingWatch()

    def profile(frame, event, arg):
        # the reading never raises into the computation: a failure of
        # its own leaves the point unbounded
        try:
            if event == "c_call":
                _called(watch, installed, frame, arg)
            elif event == "return":
                _returned(watch, installed, frame)
        except Exception:
            watch.unbound = True
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
    watch.hooked = hooked
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


def _called(watch: RoundingWatch, installed: list, frame,
            function) -> None:
    """Intent:
        Read one call of a C function in a watched block: a method of a
        decimal context the block does not watch adds that context's
        precision to `watch.called`; a `Decimal` method given a context
        at its call site (`d.sqrt(context=ctx)`, `d.sqrt(ctx)`,
        `Decimal.sqrt(d, ctx)`, or arguments the site spreads with `*`
        or `**`) sets `watch.unbound`, since it computes in a context
        the block may not watch (`_given_context`). Calls made from
        mathema's own code are not read.
    """
    owner = getattr(function, "__self__", None)
    if isinstance(owner, decimal.Context):
        if not any(owner is c for c in installed):
            watch.called.append(owner.prec)
        return
    if isinstance(owner, decimal.Decimal):
        receivers = 0
    elif getattr(function, "__objclass__", None) is decimal.Decimal:
        # the class's own method, its Decimal passed first
        receivers = 1
    else:
        return
    if frame is None:
        return
    module = frame.f_globals.get("__name__", "") or ""
    if module.startswith("mathema.") and not module.startswith(
            "mathema.lexicon"):
        return
    if _given_context(frame, getattr(function, "__name__", ""), receivers):
        watch.unbound = True


#: `_given_context`'s answer per call site, `(code, instruction)`
_CALL_SITES: dict = {}


def _context_position(name: str) -> "int | None":
    """The position of the `context` parameter of the `Decimal` method
    `name`, its receiver not counted, as the module's pure-Python
    reading declares it; None for a method that takes none."""
    import inspect
    try:
        import _pydecimal
        method = getattr(_pydecimal.Decimal, name)
        params = list(inspect.signature(method).parameters)
    except (ImportError, AttributeError, TypeError, ValueError):
        return 0
    if "context" not in params:
        return None
    return params.index("context") - 1


def _site_text(frame) -> "tuple[str, bool]":
    """Intent:
        The source text of the call the frame is making: the call's own
        span where the code records instruction positions
        (`co_positions`, Python 3.11 on), else the frame's whole current
        line, with whether it is the whole line.

    Raises:
        LookupError, ValueError: the source cannot be read.
    """
    import linecache
    code = frame.f_code
    positions = getattr(code, "co_positions", None)
    if positions is None:
        line = linecache.getline(code.co_filename, frame.f_lineno)
        if not line:
            raise LookupError("no source line")
        return line, True
    line, end, col, end_col = list(positions())[frame.f_lasti // 2]
    lines = linecache.getlines(code.co_filename)[line - 1:end]
    if not lines or col is None or end_col is None:
        raise LookupError("no call position")
    text = (lines[0][col:end_col] if line == end else
            lines[0][col:] + "".join(lines[1:-1]) + lines[-1][:end_col])
    return text, False


def _given_context(frame, name: str, receivers: int) -> bool:
    """Intent:
        Whether the call the frame is making to the `Decimal` method
        `name` is given a context, read from the call's own source text
        (`_site_text`): a `context=` keyword, a positional argument at
        or past the context's position (`receivers` the arguments
        standing before the method's own), or a `*` or `**` spread.
        Where only the whole line is known, the one call on it naming
        `name` is read. True where the call site cannot be read, or the
        line holds no such call or more than one. Answered once per call
        site.
    """
    import ast
    key = (frame.f_code, frame.f_lasti)
    if key in _CALL_SITES:
        return _CALL_SITES[key]
    position = _context_position(name)
    given = True
    if position is None:
        given = False
    else:
        call = None
        try:
            text, whole_line = _site_text(frame)
            node = ast.parse(text.strip(), mode="exec" if whole_line
                             else "eval")
            if whole_line:
                named = [n for n in ast.walk(node) if isinstance(n, ast.Call)
                         and (isinstance(n.func, ast.Attribute)
                              and n.func.attr == name)]
                call = named[0] if len(named) == 1 else None
            else:
                call = getattr(node, "body", None)
        except (LookupError, SyntaxError, ValueError, TypeError,
                IndexError, AttributeError):
            call = None
        if isinstance(call, ast.Call):
            given = (any(k.arg in (None, "context") for k in call.keywords)
                     or any(isinstance(a, ast.Starred) for a in call.args)
                     or len(call.args) > position + receivers)
    _CALL_SITES[key] = given
    return given


#: `_hands_over`'s answer per code object
_HANDS_OVER: dict = {}
#: C callables that call a function they are given
_HIGHER_ORDER_NAMES = frozenset({"map", "filter", "reduce", "starmap",
                                 "methodcaller", "partial", "sorted", "min",
                                 "max", "accumulate"})


def _returned(watch: RoundingWatch, installed: list, frame) -> None:
    """Intent:
        Read one function of a watched block as it returns: one whose
        code may hand a context to a `Decimal` method through a C
        callable (`_hands_over`) sets `watch.unbound` when its locals
        (one level into a list, tuple, set or dict) or its module's
        globals hold a decimal context the block does not watch. Code of
        mathema's own is not read.
    """
    module = frame.f_globals.get("__name__", "") or ""
    if module.startswith("mathema.") and not module.startswith(
            "mathema.lexicon"):
        return
    if not _hands_over(frame):
        return

    def unwatched(values) -> bool:
        for v in values:
            items = (list(v.values()) if isinstance(v, dict) else list(v)
                     if isinstance(v, (list, tuple, set, frozenset)) else [v])
            for item in items:
                if isinstance(item, functools.partial):
                    item = [*item.args, *item.keywords.values()]
                    if unwatched(item):
                        return True
                    continue
                if isinstance(item, decimal.Context) and not any(
                        item is c for c in installed):
                    return True
        return False
    if unwatched(list(frame.f_locals.values())) or unwatched(
            list(frame.f_globals.values())):
        watch.unbound = True


def _hands_over(frame) -> bool:
    """Intent:
        Whether the frame's code holds a call through which a context
        could reach a `Decimal` method unseen by the profiler: a call of
        a `functools.partial`, of a C callable that calls what it is
        given (`map`, `functools.reduce`, `operator.methodcaller`, ...),
        of a C callable given a callable or a spread, or of a callable
        the code names in a way the reading cannot resolve (a local, a
        subscript, a call's result) other than a `Decimal` method by
        name. True where the source cannot be read. Answered once per
        code object.
    """
    import ast
    import inspect
    import textwrap
    import types
    code = frame.f_code
    if code in _HANDS_OVER:
        return _HANDS_OVER[code]
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(code)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        _HANDS_OVER[code] = True
        return True
    env = frame.f_globals
    builtins = env.get("__builtins__")
    builtins = (builtins if isinstance(builtins, dict)
                else getattr(builtins, "__dict__", {}))

    def resolve(node):
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            return builtins.get(node.id, _UNRESOLVED)
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            if base is _UNRESOLVED:
                return _UNRESOLVED
            return getattr(base, node.attr, _UNRESOLVED)
        return _UNRESOLVED

    def python_code(value) -> bool:
        return isinstance(value, (types.FunctionType, types.MethodType)) \
            or (isinstance(value, type) and getattr(
                value, "__module__", "") not in ("builtins", "decimal",
                                                 "_decimal"))
    decimal_methods = set(dir(decimal.Decimal))
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target = resolve(func)
        if target is _UNRESOLVED:
            if isinstance(func, ast.Attribute) \
                    and func.attr in decimal_methods:
                continue
            if isinstance(func, ast.Name) and func.id in (
                    "Decimal", "str", "float", "int", "len", "abs", "round",
                    "repr", "isinstance", "list", "tuple", "dict", "set"):
                continue
            found = True
            break
        if target is decimal.Decimal or isinstance(target, decimal.Context) \
                or python_code(target):
            continue
        if isinstance(target, functools.partial) or getattr(
                target, "__name__", "") in _HIGHER_ORDER_NAMES:
            found = True
            break
        given = [*node.args, *(k.value for k in node.keywords)]
        if any(isinstance(a, (ast.Starred, ast.Lambda)) for a in node.args) \
                or any(k.arg is None for k in node.keywords) \
                or any(callable(resolve(a)) and not isinstance(
                    resolve(a), type) for a in given):
            found = True
            break
    _HANDS_OVER[code] = found
    return found


_UNRESOLVED = object()


#: the names through which code reaches decimal arithmetic
_DECIMAL_NAMES = frozenset({"decimal", "Decimal", "Context", "localcontext",
                            "setcontext", "getcontext"})
#: `may_touch_decimal`'s answer per code object
_TOUCHES: dict = {}


def may_touch_decimal(*callees) -> bool:
    """Intent:
        Whether running `callees` can reach decimal arithmetic, which
        decides only whether a point's calls are read through the
        profiler (`watched`): the decimal module is loaded, and a
        callee, or a Python function it reaches through its globals,
        closure cells and default arguments (six calls deep, at most
        `_WALK_CAP` functions, past which the answer is True), lives in a
        module whose globals hold the decimal module or an object of it,
        or names one of `_DECIMAL_NAMES` in its code. A callee with no
        Python code is read as reaching none; mathema's own wrappers are
        read through their closures only. Answered once per function's
        code.

    Notes:
        A Decimal reached otherwise (through a module the walk does not
        enter, an object's method) comes from a run the profiler did not
        read, and a point whose side holds one is not counted
        (`RoundingWatch.unread`).
    """
    if "decimal" not in sys.modules and "_decimal" not in sys.modules:
        return False
    return any(_reaches_decimal(f) for c in callees
               for f in _functions_in(c) if not _from_mathema_module(f))


def touched_decimal(*callees) -> None:
    """Intent:
        Remember that running `callees` reached decimal arithmetic (a
        Decimal came back from a run the profiler did not read), so
        `may_touch_decimal` answers True for them from then on.
    """
    for callee in callees:
        for fn in _functions_in(callee):
            if not _from_mathema_module(fn):
                _TOUCHES[fn.__code__] = True


#: the most functions one `may_touch_decimal` walk reads
_WALK_CAP = 2000


def _from_mathema_module(fn) -> bool:
    module = getattr(fn, "__module__", None) or ""
    return module.startswith("mathema.") and not module.startswith(
        "mathema.lexicon")


def _reaches_decimal(root) -> bool:
    """`may_touch_decimal` for one Python function, remembered per code
    object."""
    known = _TOUCHES.get(root.__code__)
    if known is not None:
        return known
    seen: set = set()
    todo = [(root, 0)]
    answer = False
    while todo:
        fn, level = todo.pop()
        code = fn.__code__
        if id(code) in seen:
            continue
        seen.add(id(code))
        if len(seen) > _WALK_CAP or _TOUCHES.get(code) is True:
            answer = True
            break
        if _from_mathema_module(fn):
            continue
        names: set = set()
        for nested in _codes(code):
            names.update(nested.co_names)
        if names & _DECIMAL_NAMES or _globals_hold_decimal(fn.__globals__):
            answer = True
            break
        if level >= 6:
            continue
        reached = [fn.__globals__.get(n) for n in names]
        reached += list(fn.__defaults__ or ())
        reached += list((fn.__kwdefaults__ or {}).values())
        for value in reached:
            if value is not None and not isinstance(value, type(sys)):
                todo.extend((f, level + 1) for f in _functions_in(value))
    _TOUCHES[root.__code__] = answer
    return answer


#: `_globals_hold_decimal`'s answer per module, `(globals, answer)`
_GLOBALS: dict = {}


def _globals_hold_decimal(env: dict) -> bool:
    """Whether a module's globals hold the decimal module or an object
    of it (`Decimal`, a context), remembered per module."""
    key = id(env)
    known = _GLOBALS.get(key)
    if known is not None and known[0] is env:
        return known[1]
    held = any(v is decimal or getattr(type(v), "__module__", None)
               in ("decimal", "_decimal")
               or getattr(v, "__module__", None) in ("decimal", "_decimal")
               for v in list(env.values()))
    _GLOBALS[key] = (env, held)
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
    visited: set = set()
    stack = [value]
    while stack:
        v = stack.pop()
        if id(v) in visited:
            continue
        visited.add(id(v))
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
