# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lifting a self-recursive function to its closed form.

A linear recurrence with constant coefficients (fibonacci, a doubling
count, a triangular-number accumulator) has an exact closed form, and
sympy's `rsolve` computes it from the recurrence relation plus the base
cases read straight out of the function body. The lift produced here is
the full piecewise object, base-case values on the base region, the
closed form above it, so it is exact at every integer where the
function terminates, not just where the recurrence applies. Where the
function does NOT terminate (a base region of isolated points with the
recursion descending below it), that region is reported as a raise
guard (`RecursionError`), which the pedantic raise-region machinery
then treats exactly like any explicit raise: a value claim quantifying
over it is false there.

The closed form is only meaningful at integer arguments (the runtime
recursion on a non-integer walks a different lattice entirely), so the
minted parameter symbol carries `integer=True` and the adoption site in
try_prove() additionally requires the claim's declared domain to be an
integer subset.
"""
import ast

import sympy

from ._base import NotSymbolic, OpaqueRegistry, _expr_to_sympy, strip_docstring
from ._conditioned import ConditionedLift, _condition_to_sympy
from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout

_MAX_ORDER = 6   # recurrence depth budget: rsolve is exact but the
                 # characteristic polynomial's roots grow unwieldy fast


def _self_call_shifts(ret_expr: ast.AST, fname: str, n: "sympy.Symbol",
                      env: dict) -> "tuple | None":
    """Intent:
        The recursive return expression with each self-call replaced by
        a marker symbol, plus the marker -> shift mapping: `f(n-2)`
        becomes marker `_rec1` with shift 2.

    Notes:
        `None` when any self-call's argument is not `n` minus a positive
        integer constant, when a self-call nests inside another's
        argument, or when the expression doesn't lift. Each occurrence
        gets its own marker so repeated shifts (`f(n-1) + f(n-1)`)
        still combine correctly after substitution.
    """
    markers: dict = {}
    shifts: dict = {}

    class _Replace(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if not (isinstance(node.func, ast.Name) and node.func.id == fname):
                return node
            if len(node.args) != 1 or node.keywords:
                raise NotSymbolic("self-call shape")
            try:
                arg = _expr_to_sympy(node.args[0], dict(env))
            except NotSymbolic:
                raise
            if isinstance(arg, tuple) or arg.free_symbols & set(markers.values()):
                raise NotSymbolic("nested self-call")
            shift = sympy.simplify(n - arg)
            if not (shift.is_Integer and shift > 0):
                raise NotSymbolic("shift is not a positive integer")
            marker = sympy.Symbol(f"_rec{len(markers)}")
            markers[len(markers)] = marker
            shifts[marker] = int(shift)
            return ast.copy_location(
                ast.Name(id=marker.name, ctx=ast.Load()), node)

    try:
        transformed = _Replace().visit(ast.fix_missing_locations(
            ast.Expression(body=ret_expr))).body
        ext = dict(env)
        for marker in shifts:
            ext[marker.name] = marker
        expr = _expr_to_sympy(transformed, ext)
    except (NotSymbolic, RecursionError):
        return None
    if isinstance(expr, tuple) or not shifts:
        return None
    return expr, shifts


def _base_case(stmt: ast.stmt, param: str, fname: str,
               env: dict) -> "tuple | None":
    """Intent:
        Recognize `if n <cmp> <int literal>: return <expr>` as a base
        case: `("le"|"eq", boundary, expr)`, with `<` normalized to
        `<=` on the previous integer.

    Notes:
        `None` for any other statement shape, a self-referential base
        expression, or an unliftable one.
    """
    if not (isinstance(stmt, ast.If) and not stmt.orelse
            and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return)
            and stmt.body[0].value is not None):
        return None
    test = stmt.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.left, ast.Name) and test.left.id == param):
        return None
    from ._conditioned import _literal_value
    ok, lit = _literal_value(test.comparators[0])
    if not ok or isinstance(lit, bool) or not isinstance(lit, int):
        return None
    op = test.ops[0]
    if isinstance(op, ast.LtE):
        kind, boundary = "le", lit
    elif isinstance(op, ast.Lt):
        kind, boundary = "le", lit - 1
    elif isinstance(op, ast.Eq):
        kind, boundary = "eq", lit
    else:
        return None
    ret = stmt.body[0].value
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id == fname for node in ast.walk(ret)):
        return None
    try:
        expr = _expr_to_sympy(ret, dict(env))
    except NotSymbolic:
        return None
    if isinstance(expr, tuple):
        return None
    return kind, boundary, expr


def lift_recurrence(fn, facts) -> "ConditionedLift | None":
    """Intent:
        The exact piecewise closed form of a single-parameter,
        self-recursive function whose body is leading raise guards,
        base-case `if`/`return` statements comparing the parameter
        against integer literals, and one final return combining
        self-calls at fixed positive integer shifts.

    Notes:
        `None` whenever the shape doesn't match or `rsolve` can't close
        the recurrence (a nonlinear one, non-constant coefficients, an
        order above _MAX_ORDER). Every computed seed is verified back
        against the closed form before the lift is trusted. The
        parameter symbol is minted `integer=True`; adoption must gate
        the claim's domain to an integer subset (see try_prove).
    """
    if facts.tree is None or facts.loops or not facts.recursion:
        return None
    if len(facts.params) != 1 or facts.param_kinds.get(facts.params[0]) == "sequence":
        return None
    param = facts.params[0]
    fname = facts.tree.name
    n = sympy.Symbol(param, integer=True)
    env = {param: n}
    body = strip_docstring(facts.tree.body)
    if len(body) < 2 or not isinstance(body[-1], ast.Return) \
            or body[-1].value is None:
        return None

    raise_guards: list = []
    bases: list = []
    for stmt in body[:-1]:
        if isinstance(stmt, ast.If) and not stmt.orelse \
                and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Raise):
            cond = _condition_to_sympy(stmt.test, env)
            if cond is None:
                return None
            exc = stmt.body[0].exc
            name = exc.func.id if isinstance(exc, ast.Call) \
                and isinstance(exc.func, ast.Name) else \
                (exc.id if isinstance(exc, ast.Name) else None)
            raise_guards.append((cond, name))
            continue
        base = _base_case(stmt, param, fname, env)
        if base is None:
            return None
        bases.append(base)
    if not bases:
        return None

    lifted_rec = _self_call_shifts(body[-1].value, fname, n, env)
    if lifted_rec is None:
        return None
    rec_expr, shifts = lifted_rec
    order = max(shifts.values())
    if order > _MAX_ORDER:
        return None

    # the base region over the integers, and the value each covered
    # integer takes (first matching guard, matching runtime order)
    def base_value(k: int):
        for kind, boundary, expr in bases:
            if (kind == "le" and k <= boundary) or (kind == "eq" and k == boundary):
                return expr.subs(n, sympy.Integer(k))
        return None

    top = max(boundary for _kind, boundary, _expr in bases)
    first_recursive = top + 1
    seeds = {}
    yf = sympy.Function("_y")
    for k in range(first_recursive - order, first_recursive):
        value = base_value(k)
        if value is None or value.free_symbols:
            return None
        seeds[yf(sympy.Integer(k))] = value

    # a base region of isolated points (only `==` guards) leaves the
    # recursion descending unboundedly below its floor: that region
    # never terminates, and reads as a raise guard, pedantically
    if not any(kind == "le" for kind, _b, _e in bases):
        floor = min(boundary for _kind, boundary, _expr in bases)
        for k in range(floor, first_recursive):
            if base_value(k) is None:
                return None   # a gap inside the base block: shape too odd
        raise_guards.append((sympy.Lt(n, sympy.Integer(floor)), "RecursionError"))

    # rsolve assumes a LINEAR recurrence and does not reliably refuse a
    # nonlinear one; `y(n-1)*y(n-2)` comes back with a confidently
    # wrong Binet-shaped "solution" rather than an error, so
    # linearity is checked here first: the derivative with respect to
    # each self-call marker must not itself contain any marker
    for marker in shifts:
        try:
            if rec_expr.diff(marker).free_symbols & set(shifts):
                return None
        except Exception:
            return None
    call_subs = {marker: yf(n - shift) for marker, shift in shifts.items()}
    recurrence = yf(n) - rec_expr.subs(call_subs, simultaneous=True)
    if recurrence.free_symbols - {n}:
        return None   # a second free name means non-constant coefficients
    try:
        closed = _with_timeout(
            lambda: sympy.rsolve(recurrence, yf(n), seeds), FAST_TIMEOUT_SECONDS)
    except Exception:
        return None
    if closed is None or closed.has(yf):
        return None
    # the closed form is only trusted once it provably satisfies the
    # recurrence itself and every seed; rsolve's answer is a
    # candidate, not an authority
    residual = closed - rec_expr.subs(
        {marker: closed.subs(n, n - shift) for marker, shift in shifts.items()},
        simultaneous=True)
    try:
        if _with_timeout(lambda: sympy.simplify(residual),
                         FAST_TIMEOUT_SECONDS) != 0:
            return None
    except Exception:
        return None
    for seed_call, value in seeds.items():
        try:
            k = seed_call.args[0]
            if _with_timeout(lambda: sympy.simplify(closed.subs(n, k) - value),
                         FAST_TIMEOUT_SECONDS) != 0:
                return None
        except Exception:
            return None

    pieces = []
    for kind, boundary, expr in bases:
        cond = sympy.Le(n, sympy.Integer(boundary)) if kind == "le" \
            else sympy.Eq(n, sympy.Integer(boundary))
        pieces.append((expr, cond))
    pieces.append((closed, sympy.true))
    return ConditionedLift(kind="value", expr=sympy.Piecewise(*pieces),
                           params={param: n}, sig_params=[param],
                           aggregate={}, opaque=OpaqueRegistry(),
                           raise_guards=raise_guards,
                           recurrence={"min_shift": min(shifts.values()),
                                       "top": top, "closed": closed,
                                       "valid_from": first_recursive - order})
