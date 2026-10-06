# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The allowance a computation line gives a computed value against the
exact value it stands for.

Every comparison of a float result with the mathematics (the probe line,
the `[float]` companion, a brute-force sweep, a witness run again, the
exact re-decision of a pass within tolerance, is_numerically_stable's
trials) asks one question: did the code deliver the result as closely
as its number representation honestly can? One rule answers it. With no
declared tolerance the computed value may miss the exact one by

    relative + min(absolute, relative)      relative = 1e-7 * |exact|
                                            absolute = 1e-9 + input_scaled

where `input_scaled` is the round-off the point's own inputs produce (an
array draw's `_linalg_eval.roundoff_allowance`, 0 for a scalar). The
absolute part never exceeds the relative part of the result: it covers
the rounding of a result near zero, never a wrong result, so a result
of 0.0 for an exact 1.0 at inputs of magnitude 1e16 is a miss whatever
the inputs' round-off. When the exact result is 0, or within the fixed
absolute part of 0 (a trace of -1e-16 over entries near 1, which float
rounds as it rounds 0), the absolute part alone decides what "near
zero" means. A declared tolerance is the whole allowance, an absolute
difference that replaces both parts.
"""
from __future__ import annotations

import ast
from fractions import Fraction

#: the absolute part of the default allowance
ABSOLUTE = 1e-9
#: the relative part of the default allowance, per unit of the result
RELATIVE = 1e-7
#: float64's unit roundoff, half the gap from 1 to the next float
UNIT_ROUNDOFF = 2.0 ** -53
#: the growth a backward-stable computation may show over its condition
#: number times the unit roundoff before the loss is the code's
STABILITY_FACTOR = 2 ** 10


def _magnitude(value):
    """|value| as a Fraction for an exact value or an integer beyond float
    range, else a float; None for a value that is not a real number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction,
                                                          complex)):
        return None
    if isinstance(value, complex):
        return abs(value)
    if isinstance(value, Fraction):
        return abs(value)
    if isinstance(value, int):
        try:
            return abs(float(value))
        except OverflowError:
            return abs(Fraction(value))
    return abs(value)


def allowance(reference, declared=None, input_scaled: float = 0.0):
    """Intent:
        The gap a computed value may miss the exact value `reference`
        by: the declared tolerance when the claim states one, else the
        default rule above. A Fraction when `reference` is exact beyond
        float range, so the comparison never overflows.
    """
    if declared is not None:
        return declared
    ref = _magnitude(reference)
    absolute = ABSOLUTE + float(input_scaled)
    if ref is None or ref <= ABSOLUTE:
        return absolute
    if isinstance(ref, Fraction):
        relative = Fraction(RELATIVE) * ref
        return relative + min(Fraction(absolute), relative)
    relative = RELATIVE * ref
    return relative + min(absolute, relative)


def code_sides(cj) -> "tuple[bool, bool]":
    """Intent:
        Whether each side of the claim runs code: calls `f` or a function
        the claim binds, `(left, right)`.
    """
    bound = set((getattr(cj, "funcs", None) or {}).keys()) | {"f"}

    def runs_code(src) -> bool:
        if not src:
            return False
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            return True
        return any(isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id in bound
                   for node in ast.walk(tree))
    return (runs_code(getattr(cj, "lhs", None)),
            runs_code(getattr(cj, "rhs", None)))


def reference_side(cj) -> "int | None":
    """Intent:
        Which side of the claim is the exact one: 0 for the left, 1 for
        the right, when exactly one side runs no code (it calls neither
        `f` nor a function the claim binds), else None, when the larger
        side stands in for the result.
    """
    left, right = code_sides(cj)
    if left and not right:
        return 1
    if right and not left:
        return 0
    return None


