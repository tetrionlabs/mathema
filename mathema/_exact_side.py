# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's sides evaluated exactly at an executed point.

On a computation line the function runs in floats, as it does for its
callers, but the claim's own arithmetic is mathematics: its literals are
the numbers written and its words compute exactly. This evaluates both
sides with every float input read as the exact rational it holds, each
call of the function under test made with the original floats and its
result read back as the exact rational it returned, and the claim's own
`+ - * /`, `abs`, `min` and `max` carried out in rationals. A side that
any step leaves inexact (a square root, a logarithm, a float literal the
words could not keep exact) is not returned: the caller keeps the float
evaluation.
"""
from __future__ import annotations

from fractions import Fraction

#: what a successful exact evaluation returns per side: an int, a
#: Fraction, a bool, or a list of them
EXACT_TYPES = (int, Fraction, bool)


#: numpy not looked for yet; `_NUMPY` holds the module or None after
#: the one lookup, since the interpreter does not cache a failed import
_UNLOOKED = object()
_NUMPY: object = _UNLOOKED


def _np():
    """The numpy module, or None on an install without it, looked up
    once per process."""
    global _NUMPY
    if _NUMPY is _UNLOOKED:
        try:
            import numpy
        except ImportError:
            numpy = None
        _NUMPY = numpy
    return _NUMPY


def to_exact(value):
    """A float read as the exact rational it holds, a float array or list
    as an object array (or list) of them; anything else unchanged."""
    np = _np()
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        # a signed zero has no exact counterpart and stays the float
        # it is, so the function still receives -0.0
        if value == 0.0 and str(value).startswith("-"):
            return value
        return Fraction(value) if value == value and abs(value) != float("inf") else value
    if np is not None and isinstance(value, np.ndarray) and value.dtype.kind == "f":
        out = np.empty(value.shape, dtype=object)
        for idx, v in np.ndenumerate(value):
            out[idx] = to_exact(float(v))
        return out
    if np is not None and isinstance(value, np.floating):
        return to_exact(float(value))
    if isinstance(value, list) and value and all(isinstance(v, float) for v in value):
        # a list stays a list, so the function receives the type it was
        # called with (`xs + xs` concatenates)
        return [to_exact(v) for v in value]
    return value


def to_float(value):
    """The inverse of `to_exact` for a call of the function under test:
    the floats the executed point held."""
    np = _np()
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, ExactInt):
        return int(value)
    if np is not None and isinstance(value, np.ndarray) and value.dtype == object:
        return value.astype(float)
    if isinstance(value, list):
        return [to_float(v) for v in value]
    return value


class _Inexact(Exception):
    """A callee run on exact values returned a value that is not exact."""


def wrap(callee, exact_calls: bool = False):
    """`callee` called with the executed floats, its result read back
    exactly; with `exact_calls`, called with the exact values themselves,
    its result kept only when it is exact (a float result raises
    `_Inexact`)."""
    def call(*args, **kwargs):
        if exact_calls:
            result = callee(*args, **kwargs)
            if _exact_value(result) is None:
                raise _Inexact(type(result).__name__)
            return result
        else:
            result = callee(*[to_float(a) for a in args],
                            **{k: to_float(v) for k, v in kwargs.items()})
        return to_exact(result)
    return call


def _is_exact(value) -> bool:
    from ._exact_witness import Algebraic
    return isinstance(value, (*EXACT_TYPES, Algebraic))


def _exact_value(value, rounded_roots: bool = False):
    """`value` as a plain exact value (an int, Fraction or bool, or a
    nested list of them), or None when any part is inexact. With
    `rounded_roots`, a square root of an exact rational
    (`_linalg_eval._Root`, rounded once to a float or, beyond float
    range, to 60 significant digits) is read as that rounded value, a
    reading close enough for a computation line's tolerance."""
    from ._linalg_eval import _Root
    np = _np()
    if np is not None and isinstance(value, np.ndarray):
        value = value.tolist()
    if np is not None and isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, _Root):
        return Fraction(value) if rounded_roots else None  # type: ignore[call-overload]
    if _is_exact(value):
        return value
    if isinstance(value, (list, tuple)):
        parts = [_exact_value(v, rounded_roots) for v in value]
        if any(p is None for p in parts):
            return None
        return parts
    return None


def _exact_elements(value) -> "list | None":
    """The elements of a vector of exact numbers, or None."""
    np = _np()
    if np is not None and isinstance(value, np.ndarray):
        if value.ndim != 1:
            return None
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return None
    if all(isinstance(v, (int, Fraction)) and not isinstance(v, bool)
           for v in value):
        return list(value)
    return None


