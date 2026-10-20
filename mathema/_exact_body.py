# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function body read exactly: the mathematics the code states.

A function run on exact inputs (`_exact_side.wrap` with `exact_calls`)
gives an exact result only while every step of its body keeps the
value exact, and the body as Python runs it does not: a float literal
is a double, `int / int` is a double, `math.sqrt` returns a double.
This module builds the function's exact twin, the same body with those
steps read as mathematics:

- a numeric literal is the number written, `0.5` is 1/2 and `2e-9` is
  2/10^9, the reading derive gives the literals of a claim;
- `/` of two exact numbers is their ratio, `**` with a whole exponent
  is exact and with a fractional exponent an exact sympy power;
- `float()` is the identity on an exact number, `math.fabs` its
  absolute value;
- `math.sqrt`, `math.exp`, `math.log`, the trigonometric and
  hyperbolic functions and `math.pi`, `math.e`, `math.tau` give exact
  sympy values when their arguments are exact, a value the claim's
  comparison then settles symbolically (`_exact_side.decide_symbolic`).

Everything else runs as written. A float the body reads from outside
(a module global, a closure, a value a library returns) is a double
with no exact reading, and the twin's result is then inexact at that
point, as `wrap` reports it. `abs`, `sum`, `min` and `max` are exact
on rationals as Python defines them and are left alone.

No decision is taken on a number standing for a float. The twin holds
an exact number where the computation held a rounded float, and a
decision on it can go the other way: a loop adding 0.1 until it
reaches 1 runs ten times exactly and eleven times in float. So a
comparison (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `is`,
`is not`) with such a number among its operands or inside one, its use
as a subscript or as a key of a dict or set (a display, `dict.get`,
`set.add`, `set()`, `dict()`, `hash`), the test of an `if`, `while`,
conditional expression, comprehension condition, `and`, `or`, `not`,
`bool`, `any`, `all` or `filter` on it, a `key=` of `sorted`, `min`,
`max` or `list.sort` returning it, a search of a list holding it
(`index`, `count`, `remove`), and `math.floor`, `math.ceil`,
`math.trunc`, `int()`, `round`, `divmod`, `//` and `%` of it, each
makes the point undecided (`NotExact`). Inside the body of a `try`
whose handlers catch an arithmetic or math domain error (a bare
`except`, `except Exception`, `except OverflowError`, ...), or of a
`with` statement, so does any division, power, `float()` or `math`
function of such a number, which could raise in the computation where
the exact step does not (`10.0 ** 400` overflows); the same step on
integers runs as the computation runs it first, raising the
computation's own error. The same decisions on integers are taken as
written: they are the computation's own (`n % d == 0`, a `range`
loop). Identity against `None`, `True`, `False` or `...` is no
decision on the number and is taken too. An `assert`'s test is left as
written: the assert raises or not, and a raise leaves the point
undecided. Comparisons and the other decisions on a number standing
for a float are declined for now, whether or not the float and the
exact number would decide alike.