def exact_side_at(cj, code_l, code_r, env: dict, side: "int | None",
                  callees: "dict | None" = None) -> "int | None":
    """Intent:
        The reference side at one point: `side` when the claim settles
        it; else, when neither side runs code (two claim words, as in
        `trace(A) ~= sum(eigvals(A))`), the one side that evaluates
        exactly at the point (the mathematics, against a word computed
        in float), else None.
    """
    if side is not None:
        return side
    left, right = code_sides(cj)
    if left or right:
        return None
    from ._exact_side import exact_sides
    exact = [exact_sides(code, None, env, callees or {}) is not None
             for code in (code_l, code_r)]
    if exact[0] and not exact[1]:
        return 0
    if exact[1] and not exact[0]:
        return 1
    return None


def _elements(value) -> list:
    """The numbers in a value (a number, or nested lists of them)."""
    if isinstance(value, (list, tuple)):
        return [x for v in value for x in _elements(v)]
    return [value] if _magnitude(value) is not None else []


def _array_scale(lv, rv, side):
    """The largest magnitude among the reference side's entries (both
    sides' when neither is known to be exact), 0 when there is none."""
    sides = (lv,) if side == 0 else (rv,) if side == 1 else (lv, rv)
    best = 0
    for value in sides:
        for x in _elements(value):
            m = _magnitude(x)
            if m is not None and m > best:
                best = m
    return best


def _reference_of(u, v, side) -> object:
    if side == 0:
        return u
    if side == 1:
        return v
    mu, mv = _magnitude(u), _magnitude(v)
    if mu is None:
        return v
    if mv is None:
        return u
    return u if mu >= mv else v


def _scalar(u, v, relation: str, declared, input_scaled, side,
            exact_inequality: bool, scale=None):
    from .probing import _exact_pair, holds_inf, holds_nan, same_infinity
    if holds_nan(u) or holds_nan(v):
        return False
    if _magnitude(u) is None or _magnitude(v) is None:
        # a value that is not a number (a string, None, a record) is
        # equal only by its own equality, and does not order
        if relation in ("==", "~="):
            return bool(u == v)
        if relation == "!=":
            return not (u == v)
        return None
    reference = _reference_of(u, v, side) if scale is None else scale
    tol = allowance(reference, declared, input_scaled)
    if isinstance(u, complex) or isinstance(v, complex):
        if relation not in ("==", "~=", "!="):
            return None
        if holds_inf(u) or holds_inf(v):
            close = u == v
        else:
            close = abs(u - v) <= tol
        if relation == "!=":
            return not (u == v) if exact_inequality else not close
        return close
    if same_infinity(u, v):
        return relation in ("==", "~=", "<=", ">=")
    if holds_inf(u) or holds_inf(v):
        # an infinity against a finite value: native comparison is exact
        if relation in ("==", "~="):
            return False
        if relation == "!=":
            return True
        return (u <= v if relation == "<=" else u >= v if relation == ">="
                else u < v if relation == "<" else u > v)
    u, v, tol = _exact_pair(u, v, tol)
    if relation in ("==", "~="):
        return u == v or abs(u - v) <= tol
    if relation == "!=":
        return not (u == v) if exact_inequality else not (
            u == v or abs(u - v) <= tol)
    if relation == "<=":
        return u <= v + tol
    if relation == ">=":
        return u >= v - tol
    if relation == "<":
        return u < v
    if relation == ">":
        return u > v
    return None


