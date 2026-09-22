# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The extensive proof ladder: what a `route="derive"` claim gets when
the ordinary decision procedure comes back undecided and the caller
opted into `extensive=True`. Instead of simply re-running the same
procedure with a longer wall clock, the ladder works through genuinely
different strategies, each individually capped at the fast timeout:

1. exact real-root analysis for polynomial differences (Sturm-based
   isolation, so the answer is exact, never sampled);
2. interval refinement: bisect the domain box and retake the interval
   hull on each cell, the standard cure for interval arithmetic's
   dependency problem;
3. the rewrite gallery: retry the decision on factor/trigsimp/
   logcombine/... forms of the difference;
4. the substitution library: carry the question through a known change
   of variable (t = log(x), t = exp(x), ...) with the domain mapped
   exactly, then retry the decision, root analysis, and refinement on
   the transformed problem;
5. one final retry of the base procedure under the widened
   (EXTENSIVE_TIMEOUT_SECONDS) cap.

Every rung is sound on its own terms: root isolation and interval
hulls are rigorous, rewrites are equivalence-preserving under the
domain assumptions already baked into the symbols, and a substitution
is a monotone bijection on the declared interval, so a verdict in the
transformed space is a verdict on the original claim. Anything the
ladder can't settle stays undecided, and the names of everything
attempted are handed back for the sketch."""
from __future__ import annotations

import sympy

from .._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                        FAST_TIMEOUT_SECONDS, _with_timeout)
from ..domain import Interval, bound_context as domain_bound_context, bound_to_sympy_set
from ._forms import rewrite_forms, substituted_problem, substitutions
from ._proof_support import (
    ProofResult, _decide_relation, _exact_endpoint, _humanize,
    _interval_hull, _prove_relation,
)

_MAX_REFINEMENT_CELLS = 64


def _bound_interval(bound):
    """Intent:
        A declared bound as `(lo, hi, closed_lo, closed_hi,
        plain_interval)` with exact endpoints, or `None` when the bound
        has no usable interval hull.

    Notes:
        `plain_interval` is True only when the bound's sympy set is a
        real interval outright, no integer lattice, no exclusions, no
        union. Proving over the hull is sound either way (the hull
        contains the domain); exhibiting a counterexample point is only
        sound when the point is a member, which the hull alone
        guarantees just for a plain interval.
    """
    try:
        sset = bound_to_sympy_set(bound)
        lo, hi = _exact_endpoint(sset.inf), _exact_endpoint(sset.sup)
    except Exception:
        return None
    plain = isinstance(sset, sympy.Interval)
    closed_lo = not getattr(sset, "left_open", False)
    closed_hi = not getattr(sset, "right_open", False)
    return lo, hi, closed_lo, closed_hi, plain


def _rational_cover(lo, hi):
    """Intent:
        Rational endpoints enclosing `[lo, hi]`, for handing an
        interval with irrational (e.g. substitution-mapped) endpoints
        to rational root isolation.

    Notes:
        Returns `(rlo, rhi, widened)`. A widened cover is sound for
        proving (the true interval is inside it) but not for producing
        a counterexample point, which might land in the slack; the
        caller must suppress disproof when `widened` is True.
    """
    if getattr(lo, "is_rational", False) and getattr(hi, "is_rational", False):
        return lo, hi, False
    try:
        scale = sympy.Integer(10) ** 9
        rlo = sympy.Rational(sympy.floor(lo * scale), scale)
        rhi = sympy.Rational(sympy.ceiling(hi * scale), scale)
        return rlo, rhi, True
    except Exception:
        return None


def _sturm_decide(diff, relation: str, domain: dict, params: dict) -> ProofResult | None:
    """Intent:
        Decide a univariate polynomial relation exactly by real-root
        isolation: no roots in the interval means constant sign
        (settled by one exact evaluation); with roots, one exact
        rational sample in each root-free gap covers every sign the
        polynomial takes.

    Notes:
        Only fires for a difference polynomial in exactly one
        domain-bounded symbol with rational coefficients. Every sample
        point is rational, so each sign is computed exactly; this
        rung never trusts floating point. Roots themselves evaluate to
        zero, which satisfies a non-strict ordering, so they need no
        separate check there; for `!=` a root inside the domain is the
        counterexample itself.
    """
    if relation in ("==", "~="):
        # equality of a nonzero polynomial difference is already
        # falsifiable by the base procedure; nothing exact to add here
        # that _decide_equality's is_zero path doesn't do.
        return None
    free = diff.free_symbols
    named = {p: s for p, s in params.items() if s in free}
    if len(free) != 1 or len(named) != 1:
        return None
    (pname, sym), = named.items()
    if domain.get(pname) is None:
        return None
    hull = _bound_interval(domain[pname])
    if hull is None:
        return None
    lo, hi, closed_lo, closed_hi, plain = hull
    if not (getattr(lo, "is_finite", False) and getattr(hi, "is_finite", False)):
        return None
    cover = _rational_cover(lo, hi)
    if cover is None:
        return None
    rlo, rhi, widened = cover
    may_disprove = plain and not widened
    try:
        exact = sympy.nsimplify(diff, rational=True)
        poly = sympy.Poly(exact, sym)
        dom = poly.get_domain()
        if not (dom.is_ZZ or dom.is_QQ) or poly.degree() < 1:
            return None
        if bool(rlo >= rhi):
            return None
        isolating = poly.intervals(inf=rlo, sup=rhi)
    except Exception:
        return None

    def value_at(pt):
        return exact.subs(sym, pt)

    # a degenerate isolating interval (a == b) IS an exact rational
    # root; a root at an endpoint the domain excludes is not in the
    # domain at all.
    def root_excluded(a, b):
        return (a == b) and ((a == rlo and not closed_lo and not widened)
                             or (a == rhi and not closed_hi and not widened))

    live = [(a, b) for (a, b), _mult in isolating if not root_excluded(a, b)]

    if relation == "!=":
        if not live:
            return ProofResult("proven", sketch=f"{_humanize(diff)} has no real "
                               f"root on the declared interval (exact root "
                               "isolation), so it is never zero",
                               meta={"mathema.derive_route": "sturm"})
        if may_disprove:
            try:
                roots = sympy.real_roots(poly)
                inside = [r for r in roots
                          if (bool(rlo < r) or (closed_lo and bool(rlo <= r)))
                          and (bool(r < rhi) or (closed_hi and bool(r <= rhi)))]
            except Exception:
                inside = []
            if inside:
                return ProofResult("disproven",
                                   sketch=f"{_humanize(diff)} has a real root on "
                                          "the declared interval (exact root isolation)",
                                   counterexample=f"{pname} = {sympy.nsimplify(inside[0])}")
        return None

    # every maximal sign region between consecutive roots needs one
    # exact rational sample whose polynomial value is nonzero. The
    # isolating intervals' own endpoints supply them: sorted disjoint
    # intervals mean b_i lies strictly between root_i and root_{i+1}
    # whenever it isn't itself a root, which the nonzero check
    # verifies. A region for which no candidate verifies leaves the
    # rung undecided, never sampled around.
    def region_sample(candidates):
        for pt in candidates:
            if bool(rlo <= pt) and bool(pt <= rhi) and value_at(pt) != 0:
                return pt
        return None

    samples = []
    if not isolating:
        samples.append((rlo + rhi) / 2)
    else:
        bounds = [pair for (pair, _mult) in isolating]
        first_a, first_b = bounds[0]
        if not (first_a == first_b == rlo):
            pt = region_sample([rlo, first_a, (rlo + first_a) / 2])
            if pt is None:
                return None
            samples.append(pt)
        for (a1, b1), (a2, b2) in zip(bounds, bounds[1:]):
            pt = region_sample([b1, a2, (b1 + a2) / 2])
            if pt is None:
                return None
            samples.append(pt)
        last_a, last_b = bounds[-1]
        if not (last_a == last_b == rhi):
            pt = region_sample([rhi, last_b, (last_b + rhi) / 2])
            if pt is None:
                return None
            samples.append(pt)

    want_nonneg = relation == ">="
    bad = [pt for pt in samples
           if (value_at(pt).is_negative if want_nonneg
               else value_at(pt).is_positive)]
    if not bad:
        return ProofResult("proven", sketch=f"sign of {_humanize(diff)} settled "
                           "exactly by real-root isolation: every root-free "
                           "region of the declared interval has the required sign",
                           meta={"mathema.derive_route": "sturm"})
    if may_disprove:
        witness = next((pt for pt in bad
                        if (bool(rlo < pt) or closed_lo)
                        and (bool(pt < rhi) or closed_hi)), None)
        if witness is not None:
            return ProofResult("disproven", sketch=f"exact evaluation between the "
                               f"real roots of {_humanize(diff)} found the opposite sign",
                               counterexample=f"{pname} = {witness}")
    return None


def _refine_decide(diff, relation: str, domain: dict, params: dict,
                   max_cells: int = _MAX_REFINEMENT_CELLS) -> ProofResult | None:
    """Intent:
        Decide a sign (or never-zero) question by branch-and-bound
        interval refinement: bisect the domain box wherever the hull
        straddles, certify each cell whose hull lands clear.

    Notes:
        The cure for the plain interval pass's dependency problem
        (`x*sin(x)` on `[-1, 1]` straddles as one box but certifies as
        two half-boxes). Sound in both directions: a cell's hull
        contains its true range, so a hull wholly on the wrong side is
        a real violation region (its midpoint is the counterexample);
        reported only when every bound is a plain interval, since a
        midpoint of a lattice or exclusion domain's hull may not be a
        member. Cells and depth are capped; an unbounded or
        non-interval dimension is never split.
    """
    if relation not in (">=", "<=", "!="):
        return None
    target = -diff if relation == "<=" else diff
    named = {p: s for p, s in params.items() if s in target.free_symbols}
    if not named:
        return None
    dims = {}
    plain_all = True
    for pname, sym in named.items():
        bound = domain.get(pname)
        hull = _bound_interval(bound) if bound is not None else None
        if hull is None:
            return None
        lo, hi, _cl, _ch, plain = hull
        plain_all = plain_all and plain
        dims[sym] = (lo, hi)
    if any(s not in dims for s in target.free_symbols):
        return None

    def hull_of(cell):
        box = {s: (sympy.AccumBounds(lo, hi) if lo != hi else lo)
               for s, (lo, hi) in cell.items()}
        h = _interval_hull(target, box)
        if h is None:
            return None
        if isinstance(h, sympy.AccumBounds):
            return h.min, h.max
        return h, h

    from collections import deque
    worklist = deque([dims])
    cells = 1
    exhausted = False
    while worklist:
        cell = worklist.popleft()
        got = hull_of(cell)
        if got is None:
            return None
        h_lo, h_hi = got
        s_lo, s_hi = _sign_of(h_lo), _sign_of(h_hi)
        if relation == "!=":
            if s_lo == 1 or s_hi == -1:
                continue
        else:
            if s_lo in (0, 1):
                continue
            if s_hi == -1:
                if not plain_all:
                    return None
                witness = ", ".join(
                    f"{p} = {sympy.nsimplify((lo + hi) / 2)}"
                    for p, s in named.items()
                    for lo, hi in [cell[s]])
                return ProofResult(
                    "disproven",
                    sketch="interval refinement found a region where the "
                           "difference is entirely on the wrong side of zero",
                    counterexample=witness)
        # straddling cell: split its widest finite dimension. Once the
        # cell budget is spent, stop splitting but keep scanning what
        # remains; a later cell may still disprove outright, and the
        # exhausted flag blocks any "proven" from an incomplete sweep.
        if cells >= max_cells:
            exhausted = True
            continue
        widest, width = None, None
        for s, (lo, hi) in cell.items():
            if not getattr(hi - lo, "is_finite", False):
                continue   # an infinite dimension has no midpoint to split at
            try:
                w = float(hi - lo)
            except (TypeError, OverflowError):
                continue
            if w > 0 and (width is None or w > width):
                widest, width = s, w
        if widest is None:
            exhausted = True
            continue
        lo, hi = cell[widest]
        mid = (lo + hi) / 2
        for half in ((lo, mid), (mid, hi)):
            sub = dict(cell)
            sub[widest] = half
            worklist.append(sub)
        cells += 1
    if exhausted:
        return None
    kind = ("never zero" if relation == "!="
            else "has the required sign everywhere")
    return ProofResult("proven", sketch=f"interval refinement over "
                       f"{cells} cells of the domain box certifies that "
                       f"{_humanize(diff)} {kind}",
                       meta={"mathema.derive_route": "refined_interval"})


def _sign_of(value):
    """Intent:
        Three-valued sign of a constant sympy expression: 1, 0, -1, or
        `None` when it can't be called with certainty.

    Notes:
        Exact assumptions first (a Rational, an expression sympy can
        prove positive). A symbolic constant like `sin(1/2)/2 - 1/2`
        resolves neither way exactly, so a 30-digit numeric evaluation
        decides it, but only outside a wide safety margin, inside the
        margin the answer stays `None` and the caller must treat the
        value as possibly either side of zero, never guess.
    """
    from ._proof_support import _verified_sign
    return _verified_sign(value)


def _capped(fn):
    """Intent:
        Run one ladder attempt under the fast wall-clock cap, folding a
        timeout or any sympy internal error into "this rung declines".

    Notes:
        The extensive budget is spent across many small capped attempts
        rather than one long one; a rung that hangs or crashes must
        never take the whole ladder down with it.
    """
    try:
        return _with_timeout(fn, FAST_TIMEOUT_SECONDS)
    except Exception:
        return None


def _substituted_symbol(name: str, lo, hi, closed_lo: bool, closed_hi: bool):
    """Intent:
        The fresh symbol for a substituted variable, carrying whatever
        sign assumption its mapped interval proves, t = sqrt(x) on a
        nonnegative x gets nonnegative=True, which is what lets sympy
        collapse sqrt(t**2*s**2) to t*s and expose a sum of squares.
    """
    from ..domain import Interval as _Interval, _interval_sign_kwargs
    try:
        kwargs = _interval_sign_kwargs(_Interval(lo, hi, closed_lo, closed_hi))
    except Exception:
        kwargs = None
    return sympy.Symbol(name, **(kwargs or {"real": True}))


def _joint_substituted_attempts(diff, relation: str, domain: dict, params: dict,
                                attempted: list) -> ProofResult | None:
    """Intent:
        Apply one substitution to EVERY parameter it fits,
        simultaneously, the transform that exposes symmetric
        structure a one-variable change can't: t = sqrt(a), s = sqrt(b)
        turns the AM-GM difference into ((t - s)^2)/2, a visible sum of
        squares.

    Notes:
        Only runs for two or more applicable parameters (the single
        case is `_substituted_attempts`' own loop). Disproof witnesses
        stay in the substituted variables, named in the sketch.
    """
    for sub in substitutions():
        fits = []
        for pname, sym in params.items():
            if sym not in diff.free_symbols:
                continue
            bound = domain.get(pname)
            hull = ((-sympy.oo, sympy.oo, False, False, True) if bound is None
                    else _bound_interval(bound))
            if hull is None:
                continue
            lo, hi, closed_lo, closed_hi, _plain = hull
            try:
                if sub.detect(diff, sym) and sub.applicable(lo, hi):
                    fits.append((pname, sym, lo, hi, closed_lo, closed_hi))
            except Exception:
                continue
        if len(fits) < 2:
            continue
        new_diff = diff
        new_domain = dict(domain)
        new_params = dict(params)
        replacements = {}
        ok = True
        for pname, sym, lo, hi, closed_lo, closed_hi in fits:
            carried = substituted_problem(sub, new_diff, sym,
                                          sympy.Symbol("_placeholder"),
                                          lo, hi, closed_lo, closed_hi)
            if carried is None:
                ok = False
                break
            _expr, new_lo, new_hi, n_cl, n_ch = carried
            t = _substituted_symbol(f"t_{pname}", new_lo, new_hi, n_cl, n_ch)
            replacements[sym] = sub.inverse(t)
            new_domain[pname] = Interval(new_lo, new_hi, n_cl, n_ch)
            new_params[pname] = t
        if not ok:
            continue
        try:
            new_diff = diff.subs(replacements, simultaneous=True)
        except Exception:
            continue
        names = ", ".join(pname for pname, *_ in fits)
        attempted.append(f"{sub.name} jointly on {names}")
        result = _attempt_transformed(new_diff, relation, new_domain, new_params)
        if result is not None and result.status in ("proven", "disproven"):
            meta = dict(result.meta)
            meta["mathema.derive_route"] = f"substitution:{sub.name}"
            where = (" (witness in the substituted variables)"
                     if result.status == "disproven" and result.counterexample
                     else "")
            return ProofResult(result.status,
                               sketch=f"after substituting {sub.name} jointly "
                                      f"for {names}: {result.sketch}{where}",
                               counterexample=result.counterexample, meta=meta)
    return None


def _attempt_transformed(new_diff, relation: str, new_domain: dict,
                         new_params: dict) -> ProofResult | None:
    """Intent:
        The shared mini-ladder for a substituted problem: simplify,
        base decision under the mapped bound context, then exact root
        analysis and interval refinement in the new variables.
    """
    if not new_diff.has(sympy.Integral, sympy.core.function.AppliedUndef):
        # simplify() doits a deferred Integral (wrongly, for the very
        # shapes the residue machinery exists for); when one is
        # present, _decide_relation's guarded evaluation must own it.
        simplified = _capped(lambda: sympy.simplify(new_diff))
        if simplified is not None:
            new_diff = simplified
    ctx_parts = []
    for n, s in new_params.items():
        b = new_domain.get(n)
        if b is None:
            continue
        pred = domain_bound_context(s, b)
        if pred is not None:
            ctx_parts.append(pred)
    ctx = sympy.And(*ctx_parts) if ctx_parts else None
    result = _capped(lambda: _decide_relation(
        new_diff, sympy.S.Zero, relation, new_domain, ctx, new_params))
    if result is None or result.status == "undecided":
        result = (_capped(lambda: _sturm_decide(
                      new_diff, relation, new_domain, new_params))
                  or _capped(lambda: _refine_decide(
                      new_diff, relation, new_domain, new_params)))
    return result


def _substituted_attempts(diff, relation: str, domain: dict, params: dict,
                          attempted: list) -> ProofResult | None:
    """Intent:
        Carry the question through every applicable registered
        substitution and retry the base decision, root analysis, and
        interval refinement on the transformed problem.

    Notes:
        One variable is substituted at a time; the other parameters
        keep their own bounds and symbols. A disproof found in the
        substituted space is reported with the witness left in the new
        variable, named in the sketch, since mapping it back through
        the inverse is not always exactly renderable.
    """
    for pname, sym in params.items():
        if sym not in diff.free_symbols:
            continue
        bound = domain.get(pname)
        if bound is None:
            # an undeclared parameter ranges over all reals, and a
            # substitution that compactifies (t = atan(x) maps the whole
            # line into (-pi/2, pi/2)) is exactly what can make such a
            # claim decidable.
            hull = (-sympy.oo, sympy.oo, False, False, True)
        else:
            hull = _bound_interval(bound)
        if hull is None:
            continue
        lo, hi, closed_lo, closed_hi, _plain = hull
        for sub in substitutions():
            try:
                if not sub.detect(diff, sym) or not sub.applicable(lo, hi):
                    continue
            except Exception:
                continue
            t = sympy.Symbol(f"t_{pname}", real=True)
            carried = substituted_problem(sub, diff, sym, t, lo, hi,
                                          closed_lo, closed_hi)
            if carried is None:
                continue
            new_diff, new_lo, new_hi, n_cl, n_ch = carried
            attempted.append(f"{sub.name} on {pname}")
            if not new_diff.has(sympy.Integral, sympy.core.function.AppliedUndef):
                simplified = _capped(lambda: sympy.simplify(new_diff))
                if simplified is not None:
                    new_diff = simplified
            new_domain = dict(domain)
            new_domain[pname] = Interval(new_lo, new_hi, n_cl, n_ch)
            new_params = dict(params)
            new_params[pname] = t
            ctx_parts = []
            for n, s in new_params.items():
                b = new_domain.get(n)
                if b is None:
                    continue
                pred = domain_bound_context(s, b)
                if pred is not None:
                    ctx_parts.append(pred)
            ctx = sympy.And(*ctx_parts) if ctx_parts else None
            result = _capped(lambda: _decide_relation(
                new_diff, sympy.S.Zero, relation, new_domain, ctx, new_params))
            if result is None or result.status == "undecided":
                result = (_capped(lambda: _sturm_decide(
                              new_diff, relation, new_domain, new_params))
                          or _capped(lambda: _refine_decide(
                              new_diff, relation, new_domain, new_params)))
            if result is not None and result.status in ("proven", "disproven"):
                counterexample = result.counterexample
                where = ""
                if result.status == "disproven" and counterexample:
                    mapped = _map_witness_back(counterexample, pname, sub)
                    if mapped is not None:
                        counterexample = mapped
                    else:
                        where = f" (witness in the substituted variable {t})"
                meta = dict(result.meta)
                meta["mathema.derive_route"] = f"substitution:{sub.name}"
                return ProofResult(result.status,
                                   sketch=f"after substituting {sub.name} for "
                                          f"{pname}: {result.sketch}{where}",
                                   counterexample=counterexample,
                                   meta=meta)
    return None


def _map_witness_back(counterexample: str, pname: str, sub) -> str | None:
    """Intent:
        A counterexample found in the substituted variable, mapped back
        to the original parameter through the substitution's own exact
        inverse: a witness at t = v corresponds to the original point
        x = g⁻¹(v).

    Notes:
        The counterexample string is the refinement/root rungs' own
        `"name = value[, name = value]"` form with the substituted
        parameter still under its original name; only that entry is
        remapped. `None` when the string doesn't parse or the mapped
        value doesn't evaluate to a finite real, the caller then
        keeps the t-space witness, labeled as such.
    """
    try:
        parts = []
        for part in counterexample.split(", "):
            name, _, value_text = part.partition(" = ")
            if name.strip() != pname:
                parts.append(part)
                continue
            t_value = sympy.sympify(value_text)
            x_value = sub.inverse(t_value)
            approx = x_value.evalf(6)
            if not approx.is_comparable or not approx.is_finite:
                return None
            rendered = str(x_value) if x_value.is_rational else f"{x_value} (~ {approx})"
            parts.append(f"{pname} = {rendered}")
        return ", ".join(parts)
    except Exception:
        return None


# the fast-pass rescue strategies moved to their own module once they
# stopped being extensive-only (they run on every fast pass); these
# re-exports keep existing imports working
from ._strategies import (  # noqa: E402
    _FAST_RESCUES as _FAST_RESCUES,
    _gap_substituted_attempt as _gap_substituted_attempt,
    _has_symmetry_candidate as _has_symmetry_candidate,
    _symmetric_groups as _symmetric_groups,
    fast_gap_attempt as fast_gap_attempt,
    fast_loggamma_attempt as fast_loggamma_attempt,
    fast_rescue_attempts as fast_rescue_attempts,
    fast_squared_attempt as fast_squared_attempt,
)


def extensive_ladder(lhs, rhs, relation: str, domain: dict, bound_context,
                     params: dict, opaque=None) -> tuple[ProofResult | None, list]:
    """Intent:
        Work through the strategy ladder for a base-undecided relation
        and report both the outcome and everything that was tried.

    Notes:
        Returns `(result, attempted)`: `result` is a proven or
        disproven ProofResult (None when nothing settled it) and
        `attempted` lists the strategies engaged, for the caller to
        fold into the undecided sketch; a claim record should say
        what the wider search actually did, not just that it happened.
        Rungs run cheapest-first; the widened single-shot retry of the
        base procedure runs last, preserving what `extensive` used to
        mean before the ladder existed.
    """
    attempted: list = []
    diff = lhs - rhs
    from ._proof_support import _has_equality_constraint
    assumed_surface = _has_equality_constraint(bound_context)

    # the ladder's aggregate deadline: however many rungs there are,
    # the total wall time is bounded. Each per-rung cap still applies;
    # this stops a long rung sequence (a rich rewrite gallery, many
    # substitution candidates) from summing to minutes.
    import time as _time
    _deadline = _time.monotonic() + 3 * EXTENSIVE_TIMEOUT_SECONDS

    def _over_budget() -> bool:
        return _time.monotonic() > _deadline

    def _sound(result):
        # a rung that reasons over the whole domain box (root isolation,
        # cell refinement) cannot DISPROVE a claim assumed onto an
        # equality surface: its "violating" region may lie entirely off
        # the feasible set. Proofs over the box remain sound (the
        # surface is inside it); only the disproofs are demoted.
        if (result is not None and result.status == "disproven"
                and assumed_surface):
            return None
        return result

    attempted.append("exact real-root isolation")
    result = _sound(_capped(lambda: _sturm_decide(diff, relation, domain, params)))
    if result is not None and result.status in ("proven", "disproven"):
        return result, attempted

    attempted.append("interval refinement")
    result = _sound(_capped(lambda: _refine_decide(diff, relation, domain, params)))
    if result is not None and result.status in ("proven", "disproven"):
        return result, attempted

    from ._smt import available as _smt_available, nlsat_decide
    if _smt_available():
        # the optional mathema[smt] extra: nonlinear-real-arithmetic
        # decision by z3's nlsat, complete for the polynomial/rational
        # fragment. _capped's alarm cannot interrupt the solver's own
        # C loop, so the rung sets z3's native millisecond timeout too.
        attempted.append("nlsat quantifier elimination")
        result = _sound(_capped(lambda: nlsat_decide(
            diff, relation, domain, params, bound_context)))
        if result is not None and result.status in ("proven", "disproven"):
            return result, attempted

    for name, form in rewrite_forms(diff):
        if _over_budget():
            attempted.append("stopped at the aggregate budget")
            return None, attempted
        attempted.append(name)
        result = _capped(lambda: _decide_relation(
            form, sympy.S.Zero, relation, domain, bound_context, params))
        if result is not None and result.status in ("proven", "disproven"):
            meta = dict(result.meta)
            meta["mathema.derive_route"] = f"rewrite:{name}"
            return ProofResult(result.status,
                               sketch=f"decided after {name}: {result.sketch}",
                               counterexample=result.counterexample,
                               meta=meta), attempted

    if _over_budget():
        attempted.append("stopped at the aggregate budget")
        return None, attempted
    result = _sound(_substituted_attempts(diff, relation, domain, params,
                                          attempted))
    if result is not None:
        return result, attempted

    result = _sound(_capped(lambda: _joint_substituted_attempts(
        diff, relation, domain, params, attempted)))
    if result is not None and result.status in ("proven", "disproven"):
        return result, attempted

    if diff.has(sympy.Integral):
        # a deferred definite integral sympy's own machinery couldn't
        # settle (or settled in a way the earlier rungs couldn't use):
        # the contour patterns evaluate it by residues, side conditions
        # discharged exactly against the declared domain (see
        # _residues).
        from ._residues import residue_attempts
        attempted.append("residue contour evaluation")
        # twice the usual rung budget: pole enumeration plus the
        # numeric referee against sympy's own integration are real
        # work, and this is the last substantive rung before the
        # widened retry.
        try:
            result = _with_timeout(lambda: residue_attempts(
                lhs, rhs, relation, domain, bound_context, params),
                2 * FAST_TIMEOUT_SECONDS)
        except Exception:
            result = None
        result = _sound(result)
        if result is not None and result.status in ("proven", "disproven"):
            return result, attempted

    # the nonnegative-gap WLOG rung is not here: it now runs in the fast
    # pass (see fast_gap_attempt in _prove.try_prove), before the ladder
    # is ever entered, so a symmetric inequality proves without
    # extensive=True and is never attempted twice.

    if _over_budget():
        attempted.append("stopped at the aggregate budget")
        return None, attempted
    attempted.append("widened wall-clock retry")
    result = _prove_relation(lhs, rhs, relation, domain, bound_context, params,
                             opaque=opaque, extensive=True)
    if result.status in ("proven", "disproven"):
        meta = dict(result.meta)
        meta["mathema.derive_route"] = "widened_retry"
        return ProofResult(result.status, sketch=result.sketch,
                           counterexample=result.counterexample,
                           quantifier=result.quantifier, meta=meta), attempted
    return None, attempted
