# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Partiality lemmas: where functions raise, as consumable facts.

`math.sqrt(u)` raises ValueError for u < 0 just as surely as an
explicit `if u < 0: raise ValueError` would, so a value claim
quantifying over that region is false there, pedantically, the same
reading the explicit raise guards already get. This module walks a
function body and emits those implicit raise regions as guards in the
exact shape `lift_piecewise` produces for explicit ones, so the
raise-region verdict machinery treats both identically.

The registry works for any function, not just the standard library's:
the math-module rows ship out of the box, and `register_raises_when`
(public as `mathema.lemmas.register_raises_when`) adds a lemma about
an arbitrary function, a third-party kernel, the user's own helper,
so claims about its CALLERS adjudicate against its raising region too.
True division contributes a ZeroDivisionError guard with no registry
entry at all.

Deliberately absent from the built-in rows: `x ** 0.5` (Python returns
a complex number, no raise, the ordering machinery already refuses
complex values) and numpy's vectorized forms (they return nan, which
is the missing-policy axis, adjudicated by is_missing_safe, never a
raise). A bare `sqrt` call in a body matches only through the caller's
own scope resolving it to a registered function, the spelling alone
never decides, since guessing the origin wrong would falsify with a
lemma about the wrong function.
"""
import ast

import sympy

from ._base import NotSymbolic, _bind_params, _expr_to_sympy, strip_docstring

# The partiality-lemma registry: qualified function name -> list of
# (condition builder, exception name). A condition builder takes the
# call's lifted arguments (sympy expressions) and returns the region
# where the call RAISES. The math-module rows ship out of the box;
# `register_raises_when` (public via mathema.lemmas) adds rows for
# arbitrary functions, a caller's claims then falsify over a
# registered function's raising region exactly as they do over
# math.sqrt's.
_PARTIALITY_LEMMAS: dict = {
    "math.sqrt": [(lambda u: sympy.Lt(u, 0), "ValueError")],
    "math.log": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log2": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log10": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.asin": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
    "math.acos": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
}


def qualified_name(fn) -> "str | None":
    """`module.qualname` for a plain function, `None` for anything
    without an importable identity (a lambda, a nested def's caller may
    still register it by its literal `module.qualname` string)."""
    mod = getattr(fn, "__module__", None)
    qual = getattr(fn, "__qualname__", None)
    if not mod or not qual:
        return None
    return f"{mod}.{qual}"


def register_raises_when(target, condition, exc_name: str = "ValueError") -> None:
    """Intent:
        Register a partiality lemma about any function: `condition`,
        given the call's lifted arguments as sympy expressions, returns
        the region where `target` raises `exc_name`. Claims about
        functions that CALL the target then treat that region exactly
        like an explicit raise guard.

    Notes:
        `target` is a callable or its dotted "module.qualname" string.
        Lemmas accumulate (several conditions per function are fine).
    """
    key = target if isinstance(target, str) else qualified_name(target)
    if not key:
        raise ValueError("target has no importable module.qualname; "
                         "pass the dotted name string instead")
    _PARTIALITY_LEMMAS.setdefault(key, []).append((condition, exc_name))


def _lemmas_for_call(node: ast.Call, scope: dict) -> list:
    """The registered partiality lemmas matching one call node.
    Resolution goes through the enclosing function's own scope first,
    `import math as _math; _math.sqrt(u)` reaches math.sqrt's lemma by
    resolving the actual object, however the caller spelled the import,
    with the literal dotted text as the fallback for a module the
    scope can't see."""
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        holder = scope.get(node.func.value.id)
        target = getattr(holder, node.func.attr, None) if holder is not None \
            else None
        key = qualified_name(target) if callable(target) else None
        if key and key in _PARTIALITY_LEMMAS:
            return _PARTIALITY_LEMMAS[key]
        return _PARTIALITY_LEMMAS.get(f"{node.func.value.id}.{node.func.attr}", [])
    if isinstance(node.func, ast.Name):
        target = scope.get(node.func.id)
        key = qualified_name(target) if callable(target) else None
        if key:
            return _PARTIALITY_LEMMAS.get(key, [])
    return []


def _guards_in_expr(node: ast.AST, env: dict, path_cond, out: list,
                    scope: dict) -> None:
    """Intent:
        Collect every implicit raise region inside one expression: a
        call with a registered partiality lemma (math.sqrt's negative
        region, a user-registered lemma about their own helper), or a
        true division, each guarded by the path condition it sits
        under.

    Notes:
        An argument that doesn't lift contributes no guard, a missed
        guard leaves today's behavior (no new falsification), never a
        wrong one. The recursion is manual, never a blind ast.walk: a
        guard's condition must be EXACT about whether its operation
        executes, so a ternary's arms carry the ternary's own condition
        (`0.0 if x == 0 else 1/x` divides only where x != 0, an
        unconditional guard there falsified a true claim in dev), and
        short-circuited operands of and/or, whose execution this pass
        can't condition exactly, contribute no guards at all.
    """
    if isinstance(node, ast.IfExp):
        from ._conditioned import _condition_to_sympy
        _guards_in_expr(node.test, env, path_cond, out, scope)
        cond = _condition_to_sympy(node.test, dict(env))
        if cond is not None:
            _guards_in_expr(node.body, env, sympy.And(path_cond, cond),
                            out, scope)
            _guards_in_expr(node.orelse, env,
                            sympy.And(path_cond, sympy.Not(cond)), out, scope)
        return
    if isinstance(node, ast.BoolOp):
        # only the first operand is unconditionally evaluated
        if node.values:
            _guards_in_expr(node.values[0], env, path_cond, out, scope)
        return
    if isinstance(node, ast.Call) and not node.keywords:
        for condition, exc_name in _lemmas_for_call(node, scope):
            try:
                args = [_expr_to_sympy(a, dict(env)) for a in node.args]
                region = condition(*args)
            except Exception:
                continue
            out.append((sympy.And(path_cond, region), exc_name))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        try:
            denom = _expr_to_sympy(node.right, dict(env))
        except NotSymbolic:
            denom = None
        if denom is not None and not isinstance(denom, tuple) \
                and denom.free_symbols:
            out.append((sympy.And(path_cond, sympy.Eq(denom, 0)),
                        "ZeroDivisionError"))
    for child in ast.iter_child_nodes(node):
        _guards_in_expr(child, env, path_cond, out, scope)


