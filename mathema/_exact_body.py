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
- `float()` is the identity on an exact number, `round()` rounds the
  rational exactly (half to even), `math.floor`, `math.ceil`,
  `math.trunc` and `math.fabs` are exact;
- `math.sqrt`, `math.exp`, `math.log`, the trigonometric and
  hyperbolic functions and `math.pi`, `math.e`, `math.tau` give exact
  sympy values when their arguments are exact, a value the claim's
  comparison then settles symbolically (`_exact_side.decide_symbolic`).

Everything else runs as written. A float the body reads from outside
(a module global, a closure, a value a library returns) is a double
with no exact reading, and the twin's result is then inexact at that
point, as `wrap` reports it. `int()`, `%`, `abs`, `sum`, `min` and
`max` are exact on rationals as Python defines them and are left
alone.

A value the computation holds as a float is held by the twin as a
Fraction or a sympy number, never a bare int: `float(3)` is
`Fraction(3)`, `math.sqrt(4)` is `Fraction(2)`, `4 ** 0.5` and
`2 ** 3.0` are Fractions, `7.5 // 2` is `Fraction(3)` (`//` and
`divmod` are read for that), while an int the body or the claim wrote
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
"""
from __future__ import annotations

import ast
import builtins
import copy
import inspect
import math
import sys
import textwrap
import types
import weakref
from fractions import Fraction

__all__ = ["NotExact", "exact_callee", "exact_twin", "unfaithful"]

#: the names the rewritten body calls for a literal, a division, a
#: floor division, a power and a `.__class__` read, spelled so no body
#: of its own uses them
_LITERAL, _DIV, _POW = "__mathema_literal__", "__mathema_div__", "__mathema_pow__"
_FLOORDIV, _CLASS = "__mathema_floordiv__", "__mathema_class__"

#: each function's reading, built once: `(twin, None)`, or `(None,
#: reason)` for a body that cannot be read faithfully
_TWINS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class NotExact(Exception):
    """A step of the exact reading has no exact value: a floor or a
    rounding sympy cannot settle, a transcendental value that is not a
    finite number."""


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
        vouch for.
    """
    twin, reason = _reading(fn)
    if twin is not None:
        return twin

    def refused(*args, **kwargs):
        raise NotExact(reason)
    return refused


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
    node = _Exact(src).visit(node)
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

    def found_in(self, node) -> list:
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

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id in _TEXT_CALLS:
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
        if node.attr in _TEXT_ATTRS and isinstance(node.ctx, ast.Load):
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
        self._refuse(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, (str, bytes)):
            self._refuse(node)
        self.generic_visit(node)


def _globals_of(fn) -> "dict | None":
    """Intent:
        The twin's globals: `fn`'s, copied, with the exact readings in
        place of `float`, `round`, `pow`, the `math` module and any of
        its functions bound by name, the helper names the rewritten
        body calls, and the cells of `fn`'s closure as globals. None
        when a closure cell is empty.
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
    return env


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
    computation would, annotations dropped so they are not evaluated in
    the twin."""

    def __init__(self, src: str):
        self.src = src

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


def _operator_name(op) -> "str | None":
    if isinstance(op, ast.Div):
        return _DIV
    if isinstance(op, ast.FloorDiv):
        return _FLOORDIV
    if isinstance(op, ast.Pow):
        return _POW
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
        raise NotExact(f"{value} has no exact value")
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
    raise NotExact(f"sympy cannot decide {relational}")


def _literal(text: str):
    """A numeric literal as written: an int, or the decimal as a
    Fraction (`0.1` is 1/10, `2e-9` is 2/10^9)."""
    text = text.replace("_", "")
    try:
        return int(text)
    except ValueError:
        return Fraction(text)


