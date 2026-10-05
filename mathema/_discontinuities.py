# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where a computation is discontinuous, and how much of a domain a run
covered.

A rounding step, a remainder, a sign or a branch makes the code's
value discontinuous at known places: floor, ceil and int() where
their argument is a whole number, round where it is a half-integer
(Python rounds a half to even), a remainder where its quotient is
whole, sign at zero, a comparison or a branch where its two sides are
equal. Float arithmetic misplaces exactly those points (7 / 25 * 100 is
28.000000000000004, so its ceil is 29), so the computation line runs
them on purpose. They are read from the lifted body, or from the
claim's own text when the body does not lift.

On a finite integer domain the points are enumerated exactly; on a real
interval the argument is solved for each whole number (or half) its
range reaches, up to a cap, and each solution is run with its float
neighbours one ulp either side.
"""
from __future__ import annotations

import ast
import itertools
import math
from dataclasses import dataclass
from fractions import Fraction

import sympy

#: the most discontinuity values solved for along one argument of a
#: real interval; the rest are counted as skipped
SOLVE_CAP = 200


@dataclass
class Discontinuity:
    """One discontinuity of a computation: `expr` over the parameters, and
    `kind`, `whole` (an integer), `half` (a half-integer) or `zero`."""
    expr: object
    kind: str
    words: str


@dataclass
class Coverage:
    """How many trials a run made and why, for the note's one wording
    (`words`)."""
    total: "int | None" = None
    full: bool = False
    at_discontinuities: int = 0
    discontinuity_words: str = ""
    edge_cases: int = 0
    skipped: int = 0

    def words(self, trials: int) -> str:
        """The coverage of a run in one place:
        `(every point of the domain: 34,190)` for a full sweep, else
        `(3,105 trials: 412 at discontinuities of ceil(...), 7 edge
        cases, 2,686 random; the domain has 34,190 points)`."""
        if self.full and self.total is not None and trials >= self.total:
            return f"(every point of the domain: {self.total:,})"
        if self.full and self.total is not None:
            return (f"({trials:,} trials, every point of the domain in order "
                    f"up to the first failure; the domain has {self.total:,} "
                    f"points)")
        parts = []
        if self.at_discontinuities:
            parts.append(f"{self.at_discontinuities:,} at discontinuities of "
                         f"{self.discontinuity_words}")
        if self.edge_cases:
            parts.append(f"{self.edge_cases:,} edge cases")
        random_count = max(0, trials - self.at_discontinuities - self.edge_cases)
        parts.append(f"{random_count:,} random")
        text = f"({trials:,} trials: " + ", ".join(parts)
        if self.skipped:
            text += (f"; {self.skipped:,} discontinuities past the cap of "
                     f"{SOLVE_CAP} not run")
        if self.total is not None:
            text += f"; the domain has {self.total:,} points"
        return text + ")"


def _plain(expr):
    return expr.xreplace({s: sympy.Symbol(str(s)) for s in expr.free_symbols})


def _from_expr(expr) -> list:
    """The discontinuities a sympy expression carries."""
    found: list = []
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, (sympy.floor, sympy.ceiling)):
            word = "ceil" if isinstance(node, sympy.ceiling) else "floor"
            found.append(Discontinuity(_plain(node.args[0]), "whole",
                                       f"{word}({node.args[0]})"))
        elif isinstance(node, sympy.Mod):
            a, n = node.args
            found.append(Discontinuity(_plain(a / n), "whole", f"{a} % {n}"))
        elif isinstance(node, sympy.sign):
            found.append(Discontinuity(_plain(node.args[0]), "zero",
                                       f"sign({node.args[0]})"))
        elif isinstance(node, sympy.Piecewise):
            for _value, cond in node.args:
                found.extend(_from_condition(cond))
        elif isinstance(node, (sympy.Min, sympy.Max)) and len(node.args) == 2:
            a, b = node.args
            found.append(Discontinuity(_plain(a - b), "zero", f"{node}"))
    return found


def _from_condition(cond) -> list:
    out: list = []
    if isinstance(cond, (sympy.And, sympy.Or)):
        for arg in cond.args:
            out.extend(_from_condition(arg))
    elif isinstance(cond, sympy.Not):
        out.extend(_from_condition(cond.args[0]))
    elif isinstance(cond, sympy.core.relational.Relational):
        out.append(Discontinuity(_plain(cond.lhs - cond.rhs), "zero", f"{cond}"))
    return out


_CLAIM_CALLS = {"floor": "whole", "ceil": "whole", "int": "whole",
                "round": "half", "sign": "zero"}


def _from_claim_text(cj, params) -> list:
    """The discontinuities in the claim's own text, outside any call of
    f: rounding calls, remainders and comparisons over the parameters."""
    found: list = []
    names = {p: sympy.Symbol(p) for p in params}
    for side in (cj.lhs, cj.rhs):
        try:
            tree = ast.parse(side or "0", mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in _CLAIM_CALLS and len(node.args) == 1:
                target, kind, word = node.args[0], _CLAIM_CALLS[node.func.id], node.func.id
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                target = ast.BinOp(node.left, ast.Div(), node.right)
                kind, word = "whole", None
            if target is None:
                continue
            text = ast.unparse(target)
            if "f(" in text:
                continue
            try:
                expr = sympy.sympify(text, locals=names)
            except Exception:
                continue
            found.append(Discontinuity(_plain(expr), kind,
                                       f"{word}({expr})" if word else
                                       ast.unparse(node)))
    return found


def discontinuities(cj, fn, facts) -> list:
    """Intent:
        Every discontinuity of the computation the claim reads: from the
        lifted body of `fn` when it lifts, else from the claim's own
        text; duplicates removed.
    """
    found: list = []
    try:
        from .symbolic import lift
        lifted = lift(fn, facts)
    except Exception:
        lifted = None
    if lifted is not None and not isinstance(lifted.expr, tuple):
        found.extend(_from_expr(lifted.expr))
    elif lifted is None:
        # a branched body as one Piecewise, each branch with its guard
        try:
            from .symbolic._conditioned import lift_piecewise
            whole = lift_piecewise(fn, facts)
        except Exception:
            whole = None
        expr = getattr(getattr(whole, "lifted", None), "expr", None) \
            if whole is not None else None
        if expr is None and whole is not None:
            expr = getattr(whole, "expr", None)
        if expr is not None and not isinstance(expr, tuple):
            found.extend(_from_expr(expr))
    found.extend(_from_claim_text(cj, facts.params))
    unique: dict = {}
    for d in found:
        unique.setdefault((sympy.srepr(d.expr), d.kind), d)
    return list(unique.values())


def words_of(found: list) -> str:
    return ", ".join(dict.fromkeys(d.words for d in found))


def _hits(value: Fraction, kind: str) -> bool:
    if kind == "whole":
        return value.denominator == 1
    if kind == "half":
        return value.denominator == 2
    return value == 0


def on_grid(found: list, points: list) -> list:
    """Intent:
        The points of a finite domain (`points`, dicts by parameter
        name) where some discontinuity's argument reaches it,
        decided in exact rational arithmetic.
    """
    if not found:
        return []
    syms = sorted({s for d in found for s in d.expr.free_symbols}, key=str)
    evaluators = []
    for d in found:
        try:
            evaluators.append((sympy.lambdify(syms, d.expr, modules=[{}]), d.kind))
        except Exception:
            continue
    out = []
    for pt in points:
        if any(str(s) not in pt for s in syms):
            continue
        try:
            args = [Fraction(pt[str(s)]) for s in syms]
        except (TypeError, ValueError):
            continue
        for ev, kind in evaluators:
            try:
                value = ev(*args)
                value = value if isinstance(value, Fraction) else Fraction(value)
            except Exception:
                continue
            if _hits(value, kind):
                out.append(pt)
                break
    return out


def on_interval(found: list, name: str, lo: float, hi: float) -> "tuple[list, int]":
    """Intent:
        `(values, skipped)`: the values of parameter `name` in [lo, hi]
        where a discontinuity's argument in that one parameter reaches
        it, solved exactly for each whole number (or half) its range
        reaches, each with its float neighbours one ulp either side; at
        most `SOLVE_CAP` targets per argument, the rest counted in
        `skipped`.
    """
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    sym = sympy.Symbol(name)
    values: list = []
    skipped = 0
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
        return values, skipped
    for d in found:
        if d.expr.free_symbols != {sym}:
            continue
        try:
            image = sympy.Interval(sympy.Rational(repr(lo)), sympy.Rational(repr(hi)))
            span = sympy.imageset(sympy.Lambda(sym, d.expr), image)
            low, high = float(span.inf), float(span.sup)
        except Exception:
            continue
        if not (math.isfinite(low) and math.isfinite(high)):
            continue
        if d.kind == "zero":
            targets = [0] if low <= 0 <= high else []
        else:
            first = math.ceil(low - (0.5 if d.kind == "half" else 0))
            last = math.floor(high - (0.5 if d.kind == "half" else 0))
            count = max(0, last - first + 1)
            if count > SOLVE_CAP:
                skipped += count - SOLVE_CAP
                last = first + SOLVE_CAP - 1
            targets = [k + (Fraction(1, 2) if d.kind == "half" else 0)
                       for k in range(first, last + 1)]
        for k in targets:
            try:
                roots = _with_timeout(
                    lambda k=k: sympy.solveset(sympy.Eq(d.expr, sympy.nsimplify(k)),
                                               sym, sympy.Interval(lo, hi)),
                    FAST_TIMEOUT_SECONDS)
            except Exception:
                continue
            if not isinstance(roots, sympy.FiniteSet):
                continue
            for r in roots:
                try:
                    x = float(r)
                except (TypeError, ValueError):
                    continue
                for v in (math.nextafter(x, -math.inf), x, math.nextafter(x, math.inf)):
                    if lo <= v <= hi:
                        values.append(v)
    return list(dict.fromkeys(values)), skipped


def grid_points(names: list, grid: dict) -> list:
    return [dict(zip(names, combo))
            for combo in itertools.product(*(grid[n] for n in names))]
