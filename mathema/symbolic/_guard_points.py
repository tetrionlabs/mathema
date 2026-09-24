# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The points where a function's own guards switch.

A branch such as `if denom == 0.0:` changes the result only on the set
where its condition holds, and for an equality that set has measure
zero: random sampling never lands on it. The solutions of each guard's
comparison, solved for one parameter at a time with the others held at
representative values, are points a sampler can try deliberately, the
same way it tries a domain's corners.

`guard_surfaces` reads the guards off the function body,
`diff_surfaces` off a Piecewise expression, and `surface_points`
solves them.
"""
from __future__ import annotations

import ast
import itertools
import math

import sympy

from ._base import NotSymbolic, _bind_params, _expr_to_sympy

_MAX_POINTS = 32
_MAX_COMBOS = 16


def _relational_surfaces(cond) -> list:
    """Intent:
        Every comparison inside a sympy Boolean as `lhs - rhs`, the
        expression that is zero exactly where the comparison switches.
    """
    out: list = []
    if cond is None or cond in (sympy.true, sympy.false):
        return out
    for rel in cond.atoms(sympy.core.relational.Relational):
        try:
            out.append(sympy.expand(rel.lhs - rel.rhs))
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def guard_surfaces(fn, facts) -> tuple[list, dict]:
    """Intent:
        The switching surfaces of every `if` and conditional-expression
        guard in `fn`'s body, as sympy expressions over the parameter
        symbols, with the symbol table they are written in.

    Notes:
        Straight-line assignments are traced into the guard (`denom =
        x * y; if denom == 0.0` reads as `x*y`); a name reassigned in a
        way that does not lift is dropped, so a guard on it is skipped
        rather than traced wrongly. Loop bodies are not entered: a
        guard there depends on the loop variable. Returns `([], {})`
        when the body is unavailable.
    """
    if facts.tree is None or not facts.params:
        return [], {}
    from ._conditioned import _condition_to_sympy
    from ._normalize import normalized_body
    try:
        params, _aggregate = _bind_params(fn, facts)
        body = normalized_body(fn, facts)
    except (NotSymbolic, TypeError, ValueError, AttributeError):
        return [], {}
    surfaces: list = []

    def collect_ifexp(node, env):
        for sub in ast.walk(node):
            if isinstance(sub, ast.IfExp):
                surfaces.extend(_relational_surfaces(
                    _condition_to_sympy(sub.test, dict(env))))

    def walk(stmts, env):
        for st in stmts:
            if isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                for sub in ast.walk(st):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        env.pop(sub.id, None)
                continue
            if isinstance(st, ast.If):
                collect_ifexp(st.test, env)
                surfaces.extend(_relational_surfaces(
                    _condition_to_sympy(st.test, dict(env))))
                walk(st.body, dict(env))
                walk(st.orelse, dict(env))
                for sub in ast.walk(st):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        env.pop(sub.id, None)
                continue
            if isinstance(st, (ast.Try, ast.With)):
                walk(getattr(st, "body", []), env)
                continue
            collect_ifexp(st, env)
            if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                    and isinstance(st.targets[0], ast.Name):
                name = st.targets[0].id
                try:
                    value = _expr_to_sympy(st.value, dict(env))
                except NotSymbolic:
                    value = None
                if value is None or isinstance(value, tuple):
                    env.pop(name, None)
                else:
                    env[name] = value
                continue
            for sub in ast.walk(st):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    env.pop(sub.id, None)

    try:
        walk(body, dict(params))
    except (NotSymbolic, TypeError, ValueError, AttributeError, RecursionError):
        return [], {}
    wanted = set(params.values())
    kept = [s for s in dict.fromkeys(surfaces)
            if s.free_symbols and s.free_symbols <= wanted]
    return kept, params


def diff_surfaces(expr) -> list:
    """Intent:
        The switching surfaces of every Piecewise condition inside
        `expr`: where a case-split difference changes arm.
    """
    out: list = []
    for pw in expr.atoms(sympy.Piecewise):
        for _value, cond in pw.args:
            out.extend(_relational_surfaces(cond))
    return list(dict.fromkeys(out))


def surface_points(surfaces: list, symbols: dict, candidates: dict,
                   limit: int = _MAX_POINTS) -> list[dict]:
    """Intent:
        Points on the given surfaces: each surface solved for one
        symbol at a time, the symbols its solution depends on taking
        every combination of their `candidates` values. Keys are the
        names of `symbols` (a name -> Symbol table); a point holds only
        the coordinates its surface fixed.

    Notes:
        Only a real, finite solution is kept. A symbol with no entry in
        `candidates` is never solved for and never varied (a fixed
        literal argument, say), and a solution depending on one is
        dropped. Checking a point against the domain is the caller's.
        Unbounded `sympy.solve` work belongs under the caller's
        wall-clock cap.
    """
    name_of = {sym: name for name, sym in symbols.items()}
    out: list[dict] = []
    for surface in surfaces:
        for sym in sorted(surface.free_symbols, key=str):
            name = name_of.get(sym)
            if name is None or name not in candidates:
                continue
            try:
                sols = sympy.solve(sympy.Eq(surface, 0), sym)
            except (NotImplementedError, TypeError, ValueError):
                continue
            for sol in sols if isinstance(sols, list) else ():
                others = sorted(sol.free_symbols, key=str)
                if any(name_of.get(o) not in candidates for o in others):
                    continue
                other_names = [name_of[o] for o in others]
                combos = itertools.islice(itertools.product(
                    *(candidates[n] for n in other_names)), _MAX_COMBOS)
                for combo in combos:
                    try:
                        value = complex(sol.subs(dict(zip(others, combo))).evalf())
                    except (TypeError, ValueError, ZeroDivisionError):
                        continue
                    if abs(value.imag) > 1e-12 or not math.isfinite(value.real):
                        continue
                    point = dict(zip(other_names, combo))
                    point[name] = value.real
                    if point not in out:
                        out.append(point)
                    if len(out) >= limit:
                        return out
    return out
