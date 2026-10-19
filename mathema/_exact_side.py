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

import sys
from fractions import Fraction

#: what a successful exact evaluation returns per side: an int, a
#: Fraction, a bool, or a list of them (or an exact sympy number, see
#: `symbolic_number`)
EXACT_TYPES = (int, Fraction, bool)


#: numpy not looked for yet; `_NUMPY` holds the module or None after
#: the one lookup, since the interpreter does not cache a failed import
_UNLOOKED = object()

#: the name a claim's call `f(...)` is compiled to when one of the
#: function's own parameters is named `f`: a bare `f` then reads the
#: parameter and the call reaches the function under this name
F_CALL = "__f__"


def alias_f_calls(tree, params):
    """Intent:
        `tree` (a parsed claim side) with each call `f(...)` renamed to
        `F_CALL` when one of `params` is named `f`, so a bare `f` reads
        the parameter and the call still reaches the function under
        test; renamed in place and returned.
    """
    import ast
    if "f" not in params:
        return tree
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "f":
            node.func.id = F_CALL
    return tree


def calls_f_by_alias(*codes) -> bool:
    """Intent:
        Whether any of `codes` (compiled claim sides, `None` skipped)
        calls the function under test through `F_CALL`, nested code
        objects included.
    """
    import types
    for code in codes:
        if code is None:
            continue
        if F_CALL in code.co_names or calls_f_by_alias(
                *(c for c in code.co_consts if isinstance(c, types.CodeType))):
            return True
    return False


def f_slot(*codes) -> str:
    """Intent:
        The name `codes` call the function under test by: `F_CALL` when
        they read a bare `f` as a parameter, `f` otherwise.
    """
    return F_CALL if calls_f_by_alias(*codes) else "f"


def _aliased_callees(callees: dict, codes) -> dict:
    """Intent:
        `callees` as `codes` call them: the function under test under
        `F_CALL` rather than `f` when the claim reads a bare `f` as a
        parameter, so the parameter's value keeps the name `f`.
    """
    if "f" not in callees or not calls_f_by_alias(*codes):
        return callees
    return {**{k: v for k, v in callees.items() if k != "f"},
            F_CALL: callees["f"]}
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
    """A float read as the exact rational it holds, a float array, list,
    tuple or set as an object array (or the same container) of them;
    anything else unchanged."""
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
    if isinstance(value, (list, tuple, set, frozenset)) and value \
            and all(isinstance(v, float) for v in value):
        # a list stays a list, a tuple a tuple and a set a set, so the
        # function receives the type it was called with (`xs + xs`
        # concatenates)
        return type(value)(to_exact(v) for v in value)
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
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(to_float(v) for v in value)
    return value


class _Inexact(Exception):
    """A callee run on exact values returned a value that is not exact."""


def holds_number(value) -> bool:
    """Intent:
        Whether `value` holds a number anywhere: an int, a float, a
        complex, a Fraction or Decimal, a numpy number, or a list,
        tuple, dict or array with one inside. A bool, a string, None or
        any other object is not a number.
    """
    from decimal import Decimal
    np = _np()
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return False
    if isinstance(value, (int, float, complex, Fraction, Decimal)):
        return True
    sympy = sys.modules.get("sympy")
    if sympy is not None and isinstance(value, sympy.Basic):
        return bool(value.is_number)
    if np is not None and isinstance(value, np.generic):
        return holds_number(value.item())
    if np is not None and isinstance(value, np.ndarray):
        if value.dtype.kind in "iufc":
            return True
        return any(holds_number(v) for v in value.ravel().tolist())
    if isinstance(value, (list, tuple)):
        return any(holds_number(v) for v in value)
    if isinstance(value, dict):
        return any(holds_number(v) for v in value.values())
    return False


def wrap(callee, exact_calls: bool = False, opaque: bool = False):
    """`callee` called with the executed floats, its result read back
    exactly; with `exact_calls`, called with the exact values themselves,
    its result kept only when it is exact (a float result raises
    `_Inexact`). With `opaque`, a result holding no number (a string, a
    bool, None) is kept as it is: it has no rounding to lose."""
    def call(*args, **kwargs):
        if exact_calls:
            result = callee(*args, **kwargs)
            if _exact_value(result) is None \
                    and not (opaque and not holds_number(result)):
                raise _Inexact(type(result).__name__)
            return result
        else:
            result = callee(*[to_float(a) for a in args],
                            **{k: to_float(v) for k, v in kwargs.items()})
        return to_exact(result)
    return call


def _is_exact(value) -> bool:
    from ._exact_witness import Algebraic
    return isinstance(value, (*EXACT_TYPES, Algebraic)) or symbolic_number(value)