Every call the body makes is read too, so no function written in
Python runs as written on an exact number. A Python function the body
calls (by name, through a module, from a container, or handed to a
builtin such as `map` or `sorted`) runs as its own exact twin: its
source scanned with the same refusals, its body rewritten, its globals
read the same way, built once and used however deep the calls go up to
`_MAX_DEPTH` nested calls. A callee with no faithful twin makes the
point undecided (`NotExact`): a function with no source, a lambda
defined outside the body, a decorated function, a library function
(the standard library's, or one installed in site-packages), a method
on an object, a class other than a builtin or an exception, or any
other callable object. A builtin runs as itself, as does a function a
compiled module provides when no exact number is among its arguments;
with one among them the point is undecided. A body that catches the
`NotExact` of a step it took (`except Exception:`) does not hide it:
the run that caught it is undecided all the same.

A value the computation holds as a float is held by the twin as a
Fraction or a sympy number, never a bare int: `float(3)` is
`Fraction(3)`, `math.sqrt(4)` is `Fraction(2)`, `4 ** 0.5` and
`2 ** 3.0` are Fractions, while an int the body or the claim wrote
stays an int. A question about a number's type is then answered as
the computation would: `isinstance(x, float)`, `type(x)`,
`x.__class__` and `type(x) is float` say `float` of such a value and
`int` of an int, so a body branching on the type takes the branch the
computation took.

The reading is only used on a body it follows faithfully. An exact
number stands in for a float, so a construct whose value depends on
the number's Python type or its text rather than its mathematics
would send the exact run down a path the computation did not take,
and a body holding one is refused on its syntax tree before it runs
(`unfaithful`; `exact_callee` then raises `NotExact`, the point
undecided). Refused: a comparison (`is`, `is not`, `==`, `in`, ...)
against a type reached by any path other than its bare builtin name
(`builtins.float`, a module alias of `float`, an imported class: the
twin cannot tell the real `float` from its exact one), `str`/`repr`/
`format`/`ascii`/`bin`/`hex`/`oct`/`id` calls, f-strings, `%`
formatting with a string, `.format(...)`,
`__str__`/`__repr__`/`__format__`, `.hex()`, `float.fromhex`,
`.as_integer_ratio()`, explicit `Fraction(...)` and `Decimal(...)`,
`isinstance`/`issubclass` against `Fraction`, `Decimal`,
`numbers.Rational` or a sympy class, `math.isclose`, `math.frexp`,
`math.ldexp`, `math.ulp`, `math.nextafter`, and any use of the
`struct` or `ctypes` modules, under any alias and whether imported at
module level or inside the body. Text turned back into a number
(`float(f"{x:.2f}")`, `float(str(x))`, `Decimal(str(x))`) is refused
with the text. An `import math` inside the body reaches the exact
`math` too. A body with no source to scan (built in, a lambda,
defined by `exec`) or a decorated function is refused the same way:
nothing vouches for it.

Text whose only reach is an exception's message is not refused: an
f-string, `"..." % x`, `"...".format(...)`, `str(...)` or `repr(...)`
written directly as an argument of the exception constructed by a
`raise` statement (`raise ValueError(f"negative: {x}")`, the callee
resolving to a class deriving from `BaseException`), or as the message
of an `assert`. The twin raises where the computation raises, with the
stand-in's own text in the message, and the message is never compared.
The text is refused as ever when it is wrapped in anything else on the
way to the exception (`raise ValueError("bad: " + f"{x}")`, `raise
make_error(f"{x}")`, `raise ValueError(float(f"{x:.2f}"))`), or when
the body holds a `try` or `with` statement, under which it could catch
its own exception and read the message back.
"""
from __future__ import annotations

import ast
import builtins
import copy
import functools
import inspect
import math
import sys
import textwrap
import threading
import types
import weakref
from fractions import Fraction
from typing import NoReturn

__all__ = ["NotExact", "exact_callee", "exact_twin", "unfaithful"]

#: the names the rewritten body calls for a literal, a division, a
#: floor division, a power and a `.__class__` read, spelled so no body
#: of its own uses them
_LITERAL, _DIV, _POW = "__mathema_literal__", "__mathema_div__", "__mathema_pow__"
_FLOORDIV, _CLASS = "__mathema_floordiv__", "__mathema_class__"
#: the name the rewritten body calls each callee through (`_callee`),
#: the name `NotExact` is bound to in the twin's globals, and the key
#: marking a dict as a twin's globals
_CALLEE, _NOT_EXACT = "__mathema_callee__", "__mathema_not_exact__"
_TWIN_MARK = "__mathema_twin__"
#: the names the rewritten body calls for a comparison's operand, a
#: test, a key, a remainder, and the guard around a body whose errors a
#: handler catches
_OPERAND, _TEST, _KEY = "__mathema_operand__", "__mathema_test__", "__mathema_key__"
_MEMBER = "__mathema_member__"
_MOD, _GUARD = "__mathema_mod__", "__mathema_guard__"

#: the most calls of other functions' twins nested inside one another
#: before the point is left undecided
_MAX_DEPTH = 64

#: each function's reading, built once: `(twin, None)`, or `(None,
#: reason)` for a body that cannot be read faithfully
_TWINS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class NotExact(Exception):
    """A step of the exact reading has no exact value: a floor or a
    rounding sympy cannot settle, a transcendental value that is not a
    finite number, a callee the reading cannot follow."""


class _State(threading.local):
    """The exact reading's state on this thread: `depth`, the calls of
    other functions' twins currently nested; `taint`, the reason of the
    first `NotExact` raised in the current run, kept even when the body
    catches the exception; `guard`, the handlers catching an arithmetic
    error (and `with` statements) the run is currently inside
    (`_Guard`)."""
    depth = 0
    guard = 0
    taint: "str | None" = None


_STATE = _State()


def _not_exact(reason: str) -> NoReturn:
    """Raise `NotExact` with `reason`, recording it as the run's taint
    so a body that catches it is still undecided."""
    if _STATE.taint is None:
        _STATE.taint = reason
    raise NotExact(reason)


def exact_twin(fn):
    """Intent:
        The exact twin of `fn`, a function of the same signature whose
        body is `fn`'s read exactly (the module docstring), or None when
        the body cannot be read faithfully: `fn` is not a plain Python
        function, has no source (built in, a lambda, defined by `exec`),
        is decorated or wraps another function, holds a construct the
        reading refuses (`unfaithful`), or its rewritten body does not
        compile. Built once per function.

    Notes:
        The twin's globals are a copy of `fn`'s with `float`, `round`
        and `pow` shadowed by their exact readings, the `math` module
        (and any of its functions imported by name) by exact versions,
        and `fn`'s own name bound to the twin, so a recursive call is
        read exactly too. A closure's cells are copied in as globals.
    """
    return _reading(fn)[0]


def exact_callee(fn):
    """Intent:
        `fn` as the exact reading runs it: its exact twin, or, when no
        faithful twin exists (`exact_twin` is None), a callable that
        raises `NotExact` with the reason, so a point read through it is
        undecided rather than read through a body the reading cannot
        vouch for. A run during which any step raised `NotExact` raises
        it, though the body caught it.
    """
    twin, reason = _reading(fn)
    if twin is None:
        def refused(*args, **kwargs):
            raise NotExact(reason)
        return refused

    @functools.wraps(twin)
    def run(*args, **kwargs):
        saved, _STATE.taint = _STATE.taint, None
        try:
            out = twin(*args, **kwargs)
        except NotExact:
            raise
        except Exception:
            if _STATE.taint is not None:
                raise NotExact(_STATE.taint) from None
            raise
        finally:
            taint = _STATE.taint
            _STATE.taint = saved if saved is not None else taint
        if taint is not None:
            raise NotExact(taint)
        return out
    return run


def unfaithful(fn) -> list:
    """Intent:
        The constructs in `fn`'s body the exact reading refuses (the
        module docstring), each as its source text with its line, in
        order; `[]` when there are none, or when the body has no source
        to scan.
    """
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return []
    parsed = _parse(fn)
    if parsed is None:
        return []
    src, node, _first = parsed
    return _Scan(src, fn).found_in(node)


def _reading(fn) -> tuple:
    """`(twin, None)`, or `(None, reason)`: the exact twin of `fn` or
    why there is none, cached per function."""
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return None, f"{getattr(fn, '__name__', fn)!s} is not a Python function"
    from .analysis import foreign_body
    if foreign_body(fn):
        return None, (f"{fn.__qualname__} stands for a function another "
                      f"frontend read, and its Python source is a wrapper's")
    try:
        return _TWINS[fn]
    except KeyError:
        pass
    reading = _build(fn)
    try:
        _TWINS[fn] = reading
    except TypeError:
        pass
    return reading


def _parse(fn):
    """`(src, FunctionDef, first line)` of `fn`'s source, dedented, or
    None when there is no source or it is not one plain `def`."""
    try:
        lines, first = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return None
    src = textwrap.dedent("".join(lines))
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return None
    return src, tree.body[0], first


def _plain(fn):
    """`fn` with mathema's own call adapters taken off (`_exits`'s exit
    adapter, a runtime type's realising adapter), each standing for the
    function it wraps; any other wrapper is left as it is."""
    from ._exits import _ExitsAsRaise
    from .runtime_types import _Realising
    while isinstance(fn, (_ExitsAsRaise, _Realising)):
        inner = getattr(fn, "__wrapped__", None)
        if inner is None:
            return fn
        fn = inner
    return fn


def _build(fn) -> tuple:
    """`(twin, None)`, or `(None, reason)` when `fn` has no faithful
    twin."""
    name = fn.__qualname__
    if getattr(fn, "__wrapped__", None) is not None:
        return None, f"{name} wraps another function"
    parsed = _parse(fn)
    if parsed is None:
        return None, f"the source of {name} cannot be read as one function"
    src, node, first = parsed
    if node.decorator_list:
        return None, f"{name} is decorated"
    if node.name != fn.__name__:
        return None, f"the source of {name} defines another name"
    found = _Scan(src, fn).found_in(node)
    if found:
        return None, (f"the body of {name} is not read exactly: {found[0]} "
                      f"depends on the number's Python type or text, not "
                      f"its mathematics")
    node = _Exact(src, fn.__globals__).visit(node)
    ast.fix_missing_locations(node)
    ast.increment_lineno(node, first - 1)
    module = ast.Module(body=[node], type_ignores=[])
    try:
        compiled = compile(module, fn.__code__.co_filename, "exec")
    except (SyntaxError, ValueError, TypeError):
        return None, f"the exact reading of {name} does not compile"
    env = _globals_of(fn)
    if env is None:
        return None, f"a closure cell of {name} is empty"
    try:
        exec(compiled, env)
    except Exception:
        return None, f"the exact reading of {name} does not define"
    twin = env.get(node.name)
    if not isinstance(twin, types.FunctionType):
        return None, f"the exact reading of {name} does not define"
    if fn.__globals__.get(fn.__name__) is not fn:
        # the def bound its name in the copy; the body reads that name
        # as the module does
        if fn.__name__ in fn.__globals__:
            env[fn.__name__] = fn.__globals__[fn.__name__]
        else:
            del env[fn.__name__]
    twin.__qualname__ = fn.__qualname__
    twin.__module__ = fn.__module__
    twin.__doc__ = fn.__doc__
    twin.__annotations__ = dict(getattr(fn, "__annotations__", {}) or {})
    return twin, None


# --- the constructs the reading refuses ---------------------------------

#: builtins whose value is a number's text or identity
_TEXT_CALLS = frozenset({"str", "repr", "format", "ascii", "bin", "hex",
                         "oct", "id"})
#: attributes whose value is a number's representation
_TEXT_ATTRS = frozenset({"hex", "fromhex", "as_integer_ratio", "format",
                         "__str__", "__repr__", "__format__"})
_MISSING = object()
#: the statements under which a body could catch an exception it raised
#: itself and read its message back
_CATCHING: tuple = (ast.Try, getattr(ast, "TryStar", ast.Try), ast.With,
                    ast.AsyncWith)


def _refused_callables() -> frozenset:
    """The ids of the callables (and classes) whose value depends on the
    float representation, or that build an exact number the computation
    never had."""
    import decimal
    import numbers
    values = [Fraction, decimal.Decimal, numbers.Rational, math.isclose,
              math.frexp, math.ldexp, math.nextafter, float.fromhex,
              float.hex, float.as_integer_ratio]
    if hasattr(math, "ulp"):
        values.append(math.ulp)
    return frozenset(id(v) for v in values)


def _refused_modules() -> frozenset:
    """The ids of the modules that read a float's bits."""
    import ctypes
    import struct
    return frozenset(id(m) for m in (struct, ctypes))


