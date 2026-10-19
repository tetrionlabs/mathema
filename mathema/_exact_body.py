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
point, as `wrap` reports it. `int()`, `//`, `%`, `abs`, `sum`, `min`
and `max` are exact on rationals as Python defines them and are left
alone.
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

__all__ = ["NotExact", "exact_twin"]

#: the names the rewritten body calls for a literal, a division and a
#: power, spelled so no body of its own uses them
_LITERAL, _DIV, _POW = "__mathema_literal__", "__mathema_div__", "__mathema_pow__"

#: each function's twin, built once; `(None,)` for a body that cannot
#: be read
_TWINS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class NotExact(Exception):
    """A step of the exact reading has no exact value: a floor or a
    rounding sympy cannot settle, a transcendental value that is not a
    finite number."""


def exact_twin(fn):
    """Intent:
        The exact twin of `fn`, a function of the same signature whose
        body is `fn`'s read exactly (the module docstring), or None when
        the body cannot be read: `fn` is not a plain Python function,
        has no source (built in, a lambda, defined by `exec`), is
        decorated or wraps another function, or its rewritten body does
        not compile. Built once per function.

    Notes:
        The twin's globals are a copy of `fn`'s with `float`, `round`
        and `pow` shadowed by their exact readings, the `math` module
        (and any of its functions imported by name) by exact versions,
        and `fn`'s own name bound to the twin, so a recursive call is
        read exactly too. A closure's cells are copied in as globals.
    """
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return None
    try:
        return _TWINS[fn][0]
    except KeyError:
        pass
    twin = _build(fn)
    try:
        _TWINS[fn] = (twin,)
    except TypeError:
        pass
    return twin


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


def _build(fn):
    if getattr(fn, "__wrapped__", None) is not None:
        return None
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
    node = tree.body[0]
    if node.decorator_list or node.name != fn.__name__:
        return None
    node = _Exact(src).visit(node)
    ast.fix_missing_locations(node)
    ast.increment_lineno(node, first - 1)
    module = ast.Module(body=[node], type_ignores=[])
    try:
        compiled = compile(module, fn.__code__.co_filename, "exec")
    except (SyntaxError, ValueError, TypeError):
        return None
    env = _globals_of(fn)
    if env is None:
        return None
    try:
        exec(compiled, env)
    except Exception:
        return None
    twin = env.get(node.name)
    if not isinstance(twin, types.FunctionType):
        return None
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
    return twin


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
                           "round": _round, "pow": _pow}
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
    env[_POW] = _pow
    return env


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
    each `/` and `**` (and `/=`, `**=`) a call of the exact operator,
    annotations dropped so they are not evaluated in the twin."""

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
    """A sympy result as the reading keeps it: an Integer as an int, a
    Rational as a Fraction, any other finite number as itself.

    Raises:
        NotExact: the result is not a finite number, or holds a float.
    """
    if not _symbolic_number(value):
        raise NotExact(f"{value} has no exact value")
    if value.is_Integer:
        return int(value)
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


def _pow(a, b, mod=None):
    """`a ** b`: exact for an exact base and a whole exponent (an int
    base and a non-negative int exponent stay an int), an exact sympy
    power for a fractional exponent, else Python's power."""
    if mod is not None:
        return pow(a, b, mod)
    if _is_rational(a) and _is_rational(b):
        exponent = Fraction(b)
        if exponent.denominator == 1:
            if isinstance(a, int) and exponent >= 0:
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


class _FloatMeta(type):
    """`isinstance(x, float)` in the twin: a float, or an exact number
    standing where the computation had a float (a Fraction, a sympy
    number)."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, (float, Fraction)) or _symbolic_number(obj)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, (float, Fraction))


class ExactFloat(metaclass=_FloatMeta):
    """`float` as the exact reading sees it: the identity on an exact
    number (an int, a Fraction, a sympy number), Python's `float` on
    anything else (a string, a float, a library's number)."""

    def __new__(cls, x=0):
        if isinstance(x, bool):
            return int(x)
        if _exact(x):
            return x
        return float(x)


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