def exact_words(words: dict) -> dict:
    """Intent:
        The claim words that keep an exact vector exact: `sum`, `mean`
        and `prod` as Fractions, `norm` (Euclidean, of a vector) and
        `sqrt` as the square root of the exact rational
        (`_linalg_eval._exact_sqrt`), whose whole powers are exact. Any
        other argument goes to the word as it was.
    """
    from ._linalg_eval import _exact_sqrt
    out: dict = {}

    def keep(name, exact):
        original = words.get(name)
        if original is None:
            return

        def word(*args, **kwargs):
            if len(args) == 1 and not kwargs:
                result = exact(args[0])
                if result is not None:
                    return result
            return original(*args, **kwargs)
        out[name] = word

    def total(v):
        xs = _exact_elements(v)
        return None if xs is None else sum(xs, Fraction(0))

    def mean(v):
        xs = _exact_elements(v)
        return None if not xs else sum(xs, Fraction(0)) / len(xs)

    def prod(v):
        xs = _exact_elements(v)
        if xs is None:
            return None
        out_ = Fraction(1)
        for x in xs:
            out_ *= x
        return out_

    def norm(v):
        xs = _exact_elements(v)
        return None if xs is None else _exact_sqrt(
            sum((Fraction(x) * x for x in xs), Fraction(0)))

    def sqrt(v):
        if isinstance(v, (int, Fraction)) and not isinstance(v, bool) \
                and v >= 0:
            return _exact_sqrt(Fraction(v))
        return None
    for name, fn in (("sum", total), ("mean", mean), ("prod", prod),
                     ("norm", norm), ("sqrt", sqrt)):
        keep(name, fn)
    return out


class ExactInt(int):
    """An integer literal of the claim whose division and negative powers
    stay exact: `1 / 3` is a Fraction, `10**-20` is 1/10^20."""

    @staticmethod
    def _keep(value):
        return ExactInt(value) if type(value) is int else value

    def __add__(self, other):
        return self._keep(int.__add__(self, other))

    def __radd__(self, other):
        return self._keep(int.__radd__(self, other))

    def __sub__(self, other):
        return self._keep(int.__sub__(self, other))

    def __rsub__(self, other):
        return self._keep(int.__rsub__(self, other))

    def __mul__(self, other):
        return self._keep(int.__mul__(self, other))

    def __rmul__(self, other):
        return self._keep(int.__rmul__(self, other))

    def __truediv__(self, other):
        if isinstance(other, (int, Fraction)) and not isinstance(other, bool):
            return Fraction(int(self)) / other
        return int(self) / other

    def __rtruediv__(self, other):
        if isinstance(other, (int, Fraction)) and not isinstance(other, bool):
            return other / Fraction(int(self))
        return other / int(self)

    def __pow__(self, k, mod=None):
        if mod is None and isinstance(k, int) and not isinstance(k, bool):
            return self._keep(int(self) ** int(k)) if k >= 0 \
                else Fraction(int(self)) ** int(k)
        return pow(int(self), k, mod) if mod is not None else int(self) ** k

    def __rpow__(self, base):
        if isinstance(base, (int, Fraction)) and not isinstance(base, bool) \
                and int(self) < 0:
            return Fraction(base) ** int(self)
        return base ** int(self)

    def __neg__(self):
        return ExactInt(-int(self))


#: each compiled claim side's exact twin: the same expression with every
#: numeric literal read from its source text (`__exact__("0.3")`), so no
#: literal is rounded to a float and no constant expression is folded
_EXACT_TWINS: "dict" = {}


def _literal(text: str):
    """A numeric literal's exact value from its source text."""
    text = text.replace("_", "")
    try:
        return ExactInt(int(text))
    except ValueError:
        return Fraction(text)


def _representation_literal(text: str):
    """A numeric literal as the computation reads it: an integer exact,
    a float literal as the exact value of the float it parses to, and a
    negative zero as the signed float it is."""
    text = text.replace("_", "")
    try:
        return ExactInt(int(text))
    except ValueError:
        value = float(text)
    if value == 0.0 and str(value).startswith("-"):
        return value
    return Fraction(value)


def register_source(code, src: str, tree) -> None:
    """Intent:
        Record the exact twins of `code`, compiled from `tree` (parsed
        from `src`): each int or float literal replaced by a call reading
        its source text, as written (`__exact__`) or as the computation
        reads it (`__representation__`). A sign written before a literal is
        read with it, so `-0.0` keeps its sign.
    """
    import ast
    import copy

    def twin_of(name: str):
        class _Exact(ast.NodeTransformer):
            def _call(self, text, node):
                return ast.copy_location(ast.Call(
                    func=ast.Name(name, ast.Load()),
                    args=[ast.Constant(text)], keywords=[]), node)

            def visit_UnaryOp(self, node):
                operand = node.operand
                if isinstance(node.op, ast.USub) \
                        and isinstance(operand, ast.Constant) \
                        and isinstance(operand.value, (int, float)) \
                        and not isinstance(operand.value, bool):
                    text = ast.get_source_segment(src, operand)
                    if text is not None:
                        return self._call("-" + text, node)
                return self.generic_visit(node)

            def visit_Constant(self, node):
                if isinstance(node.value, (int, float)) \
                        and not isinstance(node.value, bool):
                    text = ast.get_source_segment(src, node)
                    if text is None:
                        return node
                    return self._call(text, node)
                return node
        twin = _Exact().visit(copy.deepcopy(tree))
        ast.fix_missing_locations(twin)
        return compile(twin, "<conjecture>", "eval")
    try:
        if len(_EXACT_TWINS) > 4096:
            _EXACT_TWINS.clear()
        _EXACT_TWINS[code] = (twin_of("__exact__"), twin_of("__representation__"))
    except (SyntaxError, ValueError, TypeError):
        return