class _Scan(ast.NodeVisitor):
    """The walk over a body that finds the constructs the reading
    refuses, resolving names through the function's globals and the
    builtins so an alias (`from fractions import Fraction as Q`,
    `import struct as s`) is seen for what it is."""

    def __init__(self, src: str, fn):
        self.src = src
        self.env = fn.__globals__
        # what the body's own `import` statements bind, by name
        self.imported: dict = {}
        self.found: list = []
        self.callables = _refused_callables()
        self.modules = _refused_modules()
        # the ids of the text constructs whose only reach is an
        # exception's message (`_message_text`)
        self.message_text: set = set()
        # whether the body holds a `try` or `with` statement, under
        # which an exception it raises could be caught and its message
        # read back by the body itself
        self.catching = False

    def found_in(self, node) -> list:
        self.catching = any(isinstance(n, _CATCHING) for n in ast.walk(node))
        self.visit(node)
        return self.found

    def _refuse(self, node) -> None:
        text = ast.get_source_segment(self.src, node) or type(node).__name__
        self.found.append(f"`{text}` (line {getattr(node, 'lineno', '?')})")

    def visit_Import(self, node):
        import importlib
        for alias in node.names:
            try:
                module = importlib.import_module(alias.name.split(".")[0])
            except Exception:
                continue
            self.imported[alias.asname or alias.name.split(".")[0]] = module

    def visit_ImportFrom(self, node):
        import importlib
        if node.level or not node.module:
            return
        try:
            module = importlib.import_module(node.module)
        except Exception:
            return
        for alias in node.names:
            value = getattr(module, alias.name, _MISSING)
            if value is not _MISSING:
                self.imported[alias.asname or alias.name] = value

    def _resolve(self, node):
        if isinstance(node, ast.Name):
            value = self.imported.get(node.id, _MISSING)
            if value is _MISSING:
                value = self.env.get(node.id, _MISSING)
            if value is _MISSING:
                value = getattr(builtins, node.id, _MISSING)
            return value
        if isinstance(node, ast.Attribute):
            base = self._resolve(node.value)
            if base is _MISSING or not isinstance(base, (types.ModuleType, type)):
                return _MISSING
            return getattr(base, node.attr, _MISSING)
        return _MISSING

    def _is_type(self, node) -> bool:
        value = self._resolve(node)
        return value is not _MISSING and isinstance(value, type)

    def _type_nodes(self, node):
        """The nodes of a comparison's side that name a type, looking
        into a tuple, list or set written out (`(float, int)`)."""
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.elts:
                yield from self._type_nodes(elt)
        elif self._is_type(node):
            yield node

    def _builtin_type_name(self, node) -> bool:
        """Whether `node` is the bare name of a builtin type, bound by
        neither the module nor the body: the twin reads `float` as its
        exact `float` and every other such name as the class itself, so
        a comparison against it is answered as the computation's."""
        return (isinstance(node, ast.Name)
                and node.id not in self.imported and node.id not in self.env
                and isinstance(getattr(builtins, node.id, None), type))

    def _refused_class(self, node) -> bool:
        value = self._resolve(node)
        if value is _MISSING or not isinstance(value, type):
            return False
        if id(value) in self.callables:
            return True
        return any((getattr(c, "__module__", "") or "").split(".")[0] == "sympy"
                   for c in value.__mro__)

    def _is_text(self, node) -> bool:
        """Whether `node` is a text construct of the kinds an exception
        message may hold: an f-string, `"..." % x`, `"...".format(...)`,
        `str(...)` or `repr(...)` (the builtins, under their own
        names)."""
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.BinOp):
            return (isinstance(node.op, ast.Mod)
                    and isinstance(node.left, ast.Constant)
                    and isinstance(node.left.value, str))
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                return (func.attr == "format"
                        and isinstance(func.value, ast.Constant)
                        and isinstance(func.value.value, str))
            if isinstance(func, ast.Name):
                return self._resolve(func) in (str, repr)
        return False

    def _message_text(self, call) -> None:
        """Mark the text constructs among the arguments of `call`, the
        constructor of an exception about to be raised, as reaching
        nothing but that exception's message, so the walk does not
        refuse them. `call` must resolve to a class deriving from
        `BaseException`; a call of anything else, or any text in a body
        that could catch its own exception (`catching`), is left to the
        walk and refused as ever."""
        if self.catching or not isinstance(call, ast.Call):
            return
        cls = self._resolve(call.func)
        if cls is _MISSING or not isinstance(cls, type) \
                or not issubclass(cls, BaseException):
            return
        for arg in (*call.args, *(kw.value for kw in call.keywords)):
            if self._is_text(arg):
                self.message_text.add(id(arg))
                if isinstance(arg, ast.Call):
                    self.message_text.add(id(arg.func))

    def visit_Raise(self, node):
        # `raise E(...)`: text in the arguments becomes the message of
        # the exception raised, which the body never reads back
        if node.exc is not None:
            self._message_text(node.exc)
        self.generic_visit(node)

    def visit_Assert(self, node):
        # `assert test, msg`: the message is read only when the assert
        # fails, as the message of the AssertionError raised
        if node.msg is not None and not self.catching \
                and self._is_text(node.msg):
            self.message_text.add(id(node.msg))
            if isinstance(node.msg, ast.Call):
                self.message_text.add(id(node.msg.func))
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if id(node) in self.message_text:
            pass
        elif isinstance(func, ast.Name) and func.id in _TEXT_CALLS:
            self._refuse(node)
        elif isinstance(func, ast.Attribute) and func.attr in _TEXT_ATTRS:
            self._refuse(node)
        elif id(self._resolve(func)) in self.callables:
            self._refuse(node)
        elif isinstance(func, ast.Name) \
                and func.id in ("isinstance", "issubclass") \
                and len(node.args) == 2:
            classes = (node.args[1].elts if isinstance(node.args[1], ast.Tuple)
                       else [node.args[1]])
            if any(self._refused_class(c) for c in classes):
                self._refuse(node)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if id(node) in self.message_text:
            pass
        elif node.attr in _TEXT_ATTRS and isinstance(node.ctx, ast.Load):
            self._refuse(node)
        elif id(self._resolve(node.value)) in self.modules:
            self._refuse(node)
        self.generic_visit(node)

    def visit_Compare(self, node):
        # a type compared by identity is answered only under its bare
        # builtin name; compared by equality or membership, only the
        # real `float` reached another way is indistinguishable from the
        # twin's exact `float`
        identity = any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops)
        for side in (node.left, *node.comparators):
            for typed in self._type_nodes(side):
                if self._builtin_type_name(typed):
                    continue
                if identity or self._resolve(typed) is float:
                    self._refuse(node)
                    break
            else:
                continue
            break
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        if id(node) in self.message_text:
            # the values formatted are still scanned
            self.generic_visit(node)
            return
        self._refuse(node)

    def visit_BinOp(self, node):
        if id(node) in self.message_text:
            pass
        elif isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, (str, bytes)):
            self._refuse(node)
        self.generic_visit(node)


