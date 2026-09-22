# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The fast-pass rescue strategies: what a derive claim gets when the
ordinary decision procedure comes back undecided, BEFORE any extensive
ladder is considered. Each rescue has a near-free structural gate (a
radical present, loggamma present, a symmetric group of same-bounded
parameters), caps its own sympy work at the fast wall clock, and is
sound as an equivalence or a WLOG argument, so a claim that cannot
benefit pays almost nothing, and one that can gets a genuine proof on
the ordinary fast path.

Lived inside `_extensive.py` while the rungs were extensive-only; a
module of its own now that they run on every fast pass (the name
"extensive" stopped describing them). `_extensive` re-exports these
names for compatibility."""
from __future__ import annotations

import sympy

from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
from ._proof_support import ProofResult


def _capped(fn):
    """One rescue attempt under the fast wall-clock cap: a timeout or
    a sympy internal error folds into "this rescue declines"."""
    try:
        return _with_timeout(fn, FAST_TIMEOUT_SECONDS)
    except Exception:
        return None


def _has_symmetry_candidate(relation: str, domain: dict, params: dict) -> bool:
    """Intent:
        A zero-sympy precheck for whether the nonnegative-gap rung could
        possibly apply: the relation is an ordering (the only kind a
        WLOG order helps), and at least two parameters share an
        identical bound (the minimum for a group to order). Cheap enough
        to run on every undecided ordering claim before touching sympy.

    Notes:
        Necessary, not sufficient, an actual symmetry check
        (`_symmetric_groups`) still has to confirm the invariance. This
        just lets a claim that cannot benefit skip the sympy work
        entirely.
    """
    if relation not in (">=", "<=", ">", "<"):
        return False
    by_bound: dict = {}
    for name, bound in domain.items():
        if params.get(name) is None:
            continue
        by_bound.setdefault(repr(bound), []).append(name)
    return any(len(names) >= 2 for names in by_bound.values())


def _is_swap_invariant(diff, swap: dict) -> bool:
    """Intent:
        Whether swapping one pair of variables leaves `diff` unchanged,
        cheapest test first: structural identity, then `expand` (closes
        the polynomial case), then `cancel` (the rational case), and
        only then the expensive `simplify`, so a symmetric polynomial
        or rational is confirmed without ever paying for `simplify`.
    """
    d = diff.subs(swap, simultaneous=True) - diff
    if d == 0:
        return True
    for reducer in (sympy.expand, sympy.cancel, sympy.simplify):
        try:
            if reducer(d) == 0:
                return True
        except Exception:
            continue
    return False


def _symmetric_groups(diff, domain: dict, params: dict) -> list:
    """Intent:
        Groups of domain parameters that share an identical bound AND
        under which `diff` is fully permutation-symmetric (invariant
        under every adjacent swap); the groups a WLOG ordering may
        soundly be imposed on.

    Notes:
        Full symmetry is required: a cyclic-only invariance does NOT
        license assuming a total order, so it is not returned. Adjacent
        transpositions generate the symmetric group, so checking those
        suffices.
    """
    by_bound: dict = {}
    for name, bound in domain.items():
        sym = params.get(name)
        if sym is None:
            continue
        by_bound.setdefault(repr(bound), []).append((name, sym))
    groups = []
    for members in by_bound.values():
        if len(members) < 2:
            continue
        syms = [s for _n, s in members]
        if all(_is_swap_invariant(diff, {a: b, b: a})
               for a, b in zip(syms, syms[1:])):
            groups.append(members)
    return groups


def _has_radical(e) -> bool:
    """A fractional-exponent power anywhere in the expression, the
    shape whose comparison squaring can clear."""
    return any(p.exp.is_Rational and p.exp.q != 1
               for p in e.atoms(sympy.Pow))


def fast_squared_attempt(lhs, rhs, relation: str, domain: dict,
                         params: dict, bound_context=None) -> "ProofResult | None":
    """Intent:
        The squaring rewrite for radical comparisons: when both sides
        are provably nonnegative on the domain (sympy's assumption
        engine, no extra work), `A ? B` holds exactly when `A^2 ? B^2`
        does, for every value relation, so a comparison a bare
        radical blocks (QM-AM, GM-HM, Cauchy-Schwarz shapes) is
        re-decided on the squared difference, where the radical is
        gone.

    Notes:
        Sound as an equivalence, both directions: for nonnegative
        sides, squaring preserves ==, <=, <, >=, and > exactly, so a
        proof or a disproof of the squared form transfers (a
        counterexample point falsifies the original at the same
        coordinates). Declines (None) when no radical is present, a
        side is not provably nonnegative, or the squared form still
        does not decide. One round only: a nested-radical claim
        (Minkowski) whose clearing needs isolate-and-square iteration
        stays undecided.
    """
    if relation not in (">=", "<=", ">", "<", "==", "~="):
        return None
    diff = lhs - rhs
    if not _has_radical(diff):
        return None
    # isolate sides: the claim's own spelling may put everything on one
    # side (`f(a,b) >= 0` with f computing sqrt(...) - mean), so the
    # sides squared are the difference's positive terms vs its negated
    # terms; `P - N ? 0` holds exactly when `P ? N` does
    pos, neg = sympy.S.Zero, sympy.S.Zero
    try:
        for term in sympy.Add.make_args(sympy.expand(diff)):
            if term.could_extract_minus_sign():
                neg = neg - term
            else:
                pos = pos + term
    except Exception:
        return None
    if neg == 0 or not (pos.is_nonnegative and neg.is_nonnegative):
        return None
    from ._proof_support import _decide_relation
    try:
        squared = sympy.expand(pos ** 2 - neg ** 2)
    except Exception:
        return None
    result = _capped(lambda: _decide_relation(
        squared, sympy.S.Zero, relation, domain, bound_context, params))
    if result is not None and result.status in ("proven", "disproven"):
        meta = dict(result.meta)
        meta["mathema.derive_route"] = "squared_comparison"
        return ProofResult(
            result.status,
            sketch=f"isolating {pos} against {neg} (both nonnegative on "
                   f"the domain, so squaring preserves the relation); on "
                   f"the squared difference: {result.sketch}",
            counterexample=result.counterexample,
            quantifier=result.quantifier, meta=meta)
    return None


def _loggamma_multiplicative(e):
    """Intent:
        loggamma in its multiplicative home: each `loggamma(a)` with a
        provably positive argument becomes `log(gamma(a))`, the logs
        are combined, and gamma's own functional equation is expanded,
        the log-additive form sympy's thinner log rules cannot close
        (`loggamma(x+1) - loggamma(x) == log(x)`) reduces exactly in
        the gamma world.

    Notes:
        An argument not provably positive keeps its loggamma untouched
        (log(gamma(a)) and loggamma(a) differ off the positive axis;
        branch cuts), so the rewrite is only ever applied where it is
        an identity.
    """
    def repl(a):
        if a.is_positive:
            return sympy.log(sympy.gamma(a))
        return sympy.loggamma(a)
    return sympy.expand_func(sympy.logcombine(e.replace(sympy.loggamma, repl)))


def fast_loggamma_attempt(lhs, rhs, relation: str, domain: dict,
                          params: dict, bound_context=None) -> "ProofResult | None":
    """Intent:
        Normalize-then-prove for loggamma claims: rewrite to the
        multiplicative gamma form (see `_loggamma_multiplicative`) and
        re-decide there. Declines when no loggamma is present or the
        rewrite changes nothing.
    """
    diff = lhs - rhs
    if not diff.has(sympy.loggamma):
        return None
    form = _capped(lambda: _loggamma_multiplicative(diff))
    if form is None or form == diff:
        return None
    from ._proof_support import _decide_relation
    result = _capped(lambda: _decide_relation(
        form, sympy.S.Zero, relation, domain, bound_context, params))
    if result is not None and result.status in ("proven", "disproven"):
        meta = dict(result.meta)
        meta["mathema.derive_route"] = "loggamma_canonicalization"
        return ProofResult(
            result.status,
            sketch=f"after rewriting loggamma to log(gamma) and combining: "
                   f"{result.sketch}",
            counterexample=result.counterexample,
            quantifier=result.quantifier, meta=meta)
    return None


def fast_gap_attempt(lhs, rhs, relation: str, domain: dict,
                     params: dict, bound_context=None) -> "ProofResult | None":
    """Intent:
        The nonnegative-gap WLOG rung, promoted to the fast derive pass:
        when an ordinary proof leaves a fully-symmetric ordering claim
        undecided, impose the sorted order by nonnegative-gap
        substitution and re-decide, all under the fast wall-clock cap. A
        zero-sympy precheck gates the work, so a claim that cannot
        benefit pays almost nothing.

    Notes:
        Same soundness as the (now removed) extensive rung, full
        permutation symmetry proves every order from the sorted one;
        this only changes WHEN it runs, not what it certifies. Returns a
        proven ProofResult or None.
    """
    if not _has_symmetry_candidate(relation, domain, params):
        return None
    return _gap_substituted_attempt(lhs - rhs, relation, domain, params, [])


# the fast-pass rescue rungs, tried in order when the ordinary proof
# comes back undecided: each has a near-free structural gate (a radical
# present, loggamma present, a symmetric group of same-bounded
# parameters) so a claim that cannot benefit pays almost nothing, and
# each caps its own sympy work at the fast wall clock. Ordered
# cheapest-gate-first. A new rescue rung joins by appending here.
_FAST_RESCUES = (fast_squared_attempt, fast_loggamma_attempt,
                 fast_gap_attempt)


def fast_rescue_attempts(lhs, rhs, relation: str, domain: dict,
                         params: dict, bound_context=None) -> "ProofResult | None":
    """Intent:
        Run the fast-pass rescue rungs in order and return the first
        decided result (proven or disproven), or None when none of
        them engages or settles the claim.
    """
    for attempt in _FAST_RESCUES:
        try:
            result = attempt(lhs, rhs, relation, domain, params,
                             bound_context)
        except Exception:
            continue
        if result is not None:
            return result
    return None


def _gap_substituted_attempt(diff, relation: str, domain: dict, params: dict,
                             attempted: list) -> "ProofResult | None":
    """Intent:
        The wave-38 nonnegative-gap technique, automatic: for a claim
        fully symmetric in a group of same-bounded variables, impose
        the WLOG order v1 <= v2 <= ... by substituting
        v_{k} = v1 + g_1 + ... + g_{k-1} with each gap g_i >= 0, so an
        ordering hypothesis becomes manifest nonnegativity the interval
        / sum-of-squares machinery certifies with no case split.

    Notes:
        Sound because the claim is permutation-symmetric: proving it on
        the sorted order proves it for every order. Fresh gap symbols
        carry `nonnegative=True` and enter the domain as `[0, hi-lo]`.
        Declines (None) when no symmetric group, or the substituted
        target still doesn't decide.
    """
    from ..domain import Interval
    from ._proof_support import _decide_relation
    # the symmetry check and the substituted decide are each capped
    # separately (sequential, never nested; the alarm does not nest),
    # so neither the detection nor the re-proof can run unbounded
    groups = _capped(lambda: _symmetric_groups(diff, domain, params))
    if not groups:
        return None
    attempted.append("nonnegative-gap WLOG substitution")
    for members in groups:
        names = [n for n, _s in members]
        syms = [s for _n, s in members]
        bound = domain[names[0]]
        lo = hi = None
        if isinstance(bound, tuple):
            try:
                lo, hi = float(bound[0]), float(bound[1])
            except (TypeError, ValueError, IndexError):
                lo = hi = None
        base = syms[0]
        subs = {}
        new_domain = dict(domain)
        new_params = dict(params)
        acc = base
        gap_names = []
        for i, s in enumerate(syms[1:], start=1):
            g = sympy.Symbol(f"_gap{i}", nonnegative=True)
            acc = acc + g
            subs[s] = acc
            gname = f"_gap{i}"
            new_params[gname] = g
            new_domain[gname] = (Interval(0.0, hi - lo)
                                 if lo is not None and hi is not None
                                 else Interval(0.0, 1e6))
            gap_names.append(gname)
            del new_domain[names[i]]
            new_params.pop(names[i], None)
        try:
            new_diff = sympy.expand(diff.subs(subs, simultaneous=True))
            result = _capped(lambda: _decide_relation(
                new_diff, sympy.S.Zero, relation, new_domain, None, new_params))
        except Exception:
            result = None
        if result is not None and result.status == "proven":
            order = " <= ".join(names)
            meta = dict(result.meta)
            meta["mathema.derive_route"] = "gap_substitution"
            return ProofResult(
                "proven",
                sketch=f"by symmetry assume {order} (WLOG), substituting "
                       f"nonnegative gaps, {result.sketch}",
                quantifier=result.quantifier, meta=meta)
    return None