def exact_literals(code, written: bool = True):
    """`code` with its literals exact. `written`: each numeric literal
    is the number written in the claim (its source text, through the
    registered twin, else the shortest decimal that reads back as the
    float). Otherwise each float literal is the exact value of the float
    it parses to, the number representation's own reading. Integer
    literals divide and take negative powers exactly either way; nested
    code objects included."""
    import math
    import types
    if code is None:
        return None
    twins = _EXACT_TWINS.get(code)
    if twins is not None:
        return twins[0] if written else twins[1]
    consts = []
    for c in code.co_consts:
        if isinstance(c, float) and c == 0.0 and math.copysign(1.0, c) < 0 \
                and not written:
            # the computation reads -0.0 as the signed zero it is
            consts.append(c)
        elif isinstance(c, float) and not isinstance(c, bool) and math.isfinite(c):
            consts.append(Fraction(repr(c)) if written else Fraction(c))
        elif type(c) is int:
            consts.append(ExactInt(c))
        elif isinstance(c, types.CodeType):
            consts.append(exact_literals(c, written))
        else:
            consts.append(c)
    try:
        return code.replace(co_consts=tuple(consts))
    except (TypeError, ValueError):
        return code


def exact_sides(code_l, code_r, env: dict, callees: dict,
                exact_calls: bool = False) -> "tuple | None":
    """Intent:
        `(left, right)` evaluated exactly at the point `env` holds, the
        names in `callees` (the function under test and any function the
        claim binds) called with the executed floats and read back
        exactly, or None when either side is not exact. With
        `exact_calls` each callee runs on the exact values themselves
        (Fractions in place of floats) and the claim's literals are the
        numbers as written: the mathematics of the point. Without it the
        literals are the float readings of the computation, the way the
        number representation reads them.
    """
    from ._math_vocab import MATH_CONSTANTS
    # a named constant (pi, e) keeps its float, which no exact side
    # survives
    exact_env = {k: (wrap(callees[k], exact_calls) if k in callees
                     else v if k in MATH_CONSTANTS and v is MATH_CONSTANTS[k]
                     else to_exact(v))
                 for k, v in env.items() if k != "__builtins__"}
    for k, v in callees.items():
        exact_env.setdefault(k, wrap(v, exact_calls))
    exact_env.update(exact_words({k: v for k, v in env.items()
                                  if k not in callees}))
    exact_env["__exact__"] = _literal
    exact_env["__representation__"] = _representation_literal
    try:
        left = eval(exact_literals(code_l, exact_calls),
                    {"__builtins__": {}}, exact_env)
        right = eval(exact_literals(code_r, exact_calls),
                     {"__builtins__": {}}, exact_env) \
            if code_r is not None else None
    except Exception:
        return None
    # a rounded root is close enough for a computation line, never for
    # the mathematics
    left = _exact_value(left, not exact_calls)
    right = _exact_value(right, not exact_calls) if code_r is not None else None
    if left is None or (code_r is not None and right is None):
        return None
    return left, right


def some_side_is_finite(code_l, code_r, env: dict, callees: dict) -> bool:
    """Intent:
        Whether either side of the claim, evaluated exactly at the point
        `env` holds as a computation line reads it (the function's
        results as the values it returned, literals as the floats they
        parse to, a square root rounded once), is a finite value. Two
        float sides at the same infinity then do not agree: the value
        they stand for is finite.
    """
    exact_env = {k: (wrap(callees[k]) if k in callees else to_exact(v))
                 for k, v in env.items() if k != "__builtins__"}
    for k, v in callees.items():
        exact_env.setdefault(k, wrap(v))
    exact_env.update(exact_words({k: v for k, v in env.items()
                                  if k not in callees}))
    exact_env["__exact__"] = _literal
    exact_env["__representation__"] = _representation_literal
    for code in (code_l, code_r):
        if code is None:
            continue
        try:
            value = eval(exact_literals(code, False), {"__builtins__": {}},
                         exact_env)
        except Exception:
            continue
        if _exact_value(value, True) is not None:
            return True
    return False