def _globals_of(fn) -> "dict | None":
    """Intent:
        The twin's globals: `fn`'s, copied, with the exact readings in
        place of `float`, `round`, `pow`, the `math` module and any of
        its functions bound by name, the helper names the rewritten
        body calls, the cells of `fn`'s closure as globals, and the
        mark (`_TWIN_MARK`) by which a function the twin defines is
        known to be read already. None when a closure cell is empty.
    """
    env = dict(fn.__globals__)
    env["__builtins__"] = {**builtins.__dict__, "float": ExactFloat,
                           "round": _round, "pow": _pow, "type": _type,
                           "divmod": _divmod, "__import__": _import}
    for name, value in list(env.items()):
        if name == "__builtins__":
            continue
        exact = _exact_global(value)
        if exact is not None:
            env[name] = exact
    freevars = fn.__code__.co_freevars
    if freevars:
        try:
            cells = {name: cell.cell_contents
                     for name, cell in zip(freevars, fn.__closure__ or ())}
        except ValueError:
            return None
        for name, value in cells.items():
            exact = _exact_global(value)
            env[name] = value if exact is None else exact
    env[_LITERAL] = _literal
    env[_DIV] = _div
    env[_FLOORDIV] = _floordiv
    env[_POW] = _pow
    env[_CLASS] = _class
    env[_CALLEE] = _callee
    env[_NOT_EXACT] = NotExact
    env[_OPERAND] = _operand
    env[_MEMBER] = _member
    env[_TEST] = _test
    env[_KEY] = _key
    env[_MOD] = _mod
    env[_GUARD] = _Guard
    env[_TWIN_MARK] = True
    return env


# --- the calls the twin's body makes -----------------------------------

#: the C callable types a module or a builtin type provides, run as
#: themselves when no exact number is among their arguments
_C_CALLABLES: tuple = (types.BuiltinFunctionType, types.MethodDescriptorType,
                       types.WrapperDescriptorType, types.MethodWrapperType,
                       types.ClassMethodDescriptorType)

#: the builtin values whose own methods run as themselves (a string's
#: `.format`, a list's `.append`, a dict's `.get`)
_BUILTIN_VALUES: tuple = (str, bytes, bytearray, int, list, tuple, dict, set,
                          frozenset)

#: each Python function's call as the twin makes it, built once
_HELPERS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _own(func) -> bool:
    """A reading this module provides (`ExactFloat`, `_round`, an exact
    `math` function), called as it is."""
    return getattr(func, "__module__", None) == __name__


def _library(fn) -> bool:
    """Intent:
        Whether the Python function `fn` belongs to a library rather
        than the code under test: a module of the standard library, or
        a file installed under `site-packages` or `dist-packages`.
    """
    module = (getattr(fn, "__module__", None) or "").split(".")[0]
    if module in getattr(sys, "stdlib_module_names", ()):
        return True
    path = getattr(getattr(fn, "__code__", None), "co_filename", "") or ""
    parts = path.replace("\\", "/").split("/")
    return "site-packages" in parts or "dist-packages" in parts


def _refuser(reason: str):
    """A callable that leaves the point undecided with `reason`."""
    def refused(*args, **kwargs):
        _not_exact(reason)
    return refused


def _named(func) -> str:
    return getattr(func, "__qualname__", None) or getattr(
        func, "__name__", None) or type(func).__name__


def _holds_stand_in(value, depth: int = 0) -> bool:
    """Intent:
        Whether `value` is, or holds, an exact number standing where
        the computation had a float (`_stands_for_float`): itself, or
        an element of a list, tuple, set or frozenset, a key or value
        of a dict, or an element of an object array, looked into up to
        six levels deep; a container nested deeper counts as holding
        one.
    """
    if _stands_for_float(value):
        return True
    if depth >= 6:
        return isinstance(value, (list, tuple, set, frozenset, dict))
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_holds_stand_in(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return any(_holds_stand_in(k, depth + 1)
                   or _holds_stand_in(v, depth + 1)
                   for k, v in value.items())
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray) \
            and value.dtype == object:
        return any(_holds_stand_in(v, depth + 1) for v in value.ravel())
    return False


def _read_args(args: tuple, kwargs: dict) -> tuple:
    """The arguments of a call the twin makes to a callable it does not
    read: each Python function among them (a callback, `map`'s
    function, `sorted`'s key) as the twin calls it (`_callee`)."""
    def read(v):
        return _callee(v) if isinstance(v, types.FunctionType) else v
    return (tuple(read(a) for a in args),
            {k: read(v) for k, v in kwargs.items()})


def _helper(fn):
    """Intent:
        A Python function the twin's body calls, as the twin calls it:
        its own exact twin, counted against `_MAX_DEPTH`, or a refuser
        when it has no faithful twin. Built once per function.
    """
    try:
        return _HELPERS[fn]
    except (KeyError, TypeError):
        pass
    twin, reason = _reading(fn)
    if twin is None:
        call = _refuser(reason or f"{_named(fn)} is not read exactly")
    else:
        def call(*args, **kwargs):
            if _STATE.depth >= _MAX_DEPTH:
                _not_exact(f"the calls nest deeper than {_MAX_DEPTH}")
            _STATE.depth += 1
            try:
                return twin(*args, **kwargs)
            finally:
                _STATE.depth -= 1
    try:
        _HELPERS[fn] = call
    except TypeError:
        pass
    return call


def _opaque(func):
    """A callable the reading does not look into, run as itself when no
    exact number standing for a float is among its arguments, else
    leaving the point undecided."""
    def call(*args, **kwargs):
        if _holds_stand_in(args) or _holds_stand_in(kwargs):
            _not_exact(f"{_named(func)} is called on an exact number it "
                       f"does not read exactly")
        args, kwargs = _read_args(args, kwargs)
        return func(*args, **kwargs)
    return call


def _operand(value):
    """An operand of a comparison (`==`, `<`, `in`, `is`, ...), as it
    is.

    Raises:
        NotExact: the operand is, or holds, a number standing for a
            float (`_holds_stand_in`): the comparison could go the
            other way from the computation's.
    """
    if _holds_stand_in(value):
        _not_exact(f"a comparison on {value}, which stands for a float, "
                   f"is not taken exactly")
    return value