def _div(a, b):
    """`a / b`: the ratio of two exact numbers, else Python's division."""
    if _is_rational(a) and _is_rational(b):
        return Fraction(a) / Fraction(b)
    if _exact(a) and _exact(b):
        divisor = _sympify(b)
        if divisor.is_zero:
            raise ZeroDivisionError("division by zero")
        return _settled(_sympify(a) / divisor)
    return a / b


def _floordiv(a, b):
    """`a // b`: Python's floor division of two exact numbers, an int
    of two ints and otherwise a Fraction (the computation's `//` of a
    float is a float), the exact floor of a sympy ratio, else Python's
    `//`.

    Raises:
        NotExact: sympy does not settle the floor.
    """
    if _is_rational(a) and _is_rational(b):
        out = a // b
        return out if isinstance(a, int) and isinstance(b, int) else Fraction(out)
    if _exact(a) and _exact(b):
        divisor = _sympify(b)
        if divisor.is_zero:
            raise ZeroDivisionError("integer division or modulo by zero")
        floor = _sympy().floor(_sympify(a) / divisor)
        if not floor.is_Integer:
            raise NotExact(f"the floor of {a} / {b} is not settled")
        return Fraction(int(floor))
    return a // b


def _divmod(a, b):
    """`divmod(a, b)`: the quotient and remainder of two exact numbers,
    both ints of two ints and otherwise both Fractions, else Python's
    `divmod`."""
    if _is_rational(a) and _is_rational(b):
        q, r = divmod(a, b)
        if isinstance(a, int) and isinstance(b, int):
            return q, r
        return Fraction(q), Fraction(r)
    if _exact(a) and _exact(b):
        q = _floordiv(a, b)
        return q, _settled(_sympify(a) - _sympify(q) * _sympify(b))
    return divmod(a, b)


def _pow(a, b, mod=None):
    """`a ** b`: exact for an exact base and a whole exponent (an int
    base and a non-negative int exponent stay an int; a Fraction in
    either place gives a Fraction, as the computation's float does), an
    exact sympy power for a fractional exponent, else Python's power."""
    if mod is not None:
        return pow(a, b, mod)
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
    """`round`: exact on a rational (Python's own, half to even), exact
    on a sympy number by its floor, Python's `round` otherwise."""
    if _symbolic_number(x):
        return _round_symbolic(x, ndigits)
    return round(x) if ndigits is None else round(x, ndigits)


def _round_symbolic(x, ndigits):
    sympy = _sympy()
    scale = sympy.Integer(10) ** (0 if ndigits is None else int(ndigits))
    scaled = x * scale
    floor = sympy.floor(scaled)
    if not floor.is_Integer:
        raise NotExact(f"the floor of {scaled} is not settled")
    tie = scaled - floor - sympy.Rational(1, 2)
    if tie.is_zero is True:
        rounded = floor if int(floor) % 2 == 0 else floor + 1
    elif tie.is_positive is True:
        rounded = floor + 1
    elif tie.is_negative is True:
        rounded = floor
    else:
        raise NotExact(f"the rounding of {x} is not settled")
    if ndigits is None:
        return int(rounded)
    return _settled(rounded / scale)


def _whole(name: str, x):
    """`math.floor`, `math.ceil` or `math.trunc` of an exact number."""
    native = getattr(math, name)
    if _is_rational(x):
        return native(x)
    if not _symbolic_number(x):
        return native(x)
    sympy = _sympy()
    if name == "trunc":
        negative = x.is_negative
        if negative is None:
            raise NotExact(f"the sign of {x} is not settled")
        out = sympy.ceiling(x) if negative else sympy.floor(x)
    else:
        out = (sympy.floor if name == "floor" else sympy.ceiling)(x)
    if not out.is_Integer:
        raise NotExact(f"the {name} of {x} is not settled")
    return int(out)


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

#: the `math` functions a body may bind by name (`from math import
#: sqrt`), by identity, to their exact versions
_MATH_FUNCTIONS: dict = {id(getattr(math, name)): fn
                         for name, fn in _MATH_EXACT.items()
                         if hasattr(math, name)}


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
