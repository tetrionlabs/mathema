# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Alternative closed forms and variable substitutions for a symbolic
expression: a gallery of equivalence-preserving rewrites (factor,
trigsimp, logcombine, ...) and a registry of the classic substitutions
of analysis (t = log(x), t = exp(x), the Weierstrass half-angle, ...),
each carrying its own applicability condition and exact endpoint
mapping so a claim's domain travels through the change of variable.

Both registries serve two consumers: the extensive proof ladder
(`mathema.symbolic._extensive`), which tries them when the ordinary
decision procedure comes back undecided, and the public
`mathema.forms` API, which exposes them directly as "other closed
forms of this code". A rewrite is only ever applied to symbols that
already carry the claim's domain assumptions, so sympy combines or
splits logs and powers exactly when the domain makes it sound, never
by force."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import sympy


@dataclass(frozen=True)
class Rewrite:
    """One equivalence-preserving rewrite of an expression: `name` is
    the label a proof sketch or a rendered form carries, `apply` maps
    the expression to its rewritten form, and `wants` is a cheap test
    for whether the expression contains anything this rewrite could
    act on at all."""
    name: str
    apply: Callable[[sympy.Basic], sympy.Basic]
    wants: Callable[[sympy.Basic], bool]


def _has_trig(e: sympy.Basic) -> bool:
    return e.has(sympy.sin, sympy.cos, sympy.tan, sympy.sinh,
                 sympy.cosh, sympy.tanh)


_REWRITES: list[Rewrite] = [
    Rewrite("factor", sympy.factor, lambda e: True),
    Rewrite("cancel", sympy.cancel, lambda e: True),
    Rewrite("together", sympy.together, lambda e: True),
    Rewrite("expand", sympy.expand, lambda e: True),
    Rewrite("trigsimp", sympy.trigsimp, _has_trig),
    Rewrite("expand_trig", sympy.expand_trig, _has_trig),
    Rewrite("rewrite as exp", lambda e: e.rewrite(sympy.exp), _has_trig),
    Rewrite("rewrite as conjugate", lambda e: e.rewrite(sympy.conjugate),
            lambda e: e.has(sympy.Abs) and any(
                s.is_real is not True for s in e.free_symbols)),
    Rewrite("expand_complex", sympy.expand_complex,
            lambda e: any(s.is_real is not True for s in e.free_symbols)
            or e.has(sympy.I)),
    Rewrite("logcombine", sympy.logcombine, lambda e: e.has(sympy.log)),
    Rewrite("expand_log", sympy.expand_log, lambda e: e.has(sympy.log)),
    Rewrite("powdenest", sympy.powdenest, lambda e: e.has(sympy.Pow)),
    Rewrite("radsimp", sympy.radsimp, lambda e: e.has(sympy.Pow)),
]


def rewrites() -> tuple[Rewrite, ...]:
    """The rewrite gallery, in the order the extensive ladder tries it."""
    return tuple(_REWRITES)


def rewrite_forms(expr: sympy.Basic):
    """Yield `(name, form)` for every gallery rewrite that applies to
    `expr` and produces something structurally different from it.
    A rewrite that raises is skipped, never fatal: the gallery exists
    to offer forms, not to demand every member handle every shape."""
    for rw in _REWRITES:
        try:
            if not rw.wants(expr):
                continue
            form = rw.apply(expr)
        except Exception:
            continue
        if form != expr:
            yield rw.name, form


@dataclass(frozen=True)
class Substitution:
    """One classic change of variable, `t = g(x)`.

    `name` is the display form ("t = log(x)"); `requires` states, in
    plain text, the domain condition under which the substitution is a
    monotone bijection ("x > 0"); `forward` maps a value of x to the
    corresponding t (used on domain endpoints); `inverse` maps the new
    variable back (`x = g⁻¹(t)`, substituted into the expression);
    `detect` says whether an expression contains the shape this
    substitution is known to help with; `applicable` checks the domain
    condition on exact interval endpoints; `monotone` is "increasing"
    or "decreasing" and controls whether the mapped endpoints swap.

    A substitution transforms a sign or equality question without
    changing its answer: g is a bijection from the declared interval
    onto its image, so `expr(x)` and `expr(g⁻¹(t))` take exactly the
    same set of values. That is what lets a proof found in t-space
    stand as a proof of the original claim."""
    name: str
    requires: str
    forward: Callable[[sympy.Basic], sympy.Basic]
    inverse: Callable[[sympy.Basic], sympy.Basic]
    detect: Callable[[sympy.Basic, sympy.Symbol], bool]
    applicable: Callable[[sympy.Basic, sympy.Basic], bool]
    monotone: str = "increasing"


def _contains_call(expr: sympy.Basic, func, x: sympy.Symbol) -> bool:
    return any(x in a.free_symbols for a in expr.atoms(func))


def _contains_sqrt_of(expr: sympy.Basic, x: sympy.Symbol) -> bool:
    return any(x in p.base.free_symbols and p.exp == sympy.Rational(1, 2)
               for p in expr.atoms(sympy.Pow))


def _contains_reciprocal_of(expr: sympy.Basic, x: sympy.Symbol) -> bool:
    return any(x in p.base.free_symbols
               and p.exp.is_number and bool(p.exp < 0)
               for p in expr.atoms(sympy.Pow))


def _contains_trig_of(expr: sympy.Basic, x: sympy.Symbol) -> bool:
    return any(_contains_call(expr, fn, x)
               for fn in (sympy.sin, sympy.cos, sympy.tan))