def _member(container):
    """The container of `in` or `not in`, as it is: of a dict or a dict's
    view its keys or elements are compared, of a list, tuple, set or
    array its elements (`_operand`), of a string or a range nothing
    standing for a float.

    Raises:
        NotExact: the container holds a number standing for a float, or
            is one whose elements cannot be looked at without consuming
            them (an iterator, a generator, an object of another kind).
    """
    import collections.abc as abc
    np = sys.modules.get("numpy")
    if isinstance(container, (str, bytes, bytearray, range)):
        return container
    if isinstance(container, dict):
        _operand(list(container))
    elif isinstance(container, (abc.KeysView, abc.ValuesView,
                                abc.ItemsView)):
        _operand(list(container))
    elif isinstance(container, (list, tuple, set, frozenset)) or (
            np is not None and isinstance(container, np.ndarray)):
        _operand(container)
    else:
        _not_exact(f"the elements of {type(container).__name__} cannot be "
                   f"looked at before a membership test")
    return container


def _test(value):
    """The value an `if`, `while`, conditional expression, condition of
    a comprehension, `and`, `or` or `not` tests, as it is.

    Raises:
        NotExact: the value is a number standing for a float, or an
            array holding one: its truth is a comparison with zero.
    """
    np = sys.modules.get("numpy")
    if _stands_for_float(value) or (
            np is not None and isinstance(value, np.ndarray)
            and _holds_stand_in(value)):
        _not_exact(f"a test of {value}, which stands for a float, is not "
                   f"taken exactly")
    return value


def _key(value):
    """A subscript, or a key of a dict or set, as it is.

    Raises:
        NotExact: the key is, or holds, a number standing for a float:
            its hash and equality are decisions on it.
    """
    if _holds_stand_in(value):
        _not_exact(f"{value}, which stands for a float, is not used as a "
                   f"key exactly")
    return value


class _Guard:
    """The body of a `try` whose handlers catch an arithmetic error, or
    of a `with` statement: inside it a step on a number standing for a
    float, which could raise in the computation (an overflow, a
    division by a float rounded to zero) where the exact step does not,
    leaves the point undecided (`_guarded_native`)."""

    def __enter__(self):
        _STATE.guard += 1
        return self

    def __exit__(self, *exc):
        _STATE.guard -= 1
        return False


def _keyed_by(key):
    """A `key=` of `sorted`, `min`, `max` or `list.sort`, read exactly,
    whose results are compared: each is an operand (`_operand`)."""
    key = _callee(key) if isinstance(key, types.FunctionType) else key

    def keyed(value):
        return _operand(key(value))
    return keyed


def _truths(func):
    """`any` or `all`, testing each element (`_test`)."""
    def call(iterable):
        return func(_test(v) for v in iterable)
    return call


def _filter(function, iterable):
    """`filter`, testing each value its function returns (`_test`)."""
    if function is None:
        return filter(_test, iterable)
    function = _callee(function)
    return filter(lambda v: _test(function(v)), iterable)


def _keyed_result(func):
    """`set`, `frozenset` or `dict`, its keys checked (`_key`)."""
    def call(*args, **kwargs):
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        _key(list(out))
        return out
    return call


def _int(*args, **kwargs):
    """`int`, declining a number standing for a float (a truncation)."""
    if args:
        _decline(args[0])
    return int(*args, **kwargs)


def _bool(*args):
    """`bool`, declining a number standing for a float (a test)."""
    return bool(*(_test(a) for a in args))


def _hash(value):
    """`hash`, declining a value holding a number standing for a
    float."""
    return hash(_key(value))


#: the builtins whose decisions on a number standing for a float are
#: declined, as the twin calls them
_DECIDING: dict = {id(int): _int, id(bool): _bool, id(hash): _hash,
                   id(any): _truths(any), id(all): _truths(all),
                   id(filter): _filter, id(set): _keyed_result(set),
                   id(frozenset): _keyed_result(frozenset),
                   id(dict): _keyed_result(dict)}
#: the builtins comparing their elements by a `key=`
_KEYED = frozenset(id(f) for f in (sorted, min, max))


def _builtin(func):
    """A builtin, run as itself with any Python function among its
    arguments read exactly, its decisions on a number standing for a
    float declined (`_DECIDING`, a `key=` of `sorted`, `min` or
    `max`)."""
    deciding = _DECIDING.get(id(func))
    if deciding is not None:
        return deciding
    keyed = id(func) in _KEYED

    def call(*args, **kwargs):
        if keyed:
            # the elements compared, gathered once: a number standing
            # for a float may be compared by value, whose order is the
            # mathematics, but not inside a tuple or list, whose order
            # then decides what else comes first
            items = list(args[0]) if len(args) == 1 else list(args)
            _unordered_inside(items)
            args = (items,) if len(args) == 1 else tuple(items)
            if kwargs.get("key") is not None:
                kwargs = {**kwargs, "key": _keyed_by(kwargs["key"])}
        args, kwargs = _read_args(args, kwargs)
        return func(*args, **kwargs)
    return call


def _unordered_inside(items) -> None:
    """Leave the point undecided when an element of `items` compared by
    `sorted`, `min`, `max` or `list.sort` is a container holding a
    number standing for a float."""
    for item in items:
        if not _stands_for_float(item) and _holds_stand_in(item):
            _not_exact("an ordering of containers holding a number "
                       "standing for a float is not taken exactly")


#: the methods of a dict or set whose first argument is a key, and
#: those that may add keys
_KEY_METHODS = frozenset({"get", "pop", "setdefault", "__contains__",
                          "__getitem__", "__delitem__", "__setitem__",
                          "add", "discard", "remove"})
_KEY_ADDING = frozenset({"update", "setdefault", "__setitem__", "add",
                         "__ior__", "__or__", "union", "intersection",
                         "difference", "symmetric_difference",
                         "intersection_update", "difference_update",
                         "symmetric_difference_update", "copy"})
#: the methods of a list or tuple comparing its elements
_SEARCHING = frozenset({"index", "count", "remove", "__contains__"})


def _method(func):
    """A builtin value's own method (`_BUILTIN_VALUES`), run as itself
    with its decisions on a number standing for a float declined: a key
    of a dict or set, a search of a list, a `key=` of `list.sort`."""
    owner = func.__self__
    name = func.__name__
    keyed = isinstance(owner, (dict, set, frozenset))
    searched = isinstance(owner, (list, tuple)) and name in _SEARCHING

    def call(*args, **kwargs):
        if keyed and name in _KEY_METHODS and args:
            _key(args[0])
        if searched:
            _operand(args)
            _operand(owner)
        if name == "sort":
            _unordered_inside(owner)
            if kwargs.get("key") is not None:
                kwargs = {**kwargs, "key": _keyed_by(kwargs["key"])}
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        if keyed and name in _KEY_ADDING:
            _key(list(owner))
            if isinstance(out, (dict, set, frozenset)):
                _key(list(out))
        return out
    return call