def partiality_guards(fn, facts) -> list:
    """Intent:
        The implicit raise regions of a straight-line (or simply
        branched) body, as (condition, exception name) guards over the
        function's own parameter symbols, the same shape
        lift_piecewise's explicit raise guards take.

    Notes:
        Walks docstring-stripped statements with local assignments
        threaded into the environment, so `disc = b*b - 4*a*c;
        math.sqrt(disc)` guards on the full discriminant expression.
        Declines to an empty list on any shape it doesn't recognize
        past the statements it already processed, partial coverage
        only ever under-reports.
    """
    if facts.tree is None:
        return []
    try:
        params, aggregate = _bind_params(fn, facts)
    except Exception:
        return []
    # bundled (dataclass/dict/self) parameters are fine now: their
    # fields are ordinary composite symbols, so a guard over
    # `self.rate` or `cfg.a` reads like any scalar guard
    from ._conditioned import _condition_to_sympy

    scope = getattr(fn, "__globals__", None) or {}
    guards: list = []

    def always_exits(stmts) -> bool:
        if not stmts:
            return False
        last = stmts[-1]
        if isinstance(last, (ast.Return, ast.Raise)):
            return True
        if isinstance(last, ast.If):
            return bool(last.orelse) and always_exits(last.body) \
                and always_exits(last.orelse)
        return False

    def walk(stmts, path_cond, env):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                    and isinstance(stmt.targets[0], ast.Name):
                _guards_in_expr(stmt.value, env, path_cond, guards, scope)
                try:
                    value = _expr_to_sympy(stmt.value, dict(env))
                except NotSymbolic:
                    return
                if isinstance(value, tuple):
                    return
                env = dict(env)
                env[stmt.targets[0].id] = value
            elif isinstance(stmt, ast.Return):
                if stmt.value is not None:
                    _guards_in_expr(stmt.value, env, path_cond, guards, scope)
                return   # nothing after a return executes
            elif isinstance(stmt, ast.If):
                cond = _condition_to_sympy(stmt.test, env)
                if cond is None:
                    return
                _guards_in_expr(stmt.test, env, path_cond, guards, scope)
                walk(stmt.body, sympy.And(path_cond, cond), env)
                if stmt.orelse:
                    walk(stmt.orelse, sympy.And(path_cond, sympy.Not(cond)), env)
                # a guard's condition must be EXACT about reachability
                # (the raise-region witness is verified against the
                # condition, not by running the function, so an
                # over-approximated path would accept a false witness:
                # `if x < 0: return 0.0` followed by math.sqrt(x) never
                # raises). Statements after the If run under the
                # negation of whichever branches always exit.
                if always_exits(stmt.body):
                    path_cond = sympy.And(path_cond, sympy.Not(cond))
                if stmt.orelse and always_exits(stmt.orelse):
                    path_cond = sympy.And(path_cond, cond)
            elif isinstance(stmt, ast.Raise):
                return   # nothing after a raise executes
            elif isinstance(stmt, ast.For):
                # a loop body's guards are collected where they lift:
                # an expression depending on the loop variable or an
                # accumulator fails to lift and contributes nothing
                # (under-reporting, never a wrong guard). The walk
                # then CONTINUES past the loop with every loop-
                # assigned name evicted from the environment, a
                # later expression reading one simply stops the walk
                # there, partial coverage as everywhere else.
                # exactness across a zero-trip loop: a body guard only
                # holds where the loop actually runs, so the trip-
                # positivity condition rides on it (range(n) needs
                # n >= 1). A header this can't read collects nothing.
                body_cond = None
                if (isinstance(stmt.iter, ast.Call)
                        and isinstance(stmt.iter.func, ast.Name)
                        and stmt.iter.func.id == "range"
                        and not stmt.iter.keywords
                        and len(stmt.iter.args) in (1, 2)):
                    try:
                        if len(stmt.iter.args) == 1:
                            trip = _expr_to_sympy(stmt.iter.args[0], dict(env))
                        else:
                            trip = (_expr_to_sympy(stmt.iter.args[1], dict(env))
                                    - _expr_to_sympy(stmt.iter.args[0], dict(env)))
                        if not isinstance(trip, tuple):
                            body_cond = sympy.And(path_cond, trip >= 1)
                    except NotSymbolic:
                        body_cond = None
                if body_cond is not None:
                    for node in ast.walk(stmt):
                        if isinstance(node, (ast.Assign, ast.AugAssign)):
                            _guards_in_expr(node.value, env, body_cond,
                                            guards, scope)
                loop_names = set()
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and isinstance(
                            getattr(node, "ctx", None), ast.Store):
                        loop_names.add(node.id)
                if isinstance(stmt.target, ast.Name):
                    loop_names.add(stmt.target.id)
                env = {k: v for k, v in env.items() if k not in loop_names}
            elif isinstance(stmt, (ast.Pass, ast.Expr)):
                continue
            else:
                return
    walk(strip_docstring(facts.tree.body), sympy.true, dict(params))
    return guards
