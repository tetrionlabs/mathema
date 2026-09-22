# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Executable closed forms: a sympy expression compiled back into a
runnable callable, with the provenance and domain-validity facts that
make evidence from running it honest.

A compiled form is mathema's RECONSTRUCTION of some mathematics, a
lifted function body, a rewrite-gallery form, the resolved intermediate
of a stalled proof, never the user's own code. Numeric evidence from
evaluating one is evidence about the symbolic form, and only
transitively (through the lift) about any code it came from, so every
consumer states that provenance: the numeric-fallback route is
`probe:lifted_numeric`, its ceiling is `holds`, and the record names
the form that was actually sampled.

A compiled form evaluates; it does not print. Turning one into
compilable source in another language is not part of this module, and
nothing here emits foreign code.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

import sympy

from ._sampling import _RNG_SEED, _synth_scalar

__all__ = ["CompiledForm", "compile_form", "numeric_check"]
_NUMERIC_TRIALS = 60


@dataclass(frozen=True)
class CompiledForm:
    """One executable closed form: the expression, the callable
    compiled from it, the ordered free-variable names the callable
    takes, where the form came from (`provenance`, e.g. the rewrites
    applied), the conditions under which it is a valid rendering of its
    origin (`validity`), and the numeric backend that runs it."""
    expr: "sympy.Expr"
    fn: "Callable"
    names: tuple
    provenance: tuple = ()
    validity: str = ""
    backend: str = "math"


def compile_form(expr, names=None, provenance=(), validity="",
                 backend="math",
                 pseudo_infinity=None) -> "CompiledForm | None":
    """Intent:
        Lambdify `expr` over `names` (defaulting to its sorted free
        symbols) into a CompiledForm, or None when the expression
        contains something the backend cannot run (an unevaluated
        Integral under the plain math backend, an unmapped special
        function).

    Notes:
        `pseudo_infinity` is the claim's resolved (lo, hi) operational
        infinity (records.pseudo_infinity_range). An unevaluated
        Integral with an infinite bound is read at that range, the
        same empirical reading of infinity every other consumer of a
        `let |inf| be v` binding uses, and the truncation is stated
        in the form's validity. Without a declared operational
        infinity there is no honest finite reading, so the form
        declines to compile.
    """
    free = sorted(expr.free_symbols, key=str)
    if names is None:
        names = [str(s) for s in free]
    by_name = {str(s): s for s in free}
    syms = [by_name.get(n, sympy.Symbol(n)) for n in names]
    if expr.has(sympy.Sum, sympy.Product, sympy.Limit, sympy.Derivative):
        return None   # unevaluated calculus needs its own treatment
    if expr.has(sympy.Integral):
        # a definite integral sympy couldn't close still evaluates
        # NUMERICALLY: substitute the point, then evalf, which routes
        # through mpmath's quadrature internally, no new dependency.
        # Each call is real numeric integration, so the "quad" backend
        # tag tells consumers to spend far fewer trials. FINITE ranges
        # only: quadrature over an infinite (often oscillatory) range
        # can be silently inaccurate, and a wrong value here would
        # manufacture a counterexample, a true residue-family
        # identity was once "falsified" exactly this way. An infinite
        # bound therefore compiles only when the claim binds an
        # operational infinity, and is read at that declared range.
        has_infinite = any(
            getattr(bound, "is_infinite", False)
            for integral in expr.atoms(sympy.Integral)
            for limits in integral.limits for bound in limits[1:])
        if has_infinite:
            if pseudo_infinity is None:
                return None
            lo, hi = pseudo_infinity
            expr = expr.subs({sympy.oo: sympy.Float(hi),
                              -sympy.oo: sympy.Float(lo)})
            reading = (f"infinite integration bounds read at the "
                       f"declared operational infinity [{lo:g}, {hi:g}]")
            validity = f"{validity}; {reading}" if validity else reading
        def quad_fn(*vals, _expr=expr, _syms=tuple(syms)):
            value = _expr.subs(dict(zip(_syms, vals))).evalf(15)
            if not getattr(value, "is_number", False):
                raise ValueError("integral did not resolve numerically")
            c = complex(value)
            if abs(c.imag) > 1e-9:
                raise ValueError("complex-valued integral")
            return float(c.real)
        return CompiledForm(expr=expr, fn=quad_fn, names=tuple(names),
                            provenance=tuple(provenance), validity=validity,
                            backend="quad")
    modules = "mpmath" if backend == "mpmath" else ["math"]
    try:
        raw = sympy.lambdify(syms, expr, modules=modules)
    except Exception:
        return None
    return CompiledForm(expr=expr, fn=raw, names=tuple(names),
                        provenance=tuple(provenance), validity=validity,
                        backend=backend)


def numeric_check(lhs: CompiledForm, rhs: CompiledForm, relation: str,
                  domain: dict, tolerance: float = 1e-9,
                  admits=None, trials: int = _NUMERIC_TRIALS):
    """Intent:
        Sample the two compiled sides over the declared domain and
        adjudicate the relation numerically: the fallback evidence for
        a claim whose symbolic comparison stalled and whose original
        form the probe route cannot evaluate (a d()/integrate()/Sum()
        law). Returns `(verdict, checked, counterexample_text)` with
        verdict one of "holds" / "falsified" / None (not enough
        evaluable samples). The ceiling is holds; this is sampling,
        never proof, and it samples the RECONSTRUCTION, which the
        caller must say.

    Notes:
        Strict relations get no tolerance credit and equality gets the
        claim's own tolerance, matching the probe loop's comparison
        rules exactly. `admits`, when given, filters candidate points
        (an `assuming` surface).
    """
    names = sorted(set(lhs.names) | set(rhs.names))
    rng = random.Random(_RNG_SEED)
    checked = 0
    for _ in range(trials):
        point = {}
        for n in names:
            bound = domain.get(n)
            b = None
            if isinstance(bound, tuple):
                try:
                    b = (float(bound[0]), float(bound[1]))
                except (TypeError, ValueError):
                    b = None
            point[n] = _synth_scalar(rng, b)
        if admits is not None and not admits(point):
            continue
        try:
            lv = lhs.fn(*[point[n] for n in lhs.names])
            rv = rhs.fn(*[point[n] for n in rhs.names])
        except Exception:
            continue
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and v == v and abs(v) != float("inf") for v in (lv, rv)):
            continue
        tol = tolerance
        if "quad" in (lhs.backend, rhs.backend):
            # numeric integration carries its own error: a quad-backed
            # comparison only counts a failure past a magnitude-scaled
            # margin, so quadrature noise never manufactures a witness
            tol = tolerance + 1e-6 * max(abs(lv), abs(rv), 1.0)
        ok = (abs(lv - rv) <= tol if relation in ("==", "~=") else
              abs(lv - rv) > tol if relation == "!=" else
              lv <= rv + tol if relation == "<=" else
              lv >= rv - tol if relation == ">=" else
              lv < rv if relation == "<" else
              lv > rv if relation == ">" else None)
        if ok is None:
            return None, checked, None
        checked += 1
        if not ok:
            coords = ", ".join(f"{n}={point[n]:.6g}" for n in names)
            return "falsified", checked, f"{coords}: {lv!r} vs {rv!r}"
    if checked >= max(6, trials // 4):
        # the floor bends for expensive backends (a quad-backed check
        # runs 12 trials, each a real numeric integration): six
        # agreeing evaluations is still evidence, thin sampling below
        # that is not
        return "holds", checked, None
    return None, checked, None