def _callee(func):
    """Intent:
        `func` as the twin's body calls it: a reading of this module as
        itself, a `math` function as its exact version, a function the
        twin defined as itself (its code is already the reading), any
        other Python function as its exact twin (`_helper`), a builtin
        or a builtin class as itself (`_builtin`), a C function of a
        module and an exception class as themselves while no exact
        number is among their arguments (`_opaque`). A library
        function, a bound method, any other class or callable object
        leaves the point undecided when called.
    """
    if _own(func):
        return func
    try:
        exact = _MATH_FUNCTIONS.get(id(func))
    except TypeError:
        exact = None
    if exact is not None and _MATH_NATIVE.get(id(func)) is func:
        return exact
    name = _named(func)
    if isinstance(func, types.FunctionType):
        if func.__globals__.get(_TWIN_MARK) is True:
            return func
        if _library(func):
            return _refuser(f"{name} is a library function the reading "
                            f"does not follow")
        return _helper(func)
    if isinstance(func, types.MethodType):
        return _refuser(f"{name} is a method on an object the reading "
                        f"does not follow")
    if isinstance(func, type):
        if func.__module__ == "builtins":
            return _builtin(func)
        if issubclass(func, BaseException):
            return _opaque(func)
        return _refuser(f"{name} is a class the reading does not follow")
    if isinstance(func, types.BuiltinFunctionType) \
            and getattr(func, "__self__", None) is builtins:
        return _builtin(func)
    if isinstance(func, _C_CALLABLES):
        owner = getattr(func, "__self__", None)
        if _stands_for_float(owner):
            return _refuser(f"{name} is a method of an exact number")
        if isinstance(owner, _BUILTIN_VALUES):
            return _method(func)
        return _opaque(func)
    return _refuser(f"{name} is a callable object the reading does not "
                    f"follow")


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    """`__import__` as the twin's body sees it: an `import math` (or
    `from math import sqrt`) inside the body reaches the exact `math`
    the globals already hold, every other module itself."""
    module = builtins.__import__(name, globals, locals, fromlist, level)
    return _MATH if module is math else module


def _exact_global(value):
    """The exact reading of a global: the `math` module as `_ExactMath`,
    one of its functions as its exact version; None for anything else."""
    if value is math:
        return _MATH
    try:
        return _MATH_FUNCTIONS.get(id(value)) if callable(value) else None
    except TypeError:
        return None


class _Exact(ast.NodeTransformer):
    """The rewrite: each float literal a call reading its source text,
    each `/`, `//` and `**` (and `/=`, `//=`, `**=`) a call of the exact
    operator, each `.__class__` read a call answering the type as the
    computation would, each call made through `_callee`, each `try`
    letting a `NotExact` through its handlers, annotations dropped so
    they are not evaluated in the twin. Each decision is made through a
    check declining a number standing for a float: a comparison's
    operands (`_operand`, the container of `in` by `_member`, and none
    for `is` against `None`, `True`, `False` or `...`), the value an
    `if`, `while`, conditional expression,
    comprehension condition, `and`, `or` or `not` tests (`_test`), a
    subscript or a key of a dict or set display (`_key`), `%` (`_mod`),
    and the body of a `try` whose handlers catch an arithmetic error,
    or of a `with` statement (`_Guard`). An `assert`'s test is left as
    written: it raises or not, and a raise leaves the point undecided."""

    def __init__(self, src: str, env: "dict | None" = None):
        self.src = src
        self.env = env or {}
        # inside an assert's test, whose decisions are left as written
        self.asserting = False

    def _wrap(self, name: str, node):
        return ast.copy_location(ast.Call(
            func=ast.Name(name, ast.Load()), args=[node], keywords=[]), node)

    def _decides(self) -> bool:
        return not self.asserting

    def visit_Assert(self, node):
        self.asserting = True
        node.test = self.visit(node.test)
        self.asserting = False
        if node.msg is not None:
            node.msg = self.visit(node.msg)
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if not self._decides():
            return node
        sides = [node.left, *node.comparators]

        def singleton(n) -> bool:
            return isinstance(n, ast.Constant) and (
                n.value is None or n.value is True or n.value is False
                or n.value is Ellipsis)

        def identity_only(i: int) -> bool:
            # every operator beside operand i is `is`/`is not` against
            # a singleton constant
            pairs = []
            if i > 0:
                pairs.append((node.ops[i - 1], sides[i - 1]))
            if i < len(node.ops):
                pairs.append((node.ops[i], sides[i + 1]))
            return all(isinstance(op, (ast.Is, ast.IsNot)) and singleton(o)
                       for op, o in pairs)
        def container_only(i: int) -> bool:
            # operand i is only ever the container of `in`/`not in`
            return i > 0 and isinstance(node.ops[i - 1], (ast.In, ast.NotIn)) \
                and i == len(node.ops)

        wrapped = [s if singleton(s) or identity_only(i)
                   else self._wrap(_MEMBER, s) if container_only(i)
                   else self._wrap(_OPERAND, s)
                   for i, s in enumerate(sides)]
        node.left, node.comparators = wrapped[0], wrapped[1:]
        return node

    def _tested(self, node):
        return self._wrap(_TEST, node) if self._decides() else node

    def visit_If(self, node):
        self.generic_visit(node)
        node.test = self._tested(node.test)
        return node

    visit_While = visit_If
    visit_IfExp = visit_If

    def visit_comprehension(self, node):
        self.generic_visit(node)
        node.ifs = [self._tested(t) for t in node.ifs]
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        node.values = [*(self._tested(v) for v in node.values[:-1]),
                       node.values[-1]]
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            node.operand = self._tested(node.operand)
        return node

    def _keyed(self, node):
        return self._wrap(_KEY, node) if self._decides() else node

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if isinstance(node.slice, ast.Slice):
            for part in ("lower", "upper", "step"):
                value = getattr(node.slice, part)
                if value is not None:
                    setattr(node.slice, part, self._keyed(value))
        else:
            node.slice = self._keyed(node.slice)
        return node

    def visit_Dict(self, node):
        self.generic_visit(node)
        node.keys = [k if k is None else self._keyed(k) for k in node.keys]
        return node

    def visit_Set(self, node):
        self.generic_visit(node)
        node.elts = [self._keyed(e) for e in node.elts]
        return node

    def visit_DictComp(self, node):
        self.generic_visit(node)
        node.key = self._keyed(node.key)
        return node

    def visit_SetComp(self, node):
        self.generic_visit(node)
        node.elt = self._keyed(node.elt)
        return node

    def visit_Match(self, node):
        self.generic_visit(node)
        node.subject = self._wrap(_OPERAND, node.subject)
        return node

    def _guarded(self, body: list, at) -> list:
        return [ast.copy_location(ast.With(
            items=[ast.withitem(context_expr=ast.Call(
                func=ast.Name(_GUARD, ast.Load()), args=[], keywords=[]),
                optional_vars=None)],
            body=body), at)]

    def _catches_arithmetic(self, handler) -> bool:
        """Whether `handler` could catch an arithmetic error or a math
        domain error: a bare `except`, a class those errors derive from,
        or a name the walk cannot resolve."""
        if handler.type is None:
            return True
        kinds = (handler.type.elts if isinstance(handler.type, ast.Tuple)
                 else [handler.type])
        for kind in kinds:
            cls = _resolve_in(kind, self.env)
            if not isinstance(cls, type):
                return True
            if any(issubclass(e, cls) for e in _ARITHMETIC_ERRORS):
                return True
        return False

    def visit_With(self, node):
        self.generic_visit(node)
        node.body = self._guarded(node.body, node)
        return node

    visit_AsyncWith = visit_With

    def visit_Call(self, node):
        self.generic_visit(node)
        node.func = ast.copy_location(ast.Call(
            func=ast.Name(_CALLEE, ast.Load()), args=[node.func],
            keywords=[]), node.func)
        return node

    def visit_Try(self, node):
        self.generic_visit(node)
        if any(self._catches_arithmetic(h) for h in node.handlers):
            node.body = self._guarded(node.body, node)
        # `except NotExact: raise` ahead of the body's own handlers
        node.handlers.insert(0, ast.copy_location(ast.ExceptHandler(
            type=ast.Name(_NOT_EXACT, ast.Load()), name=None,
            body=[ast.Raise(exc=None, cause=None)]), node))
        return node

    visit_TryStar = visit_Try

    def visit_Constant(self, node):
        value = node.value
        if isinstance(value, float) and math.isfinite(value):
            text = ast.get_source_segment(self.src, node) or repr(value)
            return ast.copy_location(ast.Call(
                func=ast.Name(_LITERAL, ast.Load()),
                args=[ast.Constant(text)], keywords=[]), node)
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        name = _operator_name(node.op)
        if name is None:
            return node
        return ast.copy_location(ast.Call(
            func=ast.Name(name, ast.Load()),
            args=[node.left, node.right], keywords=[]), node)

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        name = _operator_name(node.op)
        if name is None:
            return node
        read = copy.deepcopy(node.target)
        read.ctx = ast.Load()
        call = ast.Call(func=ast.Name(name, ast.Load()),
                        args=[read, node.value], keywords=[])
        return ast.copy_location(
            ast.Assign(targets=[node.target], value=call), node)

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if node.attr != "__class__" or not isinstance(node.ctx, ast.Load):
            return node
        return ast.copy_location(ast.Call(
            func=ast.Name(_CLASS, ast.Load()),
            args=[node.value], keywords=[]), node)

    def visit_arg(self, node):
        node.annotation = None
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.returns = None
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