def relation_within(lv, rv, relation: str, declared=None,
                    input_scaled: float = 0.0, side: "int | None" = None,
                    exact_inequality: bool = True) -> "bool | None":
    """Intent:
        Whether `lv <relation> rv` holds on a computation line, the
        computed side allowed to miss the exact side (`side`, as
        `reference_side` names it) by `allowance(...)` at every element.
        A NaN anywhere fails every relation. `==`, `~=` and `!=` over
        arrays are one fact about the whole value, so `!=` holds when
        some element differs and two values of different shapes are
        unequal outright; an ordering holds when it holds at every
        element and is None (unanswerable) over mismatched shapes or
        values that do not order. `exact_inequality` makes `!=` fail
        only at an actual equality.
    """
    from .probing import _is_matrix_value, plain_value
    lv, rv = plain_value(lv), plain_value(rv)
    arrays = _is_matrix_value(lv) or _is_matrix_value(rv)
    # over arrays the result's magnitude is its largest entry: an entry
    # that is exactly 0 beside entries near 1 (the off-diagonal of an
    # identity) is judged at the result's scale, not against zero
    scale = _array_scale(lv, rv, side) if arrays else None

    def leaf(x, y):
        try:
            return _scalar(x, y, relation, declared, input_scaled, side,
                           exact_inequality, scale)
        except TypeError:
            return None

    if not arrays:
        return leaf(lv, rv)

    def walk(x, y):
        xs, ys = isinstance(x, (list, tuple)), isinstance(y, (list, tuple))
        if xs and ys:
            if len(x) != len(y):
                return None
            parts = [walk(a, b) for a, b in zip(x, y)]
        elif xs:
            parts = [walk(a, y) for a in x]
        elif ys:
            parts = [walk(x, b) for b in y]
        else:
            return leaf(x, y)
        if any(pt is None for pt in parts):
            return None
        return all(parts)

    if relation == "!=":
        if exact_inequality:
            return not _exactly_equal(lv, rv)
        equal = relation_within(lv, rv, "==", declared, input_scaled, side,
                                exact_inequality)
        return not equal
    held = walk(lv, rv)
    if held is None and relation in ("==", "~="):
        # two values of different shapes are unequal outright
        return False
    return held


def _exactly_equal(lv, rv) -> bool:
    """Whether two values (numbers, or nested lists of them) are equal
    exactly, element by element; different shapes are unequal."""
    from .probing import holds_nan
    xs, ys = isinstance(lv, (list, tuple)), isinstance(rv, (list, tuple))
    if xs and ys:
        return len(lv) == len(rv) and all(_exactly_equal(a, b)
                                          for a, b in zip(lv, rv))
    if xs:
        return all(_exactly_equal(a, rv) for a in lv)
    if ys:
        return all(_exactly_equal(lv, b) for b in rv)
    if holds_nan(lv) or holds_nan(rv):
        return False
    try:
        return bool(lv == rv)
    except Exception:
        return False


def largest_miss(lv, rv, side) -> "tuple":
    """Intent:
        `(gap, result)` for a failed comparison: the largest absolute
        difference between the sides over their elements, and the
        result's magnitude, the largest entry over both sides (the value
        a relative error is read against), both as floats; `(0.0, 0.0)`
        when nothing compares.
    """
    from .probing import _is_matrix_value, plain_value
    lv, rv = plain_value(lv), plain_value(rv)
    best = (0.0, 0.0)

    def gap_of(x, y):
        nonlocal best
        mx, my = _magnitude(x), _magnitude(y)
        if mx is None or my is None:
            return
        try:
            gap = abs(Fraction(x) - Fraction(y)) if not isinstance(
                x, complex) and not isinstance(y, complex) else abs(x - y)
        except (TypeError, ValueError, OverflowError):
            return
        try:
            gap_f = float(gap)
        except OverflowError:
            gap_f = float("inf")
        if gap_f > best[0]:
            best = (gap_f, best[1])

    def walk(x, y):
        xs, ys = isinstance(x, (list, tuple)), isinstance(y, (list, tuple))
        if xs and ys:
            for a, b in zip(x, y):
                walk(a, b)
        elif xs:
            for a in x:
                walk(a, y)
        elif ys:
            for b in y:
                walk(x, b)
        else:
            gap_of(x, y)
    result = _array_scale(lv, rv, None)
    try:
        best = (0.0, float(result))
    except OverflowError:
        best = (0.0, float("inf"))
    if _is_matrix_value(lv) or _is_matrix_value(rv):
        walk(lv, rv)
    else:
        gap_of(lv, rv)
    return best