def _safe_true(pred) -> bool:
    try:
        return bool(pred)
    except TypeError:
        return False


_SUBSTITUTIONS: list[Substitution] = [
    Substitution(
        name="t = log(x)", requires="x > 0",
        forward=sympy.log, inverse=sympy.exp,
        detect=lambda e, x: _contains_call(e, sympy.log, x),
        applicable=lambda lo, hi: _safe_true(lo > 0)),
    Substitution(
        name="t = exp(x)", requires="always",
        forward=sympy.exp, inverse=sympy.log,
        detect=lambda e, x: _contains_call(e, sympy.exp, x),
        applicable=lambda lo, hi: True),
    Substitution(
        name="t = sqrt(x)", requires="x >= 0",
        forward=sympy.sqrt, inverse=lambda t: t ** 2,
        detect=_contains_sqrt_of,
        applicable=lambda lo, hi: _safe_true(lo >= 0)),
    Substitution(
        name="t = 1/x", requires="0 outside the interval",
        forward=lambda x: 1 / x, inverse=lambda t: 1 / t,
        detect=_contains_reciprocal_of,
        applicable=lambda lo, hi: _safe_true(lo > 0) or _safe_true(hi < 0),
        monotone="decreasing"),
    Substitution(
        name="t = sin(x)", requires="-pi/2 <= x <= pi/2",
        forward=sympy.sin, inverse=sympy.asin,
        detect=_contains_trig_of,
        applicable=lambda lo, hi: (_safe_true(lo >= -sympy.pi / 2)
                                   and _safe_true(hi <= sympy.pi / 2))),
    Substitution(
        name="t = cos(x)", requires="0 <= x <= pi",
        forward=sympy.cos, inverse=sympy.acos,
        detect=_contains_trig_of,
        applicable=lambda lo, hi: (_safe_true(lo >= 0)
                                   and _safe_true(hi <= sympy.pi)),
        monotone="decreasing"),
    Substitution(
        name="t = tan(x/2)", requires="-pi < x < pi",
        forward=lambda x: sympy.tan(x / 2), inverse=lambda t: 2 * sympy.atan(t),
        detect=_contains_trig_of,
        applicable=lambda lo, hi: _safe_true(lo > -sympy.pi) and _safe_true(hi < sympy.pi)),
    Substitution(
        name="t = tanh(x)", requires="always",
        forward=sympy.tanh, inverse=sympy.atanh,
        detect=lambda e, x: _contains_call(e, sympy.tanh, x),
        applicable=lambda lo, hi: True),
    Substitution(
        name="t = erf(x)", requires="always",
        forward=sympy.erf, inverse=sympy.erfinv,
        detect=lambda e, x: _contains_call(e, sympy.erf, x),
        applicable=lambda lo, hi: True),
    Substitution(
        name="t = exp(-x)", requires="always",
        forward=lambda x: sympy.exp(-x), inverse=lambda t: -sympy.log(t),
        detect=lambda e, x: any(
            x in a.args[0].free_symbols and a.args[0].could_extract_minus_sign()
            for a in e.atoms(sympy.exp)),
        applicable=lambda lo, hi: True,
        monotone="decreasing"),
    Substitution(
        name="t = atan(x)", requires="always",
        forward=sympy.atan, inverse=sympy.tan,
        detect=lambda e, x: x in e.free_symbols,
        applicable=lambda lo, hi: (not _safe_true(getattr(lo, "is_finite", None))
                                   or not _safe_true(getattr(hi, "is_finite", None)))),
]


def substitutions() -> tuple[Substitution, ...]:
    """The substitution library, in the order the extensive ladder
    tries it. Built-ins first, then registered extras in registration
    order."""
    return tuple(_SUBSTITUTIONS)


def register_substitution(sub: Substitution) -> None:
    """Add a substitution to the library, making it available both to
    `mathema.forms.substituted_forms` and to the extensive proof
    ladder. Raises `ValueError` on a duplicate `name`: substitutions
    are identified by name in proof sketches, so two of them sharing
    one would make a proof's own record ambiguous."""
    if any(s.name == sub.name for s in _SUBSTITUTIONS):
        raise ValueError(f"a substitution named {sub.name!r} is already registered")
    _SUBSTITUTIONS.append(sub)


def substituted_problem(sub: Substitution, expr: sympy.Basic, x: sympy.Symbol,
                        t: sympy.Symbol, lo, hi,
                        closed_lo: bool = True, closed_hi: bool = True):
    """Intent:
        Carry one variable of a bounded sign/equality question through
        `sub`: the expression with `x` replaced by the inverse image of
        `t`, plus `t`'s own interval as the image of `[lo, hi]` under
        the forward map (endpoints and closedness swapped for a
        decreasing substitution).

    Notes:
        Returns `(new_expr, new_lo, new_hi, new_closed_lo,
        new_closed_hi)`, endpoints exact sympy values, or `None` when
        anything fails to evaluate. Monotonicity is `sub`'s own
        declared fact, valid under its `applicable` condition, the
        caller is expected to have checked that first.
    """
    try:
        new_expr = expr.subs(x, sub.inverse(t))
        new_lo, new_hi = sub.forward(lo), sub.forward(hi)
        if sub.monotone == "decreasing":
            new_lo, new_hi = new_hi, new_lo
            closed_lo, closed_hi = closed_hi, closed_lo
        return new_expr, new_lo, new_hi, closed_lo, closed_hi
    except Exception:
        return None