#: the errors a float step raises where its exact step may not (or the
#: other way): an overflow, a division by a float rounded to zero, a
#: math domain error
_ARITHMETIC_ERRORS = (OverflowError, ZeroDivisionError, FloatingPointError,
                      ValueError)


def _resolve_in(node, env: dict):
    """The value an exception name in a handler refers to, through
    `env` and the builtins (a dotted name through its module), or None
    when it cannot be resolved."""
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        return getattr(builtins, node.id, None)
    if isinstance(node, ast.Attribute):
        base = _resolve_in(node.value, env)
        return None if base is None else getattr(base, node.attr, None)
    return None


def _operator_name(op) -> "str | None":
    if isinstance(op, ast.Div):
        return _DIV
    if isinstance(op, ast.FloorDiv):
        return _FLOORDIV
    if isinstance(op, ast.Pow):
        return _POW
    if isinstance(op, ast.Mod):
        return _MOD
    return None


# --- the exact readings the twin's body calls --------------------------

def _sympy():
    import sympy
    return sympy


def _is_rational(value) -> bool:
    """An int (a bool included, as Python's arithmetic reads it) or a
    Fraction."""
    return isinstance(value, (int, Fraction))


def _is_symbolic(value) -> bool:
    """A sympy expression, when sympy has been imported at all (no value
    is one otherwise)."""
    sympy = sys.modules.get("sympy")
    return sympy is not None and isinstance(value, sympy.Basic)


def _symbolic_number(value) -> bool:
    """A sympy expression that is a finite number holding no float."""
    from ._exact_side import symbolic_number
    return symbolic_number(value)


def _exact(value) -> bool:
    return _is_rational(value) or _symbolic_number(value)


def _sympify(value):
    """An exact number as a sympy number."""
    sympy = _sympy()
    if _is_symbolic(value):
        return value
    q = Fraction(int(value) if isinstance(value, bool) else value)
    return sympy.Rational(q.numerator, q.denominator)


def _settled(value):
    """A sympy result of a step the computation returns a float from (a
    root, a power, a transcendental value) as the reading keeps it: a
    Rational, an Integer included, as a Fraction, any other finite
    number as itself.

    Raises:
        NotExact: the result is not a finite number, or holds a float.
    """
    if not _symbolic_number(value):
        _not_exact(f"{value} has no exact value")
    if value.is_Rational:
        return Fraction(int(value.p), int(value.q))
    return value


def _truth(relational) -> bool:
    """A sympy comparison of two numbers as a bool.

    Raises:
        NotExact: sympy left the comparison open.
    """
    sympy = _sympy()
    if relational is sympy.true or relational is True:
        return True
    if relational is sympy.false or relational is False:
        return False
    _not_exact(f"sympy cannot decide {relational}")


def _literal(text: str):
    """A numeric literal as written: an int, or the decimal as a
    Fraction (`0.1` is 1/10, `2e-9` is 2/10^9)."""
    text = text.replace("_", "")
    try:
        return int(text)
    except ValueError:
        return Fraction(text)


def _decline(*operands) -> None:
    """Leave the point undecided when any of `operands` stands for a
    float (`_stands_for_float`): the decision a step makes on it (a
    floor, a remainder, a rounding) could go the other way from the
    computation's, whose float was rounded."""
    for value in operands:
        if _stands_for_float(value):
            _not_exact(f"a decision on {value}, which stands for a float, "
                       f"is not taken exactly")


def _guarded_native(native, *operands) -> None:
    """Under a handler that catches an arithmetic error (`_Guard`): leave
    the point undecided when an operand stands for a float, and run the
    step on integer operands as the computation does, so it raises the
    computation's own error (an overflow) where the computation does."""
    if not _STATE.guard:
        return
    _decline(*operands)
    native(*operands)


def _div(a, b):
    """`a / b`: the ratio of two exact numbers, else Python's division."""
    _guarded_native(lambda x, y: x / y, a, b)
    if _is_rational(a) and _is_rational(b):
        return Fraction(a) / Fraction(b)
    if _exact(a) and _exact(b):
        divisor = _sympify(b)
        if divisor.is_zero:
            raise ZeroDivisionError("division by zero")
        return _settled(_sympify(a) / divisor)
    return a / b


def _floordiv(a, b):
    """`a // b`: Python's floor division, of two ints an int.

    Raises:
        NotExact: an operand stands for a float (`_decline`).
    """
    _decline(a, b)
    return a // b


def _mod(a, b):
    """`a % b`: Python's remainder, of two ints an int, and text
    formatting as ever when `a` is a string.

    Raises:
        NotExact: an operand of a remainder stands for a float.
    """
    if isinstance(a, (str, bytes)):
        return a % b
    _decline(a, b)
    return a % b


def _divmod(a, b):
    """`divmod(a, b)`: Python's quotient and remainder, of two ints two
    ints.

    Raises:
        NotExact: an operand stands for a float.
    """
    _decline(a, b)
    return divmod(a, b)


def _pow(a, b, mod=None):
    """`a ** b`: exact for an exact base and a whole exponent (an int
    base and a non-negative int exponent stay an int; a Fraction in
    either place gives a Fraction, as the computation's float does), an
    exact sympy power for a fractional exponent, else Python's power."""
    if mod is not None:
        return pow(a, b, mod)
    _guarded_native(lambda x, y: x ** y, a, b)
    if _is_rational(a) and _is_rational(b):
        exponent = Fraction(b)
        if exponent.denominator == 1:
            if isinstance(a, int) and isinstance(b, int) and exponent >= 0:
                return a ** int(exponent)
            return Fraction(a) ** int(exponent)
        if a == 0 and exponent < 0:
            raise ZeroDivisionError("0 cannot be raised to a negative power")
        return _settled(_sympify(a) ** _sympify(exponent))
    if _exact(a) and _exact(b):
        base, exponent = _sympify(a), _sympify(b)
        if base.is_zero and exponent.is_negative:
            raise ZeroDivisionError("0 cannot be raised to a negative power")
        return _settled(base ** exponent)
    return a ** b