def symbolic_number(value) -> bool:
    """Intent:
        Whether `value` is an exact sympy number: a finite number
        holding no float (`sqrt(2)`, `pi`, `exp(1/3)`, a Rational), the
        value a root or a transcendental step of a body read exactly
        gives (`_exact_body`). False when sympy has not been imported:
        no value is one then.
    """
    sympy = sys.modules.get("sympy")
    if sympy is None or not isinstance(value, sympy.Basic):
        return False
    return (bool(value.is_number) and value.is_finite is True
            and not value.has(sympy.Float))


def from_symbolic(value):
    """An exact sympy number as the exact sides carry it: an Integer as
    an int, a Rational as a Fraction, any other number as itself."""
    if value.is_Integer:
        return int(value)
    if value.is_Rational:
        return Fraction(int(value.p), int(value.q))
    return value


def is_symbolic_side(value) -> bool:
    """Whether an exact side is, or holds, a sympy number."""
    if isinstance(value, (list, tuple)):
        return any(is_symbolic_side(v) for v in value)
    return symbolic_number(value)


def _sympify_exact(value):
    """An exact scalar side as a sympy number, or None when it is not
    one (a bool, a list, a value that is not a number)."""
    import sympy
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Fraction)):
        q = Fraction(value)
        return sympy.Rational(q.numerator, q.denominator)
    if symbolic_number(value):
        return value
    return None


def decide_symbolic(relation: str, left, right, slack) -> "bool | None":
    """Intent:
        The claim's relation between two exact scalar sides, one of them
        at least a sympy number, settled by sympy under the fast
        wall-clock cap: `==` and `!=` by whether the difference is zero
        (its assumptions, then `simplify`, then `equals`), `~=` and a
        declared tolerance by whether `abs(difference)` is within
        `slack` (read as the exact value of the number it is), an
        ordering by the sign of the difference. None when sympy leaves
        the question open, a side is not a scalar number, or the cap
        fires: the point is then undecided, never proven or falsified.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    a, b = _sympify_exact(left), _sympify_exact(right)
    if a is None or b is None:
        return None
    gap = Fraction(slack) if slack else Fraction(0)
    eps = sympy.Rational(gap.numerator, gap.denominator)

    def zero(d) -> "bool | None":
        z = d.is_zero
        if z is None:
            d = sympy.simplify(d)
            z = d.is_zero
        if z is None:
            z = d.equals(0)
        return None if z is None else bool(z)

    def nonpositive(d) -> "bool | None":
        s = d.is_nonpositive
        if s is None:
            s = sympy.simplify(d).is_nonpositive
        return None if s is None else bool(s)

    def negative(d) -> "bool | None":
        s = d.is_negative
        if s is None:
            s = sympy.simplify(d).is_negative
        return None if s is None else bool(s)

    def decide() -> "bool | None":
        d = a - b
        if relation in ("==", "~=", "!="):
            held = zero(d) if eps == 0 else nonpositive(sympy.Abs(d) - eps)
            if held is None:
                return None
            return held if relation != "!=" else not held
        if relation == "<=":
            return nonpositive(d - eps)
        if relation == ">=":
            return nonpositive(-d - eps)
        if relation == "<":
            return negative(d)
        if relation == ">":
            return negative(-d)
        return None
    try:
        return _with_timeout(decide, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except (TypeError, ValueError, ArithmeticError):
        return None


def _exact_value(value, rounded_roots: bool = False):
    """`value` as a plain exact value (an int, Fraction or bool, an exact
    sympy number, or a nested list of them), or None when any part is
    inexact. With `rounded_roots`, a square root of an exact rational
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
    if symbolic_number(value):
        return from_symbolic(value)
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
                exact_calls: bool = False,
                opaque_results: bool = False) -> "tuple | None":
    """Intent:
        `(left, right)` evaluated exactly at the point `env` holds, the
        names in `callees` (the function under test and any function the
        claim binds) called with the executed floats and read back
        exactly, or None when either side is not exact. With
        `exact_calls` each callee runs on the exact values themselves
        (Fractions in place of floats) and the claim's literals are the
        numbers as written: the mathematics of the point. Without it the
        literals are the float readings of the computation, the way the
        number representation reads them. With `opaque_results` a
        callee's result holding no number (a string, a bool, None) is
        exact as it is (`wrap`'s `opaque`), and so is a side holding no
        number.
    """
    from ._math_vocab import MATH_CONSTANTS
    callees = _aliased_callees(callees, (code_l, code_r))
    # a named constant (pi, e) keeps its float, which no exact side
    # survives
    exact_env = {k: (wrap(callees[k], exact_calls, opaque_results)
                     if k in callees
                     else v if k in MATH_CONSTANTS and v is MATH_CONSTANTS[k]
                     else to_exact(v))
                 for k, v in env.items() if k != "__builtins__"}
    for k, v in callees.items():
        exact_env.setdefault(k, wrap(v, exact_calls, opaque_results))
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
    def read(side):
        if opaque_results and not holds_number(side):
            return side
        return _exact_value(side, not exact_calls)
    left = read(left)
    right = read(right) if code_r is not None else None
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
    callees = _aliased_callees(callees, (code_l, code_r))
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
