# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The nlsat rung: a stuck polynomial sign question decided by z3's
nonlinear-real-arithmetic procedure, as one capped attempt on the
extensive ladder.

Nonlinear real arithmetic, polynomial and rational equalities and
inequalities, radicals encoded through auxiliary variables, Abs/Min/Max
as if-then-else terms, is decidable, and at small arity usually
decided in milliseconds. The rung asks whether the claim's NEGATION has
any model inside the declared box: no model is a proof (the sketch
names the oracle); a model is only ever reported after sympy's own
exact arithmetic re-confirms the violation at that point, so a disproof
never rests on the solver or on the translation. Anything the
translation cannot express exactly (a transcendental function, an
unusable bound) declines to the later rungs.

The `z3-solver` dependency is the optional `mathema[smt]` extra; with
it absent, `available()` is False and the ladder skips the rung
silently.
"""
from __future__ import annotations

from fractions import Fraction

import sympy

from .._timeout import FAST_TIMEOUT_SECONDS


def available() -> bool:
    """Whether the optional z3 dependency is importable."""
    try:
        import z3  # noqa: F401
    except ImportError:
        return False
    return True


class _Untranslatable(Exception):
    """Intent:
        An expression outside the exact translation's vocabulary,
        the rung declines, it never approximates.
    """


class _Translator:
    """Intent:
        One exact sympy -> z3 translation: parameters become Real (or
        Int, when the symbol carries the integer assumption) constants,
        numbers become exact rationals, and a radical becomes an
        auxiliary variable with its defining polynomial constraint.
        `constraints` collects those side constraints; the caller adds
        them to the solver alongside the query.
    """

    def __init__(self, z3mod, params: dict):
        self.z3 = z3mod
        self.vars: dict = {}
        self.constraints: list = []
        self._aux: dict = {}
        for name, sym in params.items():
            self.vars[sym] = (z3mod.Int(name) if sym.is_integer
                              else z3mod.Real(name))

    def _rational(self, value) -> "object":
        q = Fraction(value.p, value.q) if isinstance(value, sympy.Rational) \
            else Fraction(float(value))
        return self.z3.RealVal(f"{q.numerator}/{q.denominator}")

    def _radical(self, base_expr, q: int):
        key = (sympy.srepr(base_expr), q)
        cached = self._aux.get(key)
        if cached is not None:
            return cached
        base = self.expr(base_expr)
        y = self.z3.Real(f"_rad{len(self._aux)}")
        self.constraints.append(y ** q == base)
        if q % 2 == 0:
            # an even root exists only for a nonnegative base, and is
            # the nonnegative branch by convention
            self.constraints.append(y >= 0)
            self.constraints.append(base >= 0)
        self._aux[key] = y
        return y

    def expr(self, e):
        z3 = self.z3
        if e in self.vars:
            return self.vars[e]
        if isinstance(e, sympy.Symbol):
            raise _Untranslatable(f"free symbol {e} is not a parameter")
        if isinstance(e, (sympy.Integer, sympy.Rational)):
            return self._rational(e)
        if isinstance(e, sympy.Float):
            return self._rational(e)
        if e is sympy.pi or e is sympy.E or e.is_infinite:
            raise _Untranslatable(f"non-rational constant {e}")
        if isinstance(e, sympy.Add):
            out = self.expr(e.args[0])
            for a in e.args[1:]:
                out = out + self.expr(a)
            return out
        if isinstance(e, sympy.Mul):
            out = self.expr(e.args[0])
            for a in e.args[1:]:
                out = out * self.expr(a)
            return out
        if isinstance(e, sympy.Pow):
            base, exp = e.args
            if isinstance(exp, sympy.Integer):
                n = int(exp)
                b = self.expr(base)
                if n >= 0:
                    return b ** n
                return self.z3.RealVal(1) / (b ** (-n))
            if isinstance(exp, sympy.Rational):
                y = self._radical(base, int(exp.q))
                p = int(exp.p)
                return y ** p if p >= 0 else self.z3.RealVal(1) / (y ** (-p))
            raise _Untranslatable(f"non-rational exponent in {e}")
        if isinstance(e, sympy.Abs):
            t = self.expr(e.args[0])
            return z3.If(t >= 0, t, -t)
        if isinstance(e, (sympy.Min, sympy.Max)):
            parts = [self.expr(a) for a in e.args]
            out = parts[0]
            for t in parts[1:]:
                out = (z3.If(t < out, t, out) if isinstance(e, sympy.Min)
                       else z3.If(t > out, t, out))
            return out
        if isinstance(e, sympy.Piecewise):
            # right-to-left If chain; the final branch must be a
            # catch-all (condition True) for the translation to be total
            pairs = list(e.args)
            last_expr, last_cond = pairs[-1]
            if last_cond is not sympy.true:
                raise _Untranslatable(f"piecewise without a catch-all: {e}")
            out = self.expr(last_expr)
            for value, cond in reversed(pairs[:-1]):
                out = z3.If(self.condition(cond), self.expr(value), out)
            return out
        raise _Untranslatable(f"{type(e).__name__} has no exact translation")

    def condition(self, c):
        z3 = self.z3
        if c is sympy.true:
            return z3.BoolVal(True)
        if c is sympy.false:
            return z3.BoolVal(False)
        if isinstance(c, sympy.And):
            return z3.And(*[self.condition(a) for a in c.args])
        if isinstance(c, sympy.Or):
            return z3.Or(*[self.condition(a) for a in c.args])
        if isinstance(c, sympy.Not):
            return z3.Not(self.condition(c.args[0]))
        if isinstance(c, sympy.Rel):
            lhs, rhs = self.expr(c.lhs), self.expr(c.rhs)
            op = c.rel_op
            if op == "==":
                return lhs == rhs
            if op == "!=":
                return lhs != rhs
            if op == "<=":
                return lhs <= rhs
            if op == "<":
                return lhs < rhs
            if op == ">=":
                return lhs >= rhs
            if op == ">":
                return lhs > rhs
        raise _Untranslatable(f"condition {c} has no exact translation")


_NEGATIONS = {">=": "<", ">": "<=", "<=": ">", "<": ">=",
              "==": "!=", "!=": "=="}


def nlsat_decide(diff, relation: str, domain: dict, params: dict,
                 bound_context=None) -> "object | None":
    """Intent:
        Decide `diff <relation> 0` over the declared box by asking z3
        whether the negation has a model. Returns a proven or disproven
        ProofResult, or None (untranslatable, unknown, timeout, or the
        extra absent).

    Notes:
        A proof is sound over a superset of the true region, so a
        non-plain bound contributes its interval hull and an assumed
        context that fails to translate is simply dropped, but in
        either widening, a model may lie outside the real domain, so
        the rung then reports proofs only. A model that does survive is
        re-checked by exact sympy substitution before any disproof is
        returned: the witness stands on sympy's own arithmetic, and the
        downstream corroboration gate still demands the executed
        witness like any other derive disproof.
    """
    if relation not in _NEGATIONS:
        return None
    if not available():
        return None
    import z3

    from ._extensive import _bound_interval
    from ._proof_support import ProofResult

    named = {p: s for p, s in params.items() if s in diff.free_symbols}
    if not named or len(named) > 6:
        return None

    translator = _Translator(z3, named)
    proofs_only = False
    box = []
    try:
        target = translator.expr(diff)
        zero = z3.RealVal(0)
        negated = _NEGATIONS[relation]
        query = {"<": target < zero, "<=": target <= zero,
                 ">": target > zero, ">=": target >= zero,
                 "==": target == zero, "!=": target != zero}[negated]
        for pname, sym in named.items():
            bound = domain.get(pname)
            if bound is None:
                continue
            hull = _bound_interval(bound)
            if hull is None:
                return None
            lo, hi, closed_lo, closed_hi, plain = hull
            var = translator.vars[sym]
            if getattr(lo, "is_finite", False):
                lo_t = translator.expr(sympy.nsimplify(lo, rational=True))
                box.append(var >= lo_t if closed_lo else var > lo_t)
            if getattr(hi, "is_finite", False):
                hi_t = translator.expr(sympy.nsimplify(hi, rational=True))
                box.append(var <= hi_t if closed_hi else var < hi_t)
            if not plain:
                # the hull is a superset of the real bound (an
                # exclusion, an integer lattice rendered real): sound
                # for a proof, not for a witness
                proofs_only = True
        if bound_context is not None:
            try:
                box.append(translator.condition(bound_context))
            except _Untranslatable:
                # dropping an assumed constraint widens the region:
                # proofs stay sound, witnesses may lie off the surface
                proofs_only = True
    except _Untranslatable:
        return None

    solver = z3.Solver()
    solver.set("timeout", max(1, FAST_TIMEOUT_SECONDS) * 1000)
    # the wall-clock timeout is BEST-EFFORT: nlsat's algebraic-number
    # kernel (exactly what radical auxiliary variables exercise) can
    # run long stretches without polling it; confirmed live on
    # multi-term root-sum shapes (Minkowski p=3, IMO 2001 P2) running
    # 40s+ past the cap. rlimit is z3's deterministic resource
    # counter, polled where the timer is not: every proof this rung
    # has produced uses under 10^5 units, and the hanging shapes burn
    # millions without progress, so this cap is ~100x headroom for
    # real work and a prompt, deterministic "unknown" for the rest.
    solver.set("rlimit", 10_000_000)
    for c in box + translator.constraints:
        solver.add(c)
    solver.add(query)
    outcome = solver.check()

    if outcome == z3.unsat:
        return ProofResult(
            "proven",
            sketch=f"the negation has no solution in the declared domain "
                   f"(decided by nlsat nonlinear real arithmetic; "
                   f"z3 {z3.get_version_string()})",
            meta={"mathema.derive_route": "smt_nlsat"})
    if outcome != z3.sat or proofs_only:
        return None

    # a model is a CANDIDATE witness: re-establish the violation with
    # exact sympy arithmetic before reporting anything
    model = solver.model()
    point = {}
    for pname, sym in named.items():
        val = model.eval(translator.vars[sym], model_completion=True)
        try:
            if sym.is_integer:
                point[sym] = sympy.Integer(val.as_long())
            else:
                point[sym] = sympy.Rational(
                    val.numerator_as_long(), val.denominator_as_long())
        except (AttributeError, z3.Z3Exception):
            return None   # an irrational algebraic model value: decline
    try:
        value = diff.subs(point)
        holds_at_point = {"<": value < 0, "<=": value <= 0,
                          ">": value > 0, ">=": value >= 0,
                          "==": sympy.Eq(value, 0),
                          "!=": sympy.Ne(value, 0)}[negated]
        if holds_at_point is not sympy.true and holds_at_point is not True:
            return None
    except Exception:
        return None
    witness = ", ".join(f"{p} = {sympy.nsimplify(v)}"
                        for p, v in sorted(point.items(), key=lambda kv: str(kv[0])))
    return ProofResult(
        "disproven",
        sketch="nlsat found a point violating the relation, re-confirmed "
               "by exact arithmetic",
        counterexample=witness,
        meta={"mathema.derive_route": "smt_nlsat"})