def _stands_for_float(value) -> bool:
    """An exact number standing where the computation had a float: a
    Fraction or a sympy number (an int stands for an int)."""
    return isinstance(value, Fraction) or _symbolic_number(value)


class _FloatMeta(type):
    """`isinstance(x, float)` in the twin: a float, or an exact number
    standing where the computation had a float (a Fraction, a sympy
    number)."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, float) or _stands_for_float(obj)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, (float, Fraction))


class ExactFloat(metaclass=_FloatMeta):
    """`float` as the exact reading sees it: an int (a bool included)
    as the Fraction of the same value, the identity on a Fraction or a
    sympy number, Python's `float` on anything else (a string, a float,
    a library's number). Named `float`, as `type(x).__name__` reads it
    in the computation."""

    def __new__(cls, x=0):
        if isinstance(x, bool):
            return Fraction(int(x))
        if _STATE.guard and isinstance(x, int):
            # an int past float range overflows as the computation's does
            float(x)
        if _is_rational(x):
            return Fraction(x)
        if _symbolic_number(x):
            return x
        return float(x)


ExactFloat.__name__ = ExactFloat.__qualname__ = "float"


def _class_of(value, own):
    """The type of a twin's value as the computation had it: `float`
    (the exact `float`) of a number standing in for a float, `int` of
    an int the claim wrote (`_exact_side.ExactInt`), else `own`, the
    type the value reports itself."""
    from ._exact_side import ExactInt
    if _stands_for_float(value):
        return ExactFloat
    if own is ExactInt:
        return int
    return own


def _type(*args):
    """`type` as the twin reads it: of one value, its type as the
    computation had it (`_class_of`); with three arguments, a class as
    ever."""
    if len(args) != 1:
        return type(*args)
    return _class_of(args[0], type(args[0]))


def _class(value):
    """`value.__class__` as the twin reads it (`_class_of`)."""
    return _class_of(value, value.__class__)


def _round(x, ndigits=None):
    """`round`: Python's own, of an int an int.

    Raises:
        NotExact: `x` stands for a float.
    """
    _decline(x)
    return round(x) if ndigits is None else round(x, ndigits)


def _whole(name: str, x):
    """`math.floor`, `math.ceil` or `math.trunc`, of an int the int.

    Raises:
        NotExact: `x` stands for a float.
    """
    _decline(x)
    return getattr(math, name)(x)


def _fabs(x):
    if _is_rational(x):
        return abs(Fraction(x))
    if _symbolic_number(x):
        return _settled(_sympy().Abs(x))
    return math.fabs(x)


def _sqrt(x):
    if not _exact(x):
        return math.sqrt(x)
    s = _sympify(x)
    if not _truth(s >= 0):
        raise ValueError("math domain error")
    return _settled(_sympy().sqrt(s))


def _log(x, base=None):
    if not _exact(x) or (base is not None and not _exact(base)):
        return math.log(x) if base is None else math.log(x, base)
    sympy = _sympy()
    s = _sympify(x)
    if not _truth(s > 0):
        raise ValueError("math domain error")
    if base is None:
        return _settled(sympy.log(s))
    b = _sympify(base)
    if not _truth(b > 0) or b == 1:
        raise ValueError("math domain error")
    return _settled(sympy.log(s) / sympy.log(b))


def _log_base(base: int):
    def word(x):
        return _log(x, base)
    return word


def _log1p(x):
    return _log(1 + x) if _exact(x) else math.log1p(x)


def _expm1(x):
    return _exp(x) - 1 if _exact(x) else math.expm1(x)


def _exp(x):
    if not _exact(x):
        return math.exp(x)
    return _settled(_sympy().exp(_sympify(x)))


def _transcendental(name: str, inside=None):
    """A `math` function of one real argument as its sympy function,
    `inside` the condition (on the sympy argument) for a real value,
    outside which `math` raises `ValueError`."""
    native = getattr(math, name)

    def word(x):
        if not _exact(x):
            return native(x)
        sympy = _sympy()
        s = _sympify(x)
        if inside is not None and not _truth(inside(s)):
            raise ValueError("math domain error")
        return _settled(getattr(sympy, name)(s))
    return word


def _atan2(y, x):
    if not (_exact(y) and _exact(x)):
        return math.atan2(y, x)
    return _settled(_sympy().atan2(_sympify(y), _sympify(x)))


def _unit(s):
    return (s >= -1) & (s <= 1)


_MATH_EXACT: dict = {
    "sqrt": _sqrt, "exp": _exp, "expm1": _expm1, "log": _log,
    "log1p": _log1p, "log2": _log_base(2), "log10": _log_base(10),
    "pow": _pow, "fabs": _fabs,
    "floor": lambda x: _whole("floor", x),
    "ceil": lambda x: _whole("ceil", x),
    "trunc": lambda x: _whole("trunc", x),
    "sin": _transcendental("sin"), "cos": _transcendental("cos"),
    "tan": _transcendental("tan"),
    "asin": _transcendental("asin", _unit),
    "acos": _transcendental("acos", _unit),
    "atan": _transcendental("atan"), "atan2": _atan2,
    "sinh": _transcendental("sinh"), "cosh": _transcendental("cosh"),
    "tanh": _transcendental("tanh"), "asinh": _transcendental("asinh"),
    "acosh": _transcendental("acosh", lambda s: s >= 1),
    "atanh": _transcendental("atanh", lambda s: (s > -1) & (s < 1)),
}


def _guarded_math(name: str, exact):
    """The exact `math` function `exact`, which under a handler catching
    an arithmetic error (`_Guard`) first declines an argument standing
    for a float and runs `math`'s own on integer arguments, raising
    where the computation raises (`_guarded_native`)."""
    native = getattr(math, name, None)

    def word(*args):
        if native is not None:
            _guarded_native(native, *args)
        return exact(*args)
    return word


_MATH_EXACT = {name: (fn if name == "pow" else _guarded_math(name, fn))
               for name, fn in _MATH_EXACT.items()}

#: the `math` functions a body may bind by name (`from math import
#: sqrt`), by identity, to their exact versions
_MATH_FUNCTIONS: dict = {id(getattr(math, name)): fn
                         for name, fn in _MATH_EXACT.items()
                         if hasattr(math, name)}
#: those `math` functions themselves, by the same ids
_MATH_NATIVE: dict = {id(getattr(math, name)): getattr(math, name)
                      for name in _MATH_EXACT if hasattr(math, name)}


class _ExactMath:
    """The `math` module as the twin reads it: the functions above by
    their exact versions, `pi`, `e` and `tau` as sympy's constants,
    everything else `math`'s own."""

    def __getattr__(self, name):
        exact = _MATH_EXACT.get(name)
        if exact is not None:
            return exact
        if name in ("pi", "e", "tau"):
            sympy = _sympy()
            return {"pi": sympy.pi, "e": sympy.E, "tau": 2 * sympy.pi}[name]
        return getattr(math, name)


_MATH = _ExactMath()
