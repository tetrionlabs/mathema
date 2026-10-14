# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Whether a region of real points, stated as a sympy boolean over
relations, holds no point at all.

The region a function's guards leave is the admitted box (each
parameter's interval) cut by the union of its raise conditions, and it
can read several parameters at once (`x < y`, `x + y >= 0`). A region
over one parameter is decided by its solution set. A region over
several is put in disjunctive normal form, and each conjunction of
linear relations is decided by Fourier-Motzkin elimination over the
reals, strict and non-strict inequalities kept apart. A relation that
is not linear, or a `!=`, is dropped from its conjunction: the
conjunction then admits at least as many points as before, so a
conjunction shown empty without it is empty with it.

The answer is True only when emptiness is shown; anything undecided
(a nonlinear conjunction that stays feasible once relaxed, too many
disjuncts or constraints, the wall-clock cap) is False.
"""
from __future__ import annotations

import sympy

_MAX_DISJUNCTS = 64
_MAX_CONSTRAINTS = 400


def region_is_empty(region) -> bool:
    """Intent:
        Whether `region`, a sympy boolean over real symbols, is shown to
        hold at no real point. False whenever that is not shown.

    Notes:
        Runs under the fast wall-clock cap; a timeout is False.
    """
    from ._timeout import FAST_TIMEOUT_SECONDS, _WallClockExpired, _with_timeout
    try:
        return bool(_with_timeout(lambda: _decide(region),
                                  FAST_TIMEOUT_SECONDS))
    except (TimeoutError, _WallClockExpired):
        return False
    except Exception:
        return False


def _decide(region) -> bool:
    """Intent:
        The undecorated decision `region_is_empty` caps.

    Raises:
        Whatever sympy raises on a form it cannot handle; the caller
        reads that as undecided.
    """
    if region is sympy.false:
        return True
    if region is sympy.true:
        return False
    free = region.free_symbols
    if not free:
        return bool(region == sympy.false)
    if len(free) == 1:
        return region.as_set() is sympy.S.EmptySet
    dnf = sympy.to_dnf(region, simplify=False)
    disjuncts = dnf.args if isinstance(dnf, sympy.Or) else (dnf,)
    if len(disjuncts) > _MAX_DISJUNCTS:
        return False
    syms = sorted(free, key=str)
    for term in disjuncts:
        if term is sympy.false:
            continue
        if term is sympy.true:
            return False
        literals = term.args if isinstance(term, sympy.And) else (term,)
        if not _conjunction_infeasible(literals, syms):
            return False
    return True


def _constraint(literal, syms):
    """Intent:
        A relation as linear constraints `(coeffs, const, strict)`, each
        meaning `sum(coeffs[s] * s) + const > 0` when strict and `>= 0`
        otherwise. An equality is two constraints. None for a relation
        that is not linear in `syms` with real number coefficients, and
        for anything that is not an order relation or an equality.
    """
    if isinstance(literal, (sympy.StrictGreaterThan, sympy.GreaterThan)):
        expr, strict = literal.lhs - literal.rhs, \
            isinstance(literal, sympy.StrictGreaterThan)
        pairs = [(expr, strict)]
    elif isinstance(literal, (sympy.StrictLessThan, sympy.LessThan)):
        expr, strict = literal.rhs - literal.lhs, \
            isinstance(literal, sympy.StrictLessThan)
        pairs = [(expr, strict)]
    elif isinstance(literal, sympy.Equality):
        expr = literal.lhs - literal.rhs
        pairs = [(expr, False), (-expr, False)]
    else:
        return None
    out = []
    for expr, strict in pairs:
        expr = sympy.expand(expr)
        coeffs = {}
        for s in syms:
            c = expr.coeff(s, 1)
            if c.free_symbols or not c.is_real:
                return None
            if c != 0:
                coeffs[s] = c
        const = sympy.expand(expr - sum(c * s for s, c in coeffs.items()))
        if const.free_symbols or not const.is_real:
            return None
        out.append((coeffs, const, strict))
    return out


def _conjunction_infeasible(literals, syms) -> bool:
    """Intent:
        Whether the conjunction of `literals` has no real solution,
        shown by Fourier-Motzkin elimination of every symbol over the
        linear relations among them. Relations that are not linear are
        left out, which can only enlarge the solution set.
    """
    rows: list = []
    for literal in literals:
        if literal is sympy.false:
            return True
        if literal is sympy.true:
            continue
        found = _constraint(literal, syms)
        if found is not None:
            rows.extend(found)
    for s in syms:
        pos = [r for r in rows if r[0].get(s, 0) > 0]
        neg = [r for r in rows if r[0].get(s, 0) < 0]
        rest = [r for r in rows if s not in r[0]]
        for cp, kp, sp in pos:
            for cn, kn, sn in neg:
                a, b = cp[s], -cn[s]
                coeffs = {}
                for t in set(cp) | set(cn):
                    if t == s:
                        continue
                    v = cp.get(t, 0) / a + cn.get(t, 0) / b
                    if v != 0:
                        coeffs[t] = v
                rest.append((coeffs, kp / a + kn / b, sp or sn))
                if len(rest) > _MAX_CONSTRAINTS:
                    return False
        rows = rest
    for coeffs, const, strict in rows:
        if coeffs:
            return False
        holds = (const > 0) if strict else (const >= 0)
        if holds is sympy.false or holds is False:
            return True
    return False
