# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The built-in claim families: per-claim-name adjudication techniques
registered with `mathema.families` and found by `check_conjectures()`
at adjudication time.

Two kinds live here:

- `probe:algorithmic` families, pairwise/finite-difference sampling
  techniques for claims derive can't decide (monotonicity, affine-ness,
  convexity/concavity), the route a `route="best"` claim falls back to.
- derive-route families, symbolic/structural checks with no sampling
  at all (`is_numerically_stable`'s pole-exclusion reasoning,
  `is_builtin_safe[param]`'s restricted-real-domain check,
  `is_pole_safe[param]`'s pole-containment check), each returning a
  `symbolic.ProofResult` or `None` to decline. The safety predicates
  also carry targeted empirical halves (`_pole_probe`/
  `_builtin_probe`/`_missing_probe`), trials at hazard-informed
  points rather than blind samples.

Registration is explicit: the package `__init__` calls
`_register_builtin_claim_families()` once at import time, rather than
this module registering itself as an import side effect.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .records import Probe

from ._sampling import _finite_bounds as _finite_bounds, _synth_scalar as _synth_scalar
from .grammar import Domain
# hazard knowledge (which parameters face which hazard kinds, and the
# restricted builtins' own accepted ranges) lives in mathema.hazards,
# the shared registry; re-exported names keep this module's public
# shape for existing importers.
from .hazards import (_SAFE_RANGE as _SAFE_RANGE,
                      _missing_guard_params as _missing_guard_params,
                      _pole_bearing_params as _pole_bearing_params,
                      _restricted_domain_targets as _restricted_domain_targets)
from .probing import _fmt, _points_for_probe, _pole_safety, _poles_by_var, _synth

# --- probe:algorithmic families: monotonicity, affine-ness, convexity ------
#
# The claim-family registry's (mathema.families) probe-tier route for
# a claim derive can't decide, clamp01's own monotonic_increasing[x]/
# monotonic_decreasing[x] (a Heaviside-gated Min/Max sympy can't settle
# the sign of) is the concrete case this was built against. Registered
# under the claim's own base name (the part before "[param]"), found by
# check_conjectures() the same way DotFamily is found by name today,
# just keyed by claim name instead of function shape. Reuses the exact
# pairwise/finite-difference techniques the original hardcoded
# `monotone` probe used before the battery migration retired it for
# having no derive-route equivalent, a revival, not new math.


def _claim_target_param(name: str) -> str | None:
    """The parameter a claim like "monotonic_increasing[x]" names,
    or None if the claim's own name carries no bracketed parameter."""
    if name.endswith("]") and "[" in name:
        return name[name.index("[") + 1:-1]
    return None


def _synth_other_params(fn, facts, target: str, domain: dict, rng: random.Random):
    """One synthesized positional-argument list for every parameter of
    fn except target, in facts.params order; target itself is left
    as None, filled in by the caller once per sample point."""
    args: list = []
    for p in facts.params:
        if p == target:
            args.append(None)
            continue
        k = facts.param_kinds.get(p, "unknown")
        args.append(_synth(k, rng, domain.get(p) if k != "sequence" else None))
    return args


def _call_with_target(fn, facts, target: str, args: list, value):
    args = list(args)
    args[facts.params.index(target)] = value
    return fn(*args)


def _probe_trials(fn, facts, target: str, domain: dict, rng: random.Random,
                  trials: int, trial):
    """Intent:
        The one trial loop every probe:algorithmic technique runs:
        synthesize the non-target arguments, hand them to `trial`,
        count only the evaluable rounds, stop at the first
        counterexample.

    Notes:
        `trial(args)` returns None (nothing evaluable this round,
        not counted), True (the property held at this round's
        samples), or a counterexample string (falsifies outright).
        The returned triple is the (verdict, n_checked,
        counterexample) shape the probe:algorithmic route reports;
        no evaluable round at all is "skipped", and a full clean run
        is "holds", never "proven", because a sampling loop can
        witness violation but not absence.
    """
    checked = 0
    for _ in range(trials):
        args = _synth_other_params(fn, facts, target, domain, rng)
        outcome = trial(args)
        if outcome is None:
            continue
        checked += 1
        if outcome is not True:
            return "falsified", checked, outcome
    if checked == 0:
        return "skipped", 0, None
    return "holds", checked, None


def _interval_ends(bounds) -> "tuple[float, float] | None":
    """Intent:
        The finite interval hull of a sampling bound: a plain `(lo, hi)`
        pair, or a `Domain` made of interval pieces (what a type marker
        such as `Probability` produces). None when the bound has no
        interval hull (no bound at all, a discrete set, a complex
        rectangle).
    """
    if isinstance(bounds, tuple) and not isinstance(bounds, frozenset):
        return _finite_bounds(*bounds)
    if isinstance(bounds, Domain) and bounds.pieces:
        spans = [p for p in bounds.pieces
                 if isinstance(p, tuple) and not isinstance(p, frozenset)
                 and not any(isinstance(v, complex) for v in p)]
        if len(spans) != len(bounds.pieces):
            return None
        ends = [_finite_bounds(*p) for p in spans]
        return min(lo for lo, _ in ends), max(hi for _, hi in ends)
    return None


def _monotone_probe(fn, facts, cj, domain: dict, rng: random.Random,
                    trials: int, *, increasing: bool):
    """Pairwise-sampling monotonicity: per trial, two ordered values of
    the claim's own target parameter, every other parameter freshly
    sampled, checking f(x1) <= f(x2) (increasing) or f(x1) >= f(x2)
    (decreasing). Necessary, not sufficient, like every probe
    technique, a real counterexample still falsifies for real, but
    "holds" here means "no violation found in `trials` pairs", not
    proof. Returns (verdict, n_checked, counterexample) or None to
    decline (the claim doesn't name a real scalar parameter of fn)."""
    target = _claim_target_param(cj.name)
    if target is None or target not in facts.params:
        return None
    if facts.param_kinds.get(target) != "scalar":
        return None
    bounds = domain.get(target)

    def trial(args):
        x1 = _synth("float", rng, bounds)
        x2 = _synth("float", rng, bounds)
        if x1 == x2:
            return None
        if x1 > x2:
            x1, x2 = x2, x1
        try:
            v1 = _call_with_target(fn, facts, target, args, x1)
            v2 = _call_with_target(fn, facts, target, args, x2)
        except Exception:
            return None
        ok = (v1 <= v2 + 1e-9) if increasing else (v1 >= v2 - 1e-9)
        if ok:
            return True
        direction = "increasing" if increasing else "decreasing"
        return f"{target}={x1:.6g} -> {v1!r}, {target}={x2:.6g} -> {v2!r} (not {direction})"

    return _probe_trials(fn, facts, target, domain, rng, trials, trial)


def _second_difference_probe(fn, facts, cj, domain: dict, rng: random.Random,
                             trials: int, *, kind: str):
    """Finite-difference second-derivative sign: per trial, a base
    point x0 and a small step h (scaled to the declared domain's own
    width, or a fixed small default when unbounded), checking the
    discrete second difference f(x0-h) - 2*f(x0) + f(x0+h) against
    zero; "affine" wants ~=0, "convex" wants >= -tolerance, "concave"
    wants <= tolerance. A real approximation, not exact: finite-
    difference noise means a genuinely borderline function can go
    either way near the tolerance band, the same honesty every other
    probe technique in this module already carries."""
    target = _claim_target_param(cj.name)
    if target is None or target not in facts.params:
        return None
    if facts.param_kinds.get(target) != "scalar":
        return None
    bounds = domain.get(target)
    lo, hi = _interval_ends(bounds) or (None, None)

    def trial(args):
        x0 = _synth("float", rng, bounds)
        span = (hi - lo) if lo is not None and hi is not None else max(1.0, abs(x0)) * 2
        h = max(span * 1e-3, 1e-6)
        if lo is not None and hi is not None and (x0 - h < lo or x0 + h > hi):
            return None
        try:
            v_lo = _call_with_target(fn, facts, target, args, x0 - h)
            v_mid = _call_with_target(fn, facts, target, args, x0)
            v_hi = _call_with_target(fn, facts, target, args, x0 + h)
        except Exception:
            return None
        second_diff = v_lo - 2 * v_mid + v_hi
        # curvature, not the raw second difference: dividing by h*h
        # recovers an actual f''(x0) estimate, scale-independent of h
        # itself (a pure quadratic's curvature comes back exact
        # regardless of h or x0, confirmed directly). Comparing the
        # *raw* second difference (which shrinks as h**2) against a
        # tolerance scaled only to the function's own value magnitude
        # is the wrong reference scale entirely; it was off by orders
        # of magnitude for a real quadratic before this fix, silently
        # calling every shape "affine". A fixed absolute tolerance on
        # the recovered curvature is still an approximation, not exact;
        # a function whose real curvature is tiny relative to its
        # own value scale (or exactly at the tolerance boundary) can
        # still be misjudged, the same honest limit every probe
        # technique in this module already carries.
        curvature = second_diff / (h * h)
        tol = 1e-4
        ok = (abs(curvature) <= tol if kind == "affine" else
             curvature >= -tol if kind == "convex" else
             curvature <= tol)
        if ok:
            return True
        return (f"{target}={x0:.6g}, h={h:.3g}: curvature estimate "
                f"{curvature:.6g} does not settle {kind}")

    return _probe_trials(fn, facts, target, domain, rng, trials, trial)


def _pole_exclusion_proof(fn, facts, domain: dict, params,
                          proven_sketch: str):
    """Intent:
        The pole-vs-declared-domain containment proof both pole-hazard
        derive routes share: disproven the moment any of `params` has a
        pole provably inside its own bound (that location is the
        counterexample), proven with `proven_sketch` when every
        checked parameter's poles are provably excluded, None when
        nothing was checkable or any containment was undecided.

    Notes:
        Fast-path only (direct lift() critical points, the same
        restriction _affine_hint()/the default probe battery already
        use), deliberately not extensive, so an ordinary check()
        call pays no extra cost by default. A parameter with no
        discovered poles, or a bound that isn't a plain interval,
        contributes nothing rather than deciding anything.
    """
    from .symbolic import ProofResult
    try:
        points = _points_for_probe(fn, facts, domain, extensive=False)
    except Exception:
        return None
    poles_by_var = _poles_by_var(points)
    checked_any = False
    for p in params:
        bounds = domain.get(p)
        poles = poles_by_var.get(p)
        if not poles or not isinstance(bounds, tuple):
            continue
        checked_any = True
        verdict, contained = _pole_safety(bounds, poles)
        if verdict == "falsified":
            return ProofResult("disproven",
                               sketch=f"{p} = {contained[0]} is a pole inside "
                                      "the declared domain",
                               counterexample=f"{p} = {contained[0]}")
        if verdict == "undecided":
            return None
    if not checked_any:
        return None
    return ProofResult("proven", sketch=proven_sketch)


def _is_numerically_stable_derive(fn, facts, lhs_src: str, rhs_src: str,
                               relation: str, domain: dict | None = None,
                               tolerance: float | None = None):
    """Intent:
        A derive-route alternative to is_numerically_stable's existing
        probe implementation: proven when every declared-domain
        parameter's own poles are provably excluded by its bound (the
        same reasoning is_pole_safe[param] already uses, via the shared
        _pole_exclusion_proof), disproven when one is provably inside,
        undecided (returns None, falling through to the existing probe
        check) otherwise.

    Notes:
        lhs_src/rhs_src/relation are unused (this doesn't reason about
        the claim's own algebraic text at all, only fn's poles against
        the declared domain), kept for protocol uniformity with every
        other derive-route family.
    """
    domain = domain or {}
    if not domain:
        return None
    return _pole_exclusion_proof(
        fn, facts, domain, list(domain),
        proven_sketch="every declared-domain parameter's own poles are "
                      "excluded by its bound")


# --- is_builtin_safe[param]: a declared-domain parameter fed into a
# real math function whose own domain is narrower than sympy's symbolic
# generalization (factorial/gamma/lgamma need an integer or positive
# argument; sqrt/log/asin/acos need a non-negative/positive/[-1,1]
# argument respectively), proven/falsified/undecided per the same
# "conservative, honest, never a false certainty" standard
# _is_numerically_stable_derive already holds itself to. -----------------

def _piece_bounds(piece):
    """(lo, hi) for a plain interval-shaped piece (a tuple, `Interval`
    included since it's a tuple subclass) as plain floats, or `None`
    for a frozenset piece (checked value-by-value instead) or anything
    that doesn't convert to two numbers."""
    if isinstance(piece, tuple) and not isinstance(piece, frozenset) and len(piece) == 2:
        try:
            return float(piece[0]), float(piece[1])
        except (TypeError, ValueError):
            return None
    return None


def _in_safe_range(lo: float, hi: float, safe_lo, safe_lo_incl, safe_hi, safe_hi_incl) -> bool:
    lo_ok = lo > safe_lo or (lo == safe_lo and safe_lo_incl)
    hi_ok = hi < safe_hi or (hi == safe_hi and safe_hi_incl)
    return lo_ok and hi_ok


def _domain_pieces(dom):
    """Every concrete (lo, hi)-shaped piece (or frozenset of explicit
    values) dom restricts values to, as a plain list, bare "Z"/"N"
    and no domain declared at all are each expanded to the one
    unbounded-or-half-bounded interval they represent (per
    declared-schema.md, "Domain is a claim field": an unstated domain
    asserts everywhere, not nothing, so `None` is (-inf, inf), not an
    empty/unknown domain). A `Domain` object contributes every one of
    its own pieces (or its own bare-type equivalent, if it states a
    type with no further pieces)."""
    if dom is None or dom == "Z":
        return [(-math.inf, math.inf)]
    if dom == "N":
        return [(0.0, math.inf)]
    if isinstance(dom, frozenset):
        return [dom]
    if isinstance(dom, tuple):
        return [dom]
    if isinstance(dom, Domain):
        if dom.pieces:
            return list(dom.pieces)
        return [(0.0, math.inf)] if dom.base_type == "N" else [(-math.inf, math.inf)]
    return []


def _range_piece_verdict(name: str, piece) -> str:
    """proven/falsified/undecided for one domain piece against name's
    own safe range. No "partially safe" middle ground: a piece that
    only partially overlaps the safe range still contains a real
    counterexample (e.g. sqrt over [-5, 5] includes -3), so that's a
    real falsification, not merely undecided, the claim asserts the
    *entire* piece is safe. "undecided" is reserved for a piece this
    can't evaluate numerically at all."""
    safe_lo, safe_lo_incl, safe_hi, safe_hi_incl = _SAFE_RANGE[name]
    if isinstance(piece, frozenset):
        try:
            values = [float(v) for v in piece]
        except (TypeError, ValueError):
            return "undecided"
        return ("proven" if all(_in_safe_range(v, v, safe_lo, safe_lo_incl, safe_hi, safe_hi_incl)
                                for v in values) else "falsified")
    bounds = _piece_bounds(piece)
    if bounds is None:
        return "undecided"
    lo, hi = bounds
    return ("proven" if _in_safe_range(lo, hi, safe_lo, safe_lo_incl, safe_hi, safe_hi_incl)
           else "falsified")


def _combine_piece_verdicts(verdicts: list) -> str:
    """A domain is a union of its pieces: one falsified piece means a
    real counterexample exists somewhere in the domain (falsified wins
    outright, regardless of what any other piece says); otherwise any
    piece this couldn't evaluate makes the whole domain undecided;
    only when every piece is provably safe is the whole domain proven."""
    if any(v == "falsified" for v in verdicts):
        return "falsified"
    if any(v == "undecided" for v in verdicts):
        return "undecided"
    return "proven"


def _factorial_verdict(dom) -> str:
    """proven/falsified/undecided for whether dom guarantees a
    non-negative *integer*; factorial's own requirement is stricter
    than the other five (a range alone isn't enough: sympy's
    continuous gamma-based generalization accepts any real, but real
    math.factorial raises for a non-integer just as surely as for a
    negative one), so this doesn't reuse _range_piece_verdict at all."""
    if dom is None or dom == "Z":
        return "falsified"   # unbounded/no domain: a negative integer
                             # counterexample always exists in either
    if dom == "N":
        return "proven"
    if isinstance(dom, frozenset):
        try:
            values = [float(v) for v in dom]
        except (TypeError, ValueError):
            return "undecided"
        return "proven" if all(v >= 0 and v.is_integer() for v in values) else "falsified"
    if isinstance(dom, tuple):
        bounds = _piece_bounds(dom)
        if bounds is None:
            return "undecided"
        lo, hi = bounds
        # a non-degenerate continuous range always contains a
        # non-integer real (or is entirely negative), either way a
        # real counterexample exists; only a single integer point is safe.
        return "proven" if lo == hi and lo >= 0 and lo.is_integer() else "falsified"
    if isinstance(dom, Domain):
        if dom.base_type == "N":
            return "proven"   # N alone guarantees non-negative integers
                              # regardless of any further pieces/exclusions
        integer_spaced = dom.base_type == "Z"
        pieces = dom.pieces or ((-math.inf, math.inf),)
        verdicts = []
        for piece in pieces:
            if isinstance(piece, frozenset):
                try:
                    values = [float(v) for v in piece]
                except (TypeError, ValueError):
                    verdicts.append("undecided")
                    continue
                verdicts.append("proven" if all(v >= 0 and v.is_integer() for v in values)
                               else "falsified")
                continue
            bounds = _piece_bounds(piece)
            if bounds is None:
                verdicts.append("undecided")
                continue
            lo, hi = bounds
            if integer_spaced:
                # a Z-typed piece only ever samples the integers inside
                # it, so lo >= 0 alone is enough, no degenerate-point
                # requirement the way a continuous R piece needs.
                verdicts.append("proven" if lo >= 0 else "falsified")
            else:
                verdicts.append("proven" if lo == hi and lo >= 0 and lo.is_integer()
                               else "falsified")
        return _combine_piece_verdicts(verdicts)
    return "undecided"


def _check_restricted_domain(name: str, dom) -> str:
    """Intent:
        "proven"/"falsified"/"undecided" for whether dom (a claim's own
        declared domain bound for one parameter) is safe for a call to
        the math function named name.

    Notes:
        factorial gets its own dedicated check (_factorial_verdict);
        it needs an integer *type* guarantee, not just a range, unlike
        the other five. Every other name here reduces to "is dom a
        subset of this function's own safe range" via
        _domain_pieces/_range_piece_verdict/_combine_piece_verdicts,
        the same three-step shape regardless of which of the five it is.
    """
    if name == "factorial":
        return _factorial_verdict(dom)
    return _combine_piece_verdicts([_range_piece_verdict(name, p) for p in _domain_pieces(dom)])


def _is_builtin_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                            relation: str, domain: dict | None = None,
                            tolerance: float | None = None):
    """Intent:
        A derive-route check for is_builtin_safe[param]: proven when
        param's own declared domain is safe for every restricted-domain
        math function it's actually passed to in fn's body, disproven
        when provably unsafe for at least one, undecided otherwise
        (falling through to _builtin_probe's edge trials on
        route="best").

    Notes:
        rhs_src/relation/tolerance are unused (this doesn't reason
        about the claim's own algebraic text, only fn's restricted-
        domain calls against the declared domain), kept for protocol
        uniformity with every other derive-route family. `lhs_src` is
        param itself: grammar.parse_domain_safety() parses
        "is_builtin_safe(param)" straight into
        `Conjecture(lhs=param, relation="is_builtin_safe", rhs="")`, no
        f(...) wrapper and no name-parsing needed here.
    """
    from .symbolic import ProofResult
    param = lhs_src
    names = _restricted_domain_targets(fn, facts).get(param)
    if not names:
        return None
    domain = domain or {}
    dom = domain.get(param)
    verdicts = {name: _check_restricted_domain(name, dom) for name in names}
    if any(v == "falsified" for v in verdicts.values()):
        # a domain-vs-range violation is an INFERENCE about what the
        # bare builtin call would do, not an established fact about
        # this code, a body that guards or clamps before the call
        # proves the inference wrong. The code is the arbiter: decline
        # here and let the trials at the admitted edge values decide
        # (an unguarded body falsifies there with a real witness; a
        # guarding body holds).
        return None
    if all(v == "proven" for v in verdicts.values()):
        return ProofResult("proven",
                           sketch=f"{param}'s declared domain is safe for "
                                  f"{', '.join(sorted(names))}")
    return None


def _is_pole_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                         relation: str, domain: dict | None = None,
                         tolerance: float | None = None):
    """Intent:
        A derive-route check for is_pole_safe[param]: proven when
        param's own declared domain provably excludes every pole of fn
        found for it, disproven when one is provably inside, undecided
        otherwise (falling through to _pole_probe's admitted-pole
        trials on route="best").

    Notes:
        rhs_src/relation/tolerance are unused, kept for protocol
        uniformity with every other derive-route family (see
        _is_builtin_safe_derive's own note on why). `lhs_src` is param
        itself. The containment reasoning is the shared
        _pole_exclusion_proof, restricted to this one parameter.
    """
    param = lhs_src
    domain = domain or {}
    if not isinstance(domain.get(param), tuple):
        return None
    return _pole_exclusion_proof(
        fn, facts, domain, [param],
        proven_sketch=f"the declared domain for {param} excludes every "
                      f"DISCOVERED pole of {facts.name} (pole discovery "
                      f"is the fast-path search; the containment itself "
                      f"is exact)")


def _pinned_float_env():
    """The floating-point error regime every hazard trial runs under:
    numpy's own defaults, pinned explicitly so a verdict never depends
    on whatever ambient `numpy.seterr` state the calling process
    happens to carry. A no-op context when numpy isn't importable."""
    import contextlib
    try:
        import numpy
    except Exception:
        return contextlib.nullcontext()
    return numpy.errstate(divide="warn", over="warn", under="ignore",
                          invalid="warn")


def _hazard_value_probe(fn, facts, cj, domain: dict, rng: random.Random,
                        trials: int, candidates: list, describe):
    """Intent:
        The empirical core the pole/numeric probe halves share: cycle
        the in-domain hazard candidates for the claim's own parameter
        (every other parameter freshly sampled) and demand a clean,
        finite return at each, a raise or a non-finite result at an
        admitted point is the counterexample, described by
        `describe(value, what_happened)`.

    Notes:
        Candidates are already filtered to the declared domain by the
        caller: everything tried here is a point the domain admits, so
        a failure is the claim's own falsification, never an
        out-of-domain artifact. A non-numeric return (a tuple, a
        sequence) is out of scope for a numeric-hazard trial and
        passes. Declines (None) when the claim names no real scalar
        parameter or no candidate survives the domain filter;
        sampling has nothing hazard-informed to say then.
    """
    target = cj.lhs
    if target not in facts.params:
        return None
    if facts.param_kinds.get(target) == "sequence":
        return None
    if not candidates:
        return None
    state = {"idx": 0}

    def trial(args):
        value = candidates[state["idx"] % len(candidates)]
        state["idx"] += 1
        try:
            with _pinned_float_env():
                out = _call_with_target(fn, facts, target, args, value)
        except Exception as exc:
            return describe(value, f"raised {type(exc).__name__}")
        try:
            as_float = float(out)
        except (TypeError, ValueError):
            return True
        if as_float != as_float or math.isinf(as_float):
            return describe(value, f"returned {out!r}")
        return True

    rounds = max(len(candidates), min(trials, len(candidates) * 4))
    return _probe_trials(fn, facts, target, domain, rng, rounds, trial)


def _pole_probe(fn, facts, cj, domain: dict, rng: random.Random,
                trials: int):
    """Empirical half of is_pole_safe[param]: trials at every
    discovered pole location the declared domain actually admits, and
    at in-domain approach points just beside each pole. A raise or a
    non-finite return at an admitted point falsifies with that
    witness; a clean run holds (n); sampling can witness a reachable
    pole, never prove absence, so avoidance stays derive's alone."""
    from .hazards import _admitted_spelling, hazard_points
    from .probing import _nonpositive_integer_in
    target = cj.lhs
    if target not in facts.params:
        return None
    bounds = domain.get(target)

    candidates: list = []
    for pt in hazard_points(fn, facts, domain, kinds=["pole"]):
        if pt.param != target:
            continue
        if pt.value is None:
            if pt.at == "non-positive integers":
                # gamma/loggamma's infinite pole class: the concrete
                # non-positive integer the bound admits, if any
                k = 0 if bounds is None else _nonpositive_integer_in(bounds)
                if k is not None and k is not False:
                    spelled = _admitted_spelling(float(k), bounds)
                    if spelled is not None:
                        candidates.append(spelled)
            continue
        scale = max(1.0, abs(pt.value))
        for cand in (pt.value,
                     pt.value - 1e-3 * scale, pt.value + 1e-3 * scale,
                     pt.value - 1e-6 * scale, pt.value + 1e-6 * scale):
            spelled = _admitted_spelling(cand, bounds)
            if spelled is not None and spelled not in candidates:
                candidates.append(spelled)
    return _hazard_value_probe(
        fn, facts, cj, domain, rng, trials, candidates,
        lambda value, what: (f"{target} = {value:.6g} is admitted by the "
                             f"declared domain but sits at or beside a "
                             f"pole: the call {what}"))


def _is_extremity_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                            relation: str, domain: dict | None = None,
                            tolerance: float | None = None):
    """Intent:
        The range-analysis half of is_extremity_safe[param]: proven when
        the rigorous interval hull of the lifted form over the declared
        domain box provably stays inside float range (the true range is
        contained in the hull, so containment IS representability
        everywhere); undecided (None) otherwise, falling through to
        the extreme-trial probe half.

    Notes:
        Analysis never falsifies here: interval arithmetic
        over-approximates, so a hull escaping float range does not
        witness any attained overflow, and even an attained
        mathematical overflow says nothing certain about code that
        clamps before it. Violation is the probe half's to witness
        with a real call. Requires every declared bound along the way
        to be finite (an unbounded box has an unbounded hull); the
        probe half owns the unbounded case through its
        pseudo-infinity scoping.
    """
    import sys

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .symbolic import ProofResult, lift
    param = lhs_src
    if param not in facts.params:
        return None
    domain = domain or {}
    try:
        lifted = lift(fn, facts)
    except Exception:
        return None
    if lifted is None or isinstance(lifted.expr, tuple):
        return None
    expr = lifted.expr
    params = {s.name: s for s in expr.free_symbols}
    if param not in params:
        return None
    try:
        from .symbolic._proof_support import _interval_bounds
        hull = _with_timeout(
            lambda: _interval_bounds(expr, domain, params),
            FAST_TIMEOUT_SECONDS)
    except Exception:
        return None
    if hull is None:
        return None
    lo = getattr(hull, "min", hull)
    hi = getattr(hull, "max", hull)
    float_max = sys.float_info.max
    try:
        within = bool((lo > -float_max) == True         # noqa: E712
                      and (hi < float_max) == True)     # noqa: E712
    except Exception:
        return None
    if not within:
        return None
    return ProofResult(
        "proven",
        sketch=f"the value hull over the declared domain stays inside "
               f"float range, so no admitted input can push the "
               f"result past what a float represents ({param} "
               f"included at its declared extremes)")


def _extreme_probe(fn, facts, cj, domain: dict, rng: random.Random,
                   trials: int):
    """Empirical half of is_extremity_safe[param]: trials at the
    representation-extreme inputs the declared domain admits, the
    finite declared endpoints, and (for an unbounded side) the
    pseudo-infinity cap when the claim states one, else the true
    representation ladder (float max, the x*x-overflow scale, the
    exp-overflow threshold, the denormal band). Reaching true float
    extremes on an unbounded, uncapped domain is this member's
    explicit job; every trial point is still admitted by the domain.
    A raise or non-finite return falsifies with that witness."""
    from .hazards import _extreme_candidates
    from .records import pseudo_infinity_range
    target = cj.lhs
    if target not in facts.params:
        return None
    pinf = pseudo_infinity_range(getattr(cj, "pseudo_infinity", None))
    candidates = _extreme_candidates(domain.get(target),
                                     pseudo_infinity=pinf)
    return _hazard_value_probe(
        fn, facts, cj, domain, rng, trials, candidates,
        lambda value, what: (f"{target} = {value:.6g} is admitted by the "
                             f"declared domain but the implementation "
                             f"leaves float range there: the call {what}"))


def _is_state_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                          relation: str, domain: dict | None = None,
                          tolerance: float | None = None):
    """Intent:
        The structural half of is_state_safe (the mutation member of
        the stateless cluster): calling the function mutates no
        external state, no argument in place, no global, no module
        attribute. Proven under the write-free certificate (no
        syntactic external-write site anywhere in the body, every
        name resolved) or a full lift (an expression has nothing to
        mutate with). A detected write site stays undecided (None):
        structure can't tell whether the writing branch executes, so
        the snapshot trials decide.

    Notes:
        WRITES only, deliberately: external READS are
        is_deterministic's territory; together the two bracket the
        purity story core-side (the T0-T5 tiering itself is not a
        core concern). rhs_src/relation/tolerance kept for protocol
        uniformity.
    """
    from .hazards import _write_free
    from .symbolic import ProofResult, lift
    if _write_free(facts):
        return ProofResult(
            "proven",
            sketch="no external-write site exists in the body (no "
                   "argument mutation, no global or module write, no "
                   "dynamic escape) and every name resolves; there "
                   "is no state to mutate")
    try:
        lifted = lift(fn, facts)
    except Exception:
        lifted = None
    if lifted is not None:
        return ProofResult(
            "proven",
            sketch="the body lifts to a closed expression, which "
                   "mutates nothing by construction")
    return None


def _state_probe(fn, facts, cj, domain: dict, rng: random.Random,
                 trials: int):
    """Empirical half of is_state_safe: deep-copy the arguments and
    snapshot the function's module globals (data entries only) before
    a call, compare after, an observed mutation falsifies naming
    the mutated target. Clean rounds hold: an unexecuted branch may
    still hide a write, so trials never establish this fact."""
    import copy
    import types
    if not facts.params:
        return None
    target = facts.params[0]
    module_dict = getattr(fn, "__globals__", {}) or {}

    def data_globals():
        out = {}
        for name, value in module_dict.items():
            if name.startswith("__"):
                continue
            if isinstance(value, (types.ModuleType, types.FunctionType,
                                  types.BuiltinFunctionType, type)):
                continue
            out[name] = value
        return out

    def trial(args):
        call_args = list(args)
        call_args[facts.params.index(target)] = _synth(
            facts.param_kinds.get(target, "unknown"), rng,
            domain.get(target))
        try:
            originals = copy.deepcopy(call_args)
        except Exception:
            return None
        before = data_globals()
        try:
            before_copy = {k: copy.deepcopy(v) for k, v in before.items()}
        except Exception:
            before_copy = None
        try:
            with _pinned_float_env():
                fn(*call_args)
        except Exception:
            return None   # a raising point says nothing about mutation
        for p, original, after in zip(facts.params, originals, call_args):
            same = (original == after
                    or (isinstance(original, float) and original != original
                        and isinstance(after, float) and after != after))
            if not same:
                return (f"calling the function mutated its own argument "
                        f"{p!r}: {original!r} became {after!r}")
        after_globals = data_globals()
        if set(after_globals) != set(before):
            changed = sorted(set(after_globals) ^ set(before))
            return (f"calling the function changed module state: "
                    f"{', '.join(changed)}")
        if before_copy is not None:
            for name, value in before_copy.items():
                current = after_globals[name]
                if current is not before[name]:
                    # rebound to a different object: a real change,
                    # whatever the type, and no comparison needed
                    return (f"calling the function rebound module-level "
                            f"{name!r}: {value!r} became {current!r}")
                if type(current).__eq__ is object.__eq__:
                    # equality is identity for this type, and `value` is
                    # a deep copy, so the comparison below can only ever
                    # say "changed", which is how a module carrying
                    # `from __future__ import annotations` got reported
                    # as mutating its `annotations` global, with a
                    # witness whose before and after printed identically
                    # (`__future__._Feature` defines no `__eq__`). The
                    # object is the same one; in-place mutation of a
                    # type like this is simply not detectable here, and
                    # claiming it is a false positive.
                    continue
                try:
                    unchanged = bool(current == value)
                except Exception:
                    # a numpy array (or anything else whose `==` is
                    # elementwise) has no single truth value, the
                    # identity check above already covered rebinding,
                    # so say nothing rather than raise
                    continue
                if not unchanged:
                    return (f"calling the function mutated module-level "
                            f"{name!r}: {value!r} became {current!r}")
        return True

    return _probe_trials(fn, facts, target, domain, rng,
                         max(trials // 4, 8), trial)


def _excluded_outside_domain_derive(fn, facts, lhs_src: str, rhs_src: str,
                                    relation: str, domain: dict | None = None,
                                    tolerance: float | None = None):
    """Intent:
        The structural half of excluded_outside_domain[param]: the
        function must raise on any input outside param's declared
        domain. Proven when the function is wrapped by
        @enforce_domain covering this parameter, rejection by
        construction, the wrapper checks every call before the body
        runs. Undecided (None) otherwise: the trials at concrete
        out-of-domain values decide empirically.

    Notes:
        This claim is never battery-suggested: it is DECLARED,
        explicitly, via the `excluding` keyword, or automatically by
        @enforce_domain itself (the decorator that makes it true also
        declares it). rhs_src/relation/tolerance kept for protocol
        uniformity.
    """
    from .symbolic import ProofResult
    param = lhs_src
    enforced = getattr(fn, "__mathema_enforced_domain__", None)
    if enforced is not None and param in enforced:
        return ProofResult(
            "proven",
            sketch=f"rejection by construction: the enforce_domain "
                   f"wrapper checks {param} against its declared domain "
                   f"before the body ever runs")
    return None


def _excluded_probe(fn, facts, cj, domain: dict, rng: random.Random,
                    trials: int):
    """Empirical half of excluded_outside_domain[param]: call fn at
    concrete values provably outside the declared domain (just past
    each boundary, every domain shape supported); every such call
    must raise. A clean return falsifies with the accepted value as
    witness; the exclusion is asserted, not enforced. All raise ->
    holds (the outside is a continuum, so trials never establish)."""
    from .domain import is_missing
    from .probing import _out_of_domain_candidates
    target = cj.lhs
    if target not in facts.params:
        return None
    bounds = domain.get(target)
    if bounds is None:
        return None   # an unstated domain admits everything: no outside
    candidates = [c for c in _out_of_domain_candidates(bounds)
                  if not is_missing(c)]   # missing spellings are
    # is_missing_safe's own hazard, not this member's
    if not candidates:
        return None
    sequence_target = facts.param_kinds.get(target) == "sequence"
    state = {"idx": 0}

    def trial(args):
        bad = candidates[state["idx"] % len(candidates)]
        state["idx"] += 1
        if sequence_target:
            # a sequence parameter is violated one ELEMENT at a time:
            # a fresh in-domain sequence with one out-of-domain entry
            seq = [rng.uniform(-10, 10) for _ in range(4)]
            seq[rng.randrange(len(seq))] = bad
            value: object = seq
            spelled = f"{target}[...] = {bad!r}"
        else:
            value = bad
            spelled = f"{target} = {bad!r}"
        try:
            out = _call_with_target(fn, facts, target, args, value)
        except Exception:
            return True   # rejected, as the claim demands
        return (f"{spelled} is outside the declared domain but was "
                f"accepted (returned {out!r}); the exclusion is "
                f"asserted, not enforced")

    rounds = max(len(candidates), min(trials, len(candidates) * 4))
    return _probe_trials(fn, facts, target, domain, rng, rounds, trial)


def _is_deterministic_derive(fn, facts, lhs_src: str, rhs_src: str,
                             relation: str, domain: dict | None = None,
                             tolerance: float | None = None):
    """Intent:
        The structural half of is_deterministic (the STRONG member of
        the stateless cluster): the function runs the same way every
        time, nothing external can change state within it and no
        seed is involved anywhere. A body that lifts to a closed
        symbolic form is deterministic by construction: the form has
        no state to vary with. Undecided (None) otherwise: the
        generic empirical loop (f(...) == f(...), re-evaluated per
        trial) is the runtime half that catches a body reading time,
        RNG state, or mutable globals.

    Notes:
        The maths is deterministic by definition; determinism is the
        IMPLEMENTATION's claim. Deterministic implies reproducible
        (the weaker, up-to-a-seed member below). rhs_src/relation/
        tolerance kept for protocol uniformity.
    """
    from .symbolic import ProofResult, lift
    try:
        lifted = lift(fn, facts)
    except Exception:
        return None
    if lifted is None:
        return None
    return ProofResult(
        "proven",
        sketch="the body lifts to a closed symbolic form, which is "
               "deterministic by construction; there is no state for "
               "the same inputs to vary with")


def _is_reproducible_derive(fn, facts, lhs_src: str, rhs_src: str,
                            relation: str, domain: dict | None = None,
                            tolerance: float | None = None):
    """Intent:
        The structural half of is_reproducible (the WEAKER member of
        the stateless cluster): reproducible UP TO an RNG seed, fix
        the seed, rerun, get the same output. A deterministic body is
        a fortiori reproducible, so this accepts determinism's own
        proof (the lift); everything else falls to the paired
        seed-restored trials.
    """
    proof = _is_deterministic_derive(fn, facts, lhs_src, rhs_src,
                                     relation, domain=domain,
                                     tolerance=tolerance)
    if proof is None:
        return None
    from .symbolic import ProofResult
    return ProofResult(
        "proven",
        sketch="deterministic by construction (the body lifts to a "
               "closed form), and deterministic implies reproducible")


def _reproducible_probe(fn, facts, cj, domain: dict, rng: random.Random,
                        trials: int):
    """Empirical half of is_reproducible: two calls at the same inputs
    with the recognized RNG state captured and restored between them
    (the stdlib `random` global state, and numpy's legacy global state
    when numpy is importable) must return the same value, same seed,
    same run. Divergence falsifies with the pair as witness; a
    passed-in generator object is out of this v1's scope. Agreement
    across trials holds (specific states were tested, not all)."""
    if not facts.params:
        return None
    target = facts.params[0]

    def rng_states():
        states = [("random", random.getstate, random.setstate)]
        try:
            import numpy
            states.append(("numpy", numpy.random.get_state,
                           numpy.random.set_state))
        except Exception:
            pass
        return states

    def trial(args):
        call_args = list(args)
        call_args[facts.params.index(target)] = _synth(
            facts.param_kinds.get(target, "unknown"), rng,
            domain.get(target))
        captured = [(setter, getter()) for _, getter, setter in rng_states()]
        try:
            with _pinned_float_env():
                first = fn(*call_args)
        except Exception:
            return None   # a raising point says nothing about seeds
        for setter, state in captured:
            setter(state)
        try:
            with _pinned_float_env():
                second = fn(*call_args)
        except Exception as exc:
            return (f"same inputs, same restored RNG state: the first "
                    f"call returned {first!r} but the second raised "
                    f"{type(exc).__name__}")
        agree = (first == second
                 or (isinstance(first, float) and isinstance(second, float)
                     and (first != first and second != second)))
        if not agree:
            return (f"same inputs, same restored RNG state, different "
                    f"results: {first!r} then {second!r}, the "
                    f"implementation is not reproducible up to its seed")
        return True

    return _probe_trials(fn, facts, target, domain, rng,
                         max(trials // 4, 8), trial)


def _is_empty_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                          relation: str, domain: dict | None = None,
                          tolerance: float | None = None):
    """Intent:
        The structural half of is_empty_safe[xs]: proven when the
        sequence parameter carries an explicit raising emptiness guard
        (`if not xs: raise`, `if len(xs) == 0: raise`), the empty
        boundary is deliberately rejected, which is safe handling.
        Undecided (None) otherwise: the probe decides empirically
        whether an empty input crashes by accident.

    Notes:
        rhs_src/relation/tolerance kept for protocol uniformity;
        `lhs_src` is the parameter itself.
    """
    from .hazards import _emptiness_guard_params
    from .symbolic import ProofResult
    param = lhs_src
    if facts.param_kinds.get(param) != "sequence":
        return None
    if param in _emptiness_guard_params(facts):
        return ProofResult(
            "proven",
            sketch=f"the empty {param} is deliberately rejected by an "
                   f"explicit raising guard; the boundary is handled, "
                   f"not stumbled into")
    return None


def _empty_probe(fn, facts, cj, domain: dict, rng: random.Random,
                 trials: int):
    """Empirical half of is_empty_safe[xs]: call fn with the empty
    sequence, a single-element sequence, and a longer one (every other
    parameter freshly sampled). An UNGUARDED raise on the empty input
    is an accidental boundary crash and falsifies with that witness
    (min/max/mean of [] raise however sound the maths); a raise
    behind a recognized emptiness guard is deliberate rejection and
    passes. A raise or non-finite result on the non-empty sanity
    inputs falsifies outright."""
    from .hazards import _emptiness_guard_params
    target = cj.lhs
    if facts.param_kinds.get(target) != "sequence":
        return None
    guarded = target in _emptiness_guard_params(facts)
    shapes = ("empty", "single", "longer")
    state = {"idx": 0}

    def trial(args):
        shape = shapes[state["idx"] % len(shapes)]
        state["idx"] += 1
        value = ([] if shape == "empty"
                 else [rng.uniform(-10, 10)] if shape == "single"
                 else [rng.uniform(-10, 10) for _ in range(5)])
        try:
            with _pinned_float_env():
                out = _call_with_target(fn, facts, target, args, value)
        except Exception as exc:
            if shape == "empty":
                if guarded:
                    return True   # deliberate rejection
                return (f"{target} = [] raised {type(exc).__name__} with no "
                        f"emptiness guard in the body, the empty boundary "
                        f"is stumbled into, not handled")
            return (f"{target} = {value!r} raised {type(exc).__name__}")
        try:
            as_float = float(out)
        except (TypeError, ValueError):
            return True
        if shape != "empty" and (as_float != as_float
                                 or math.isinf(as_float)):
            return (f"{target} = {value!r} returned {out!r}")
        return True

    result = _probe_trials(fn, facts, target, domain, rng,
                           max(trials // 4, 9), trial)
    verdict, checked, cx = result
    if verdict == "holds" and len(facts.params) == 1:
        # exhaustive coverage: the empty-sequence hazard is one input,
        # and with no other parameter to vary, observing that one call
        # behave IS the whole hazard class
        return ("proven", checked, None,
                "the empty-sequence hazard is a single input; with one "
                "parameter the call at [] was observed to behave, so the "
                "examination is exhaustive")
    return result


#: exception types that mean the function stumbled on an input it did not
#: handle, an accidental crash, as opposed to a deliberate rejection
#: (a ValueError from a validating guard, which is not in this set).
_ACCIDENTAL_CRASHES = (TypeError, IndexError, UnicodeError, RecursionError,
                       AttributeError, KeyError, OverflowError)


def _is_arbitrary_input_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                                    relation: str, domain: dict | None = None,
                                    tolerance: float | None = None):
    """Intent:
        Structural half of is_arbitrary_input_safe: decline. "No
        accidental crash on ANY string" is not something the derive
        route can establish symbolically over arbitrary code, so the
        member is empirical, this returns None and the fuzz + shrink
        probe does the work.
    """
    return None


def _arbitrary_input_probe(fn, facts, cj, domain: dict, rng: random.Random,
                           trials: int):
    """Empirical half of is_arbitrary_input_safe[s]: feed the target
    string parameter every edge case in the corpus (empty, whitespace,
    control chars, combining/zero-width marks, non-ascii, a very long
    string, injection-/format-/path-shaped strings) plus a few random
    draws, every other parameter freshly sampled. An ACCIDENTAL-type
    exception (TypeError/IndexError/UnicodeError/RecursionError/
    AttributeError/KeyError/OverflowError) raised with NO validating
    guard on the parameter is a crash: the minimal triggering string is
    found by shrinking and returned as the witness. A raise the function
    GUARDS (a validating `if ...: raise`/`assert`), or any other
    exception type (a deliberate ValueError), is accepted; a normal
    return is fine."""
    from ._sampling import _STRING_SPECIALS, _synth_string
    from ._shrink import shrink
    from .analysis import _guards

    target = cj.lhs
    if facts.param_kinds.get(target) != "string":
        return None
    guarded = _guards(facts.tree, facts.params).get(target) in ("raise", "assert")

    def crash_on(args, value):
        try:
            with _pinned_float_env():
                _call_with_target(fn, facts, target, args, value)
        except _ACCIDENTAL_CRASHES as exc:
            return None if guarded else type(exc).__name__
        except Exception:
            return None       # a deliberate/other exception is not a crash
        return None

    corpus = list(_STRING_SPECIALS) + [_synth_string(rng) for _ in range(8)]
    state = {"i": 0}

    def trial(args):
        if state["i"] >= len(corpus):
            return True
        value = corpus[state["i"]]
        state["i"] += 1
        exc = crash_on(args, value)
        if exc is None:
            return True
        minimal = shrink(value, lambda s: crash_on(args, s) is not None)
        return (f"{target} = {minimal!r} raised {exc} on arbitrary input, "
                f"an unguarded crash, not a declared rejection")

    return _probe_trials(fn, facts, target, domain, rng,
                         max(trials, len(corpus)), trial)


def _is_representation_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                                   relation: str, domain: dict | None = None,
                                   tolerance: float | None = None):
    """Intent:
        The structural half of is_representation_safe[param]: does the
        body's own type discipline provably match the declared
        domain's representation policy? Proven when the policy admits
        exactly one machine spelling (an integer-typed bound) AND
        raising type guards enforce it completely (accepting int and
        rejecting bool; isinstance(x, int) alone lets True through,
        so the bool rejection must be explicit). Disproven, with a
        corroborating real call as witness, when a recognized guard
        raises on a spelling the policy admits. Everything else is
        undecided (None): the cross-spelling probe settles it.

    Notes:
        This deliberately is NOT what mypy checks. mypy proves static
        name-level type consistency without running anything;
        this claim is about VALUE-level representation policy (the
        domain's own machine-int-only reading of Z) and behavioural
        agreement at the same mathematical point, annotations here
        are structural evidence, never trusted facts. rhs_src/
        relation/tolerance kept for protocol uniformity; `lhs_src` is
        param itself.
    """
    from .domain import _as_domain
    from .hazards import _spelling_values, _type_guard_params
    from .symbolic import ProofResult
    param = lhs_src
    if param not in facts.params:
        return None
    domain = domain or {}
    bounds = domain.get(param)
    try:
        base_type = _as_domain(bounds).base_type
    except Exception:
        return None
    guard = _type_guard_params(facts).get(param)
    integer_only = base_type in ("Z", "N")
    if integer_only and guard is not None \
            and guard["accepts"] == frozenset({"int"}) \
            and "bool" in guard["rejects"]:
        return ProofResult(
            "proven",
            sketch=f"{param}'s integer-typed domain admits exactly one "
                   f"machine spelling, and the body's raising type "
                   f"guards enforce it (int accepted, bool explicitly "
                   f"rejected)")
    if guard is not None:
        admitted_spellings = ({"int"} if integer_only
                              else {"int", "float"})
        rejected_admitted = sorted(guard["rejects"] & admitted_spellings)
        if rejected_admitted:
            spelling = rejected_admitted[0]
            values = _spelling_values(bounds) or [1]
            caster = int if spelling == "int" else float
            corroborating_rng = random.Random(0)
            for v in values:
                args = _synth_other_params(fn, facts, param, domain,
                                           corroborating_rng)
                try:
                    _call_with_target(fn, facts, param, args, caster(v))
                except Exception as exc:
                    return ProofResult(
                        "disproven",
                        sketch=f"the declared domain admits the {spelling} "
                               f"spelling of {param} but a raising type "
                               f"guard rejects it",
                        counterexample=f"{param} = {caster(v)!r} raised "
                                       f"{type(exc).__name__} by explicit "
                                       f"type guard")
            return None   # structure says rejected, runtime disagrees
    return None


def _representation_probe(fn, facts, cj, domain: dict, rng: random.Random,
                          trials: int):
    """Empirical half of is_representation_safe[param]: at each
    integral mathematical point the domain contains, call fn with
    every machine spelling of that value (int, float, and bool at 0/1)
    and demand what the declared representation policy demands;
    admitted spellings must all return math-equal results (an
    admitted spelling raising, or two admitted spellings diverging
    past tolerance, falsifies with the pair as witness), and a
    policy-excluded spelling must raise (a clean return means the
    type exclusion is asserted, not enforced). What runs here is what
    mypy cannot ask: whether f(2), f(2.0), and f(True) AGREE."""
    from .grammar import domain_contains
    from .hazards import _spelling_values
    target = cj.lhs
    if target not in facts.params:
        return None
    if facts.param_kinds.get(target) == "sequence":
        return None
    bounds = domain.get(target)
    values = _spelling_values(bounds)
    if not values:
        return None
    tol = cj.tolerance if cj.tolerance is not None else 1e-9

    def admitted(value) -> bool:
        try:
            return domain_contains(value, bounds)
        except Exception:
            return False

    state = {"idx": 0}

    def trial(args):
        v = values[state["idx"] % len(values)]
        state["idx"] += 1
        spellings = [("int", int(v)), ("float", float(v))]
        if v in (0, 1):
            spellings.append(("bool", bool(v)))
        outcomes = []
        for label, spelled in spellings:
            try:
                with _pinned_float_env():
                    out = _call_with_target(fn, facts, target, args, spelled)
                outcomes.append((label, spelled, "returned", out))
            except Exception as exc:
                outcomes.append((label, spelled, "raised",
                                 type(exc).__name__))
        def agrees(a, b) -> bool:
            if a == b:
                return True
            if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
                return False
            if a != a and b != b:
                return True   # both NaN: the same missing outcome
            try:
                return abs(float(a) - float(b)) <= tol
            except (OverflowError, ValueError):
                return False

        reference = None
        for label, spelled, what, out in outcomes:
            if admitted(spelled):
                if what == "raised":
                    return (f"{target} = {spelled!r} (the {label} spelling) "
                            f"is admitted by the declared domain but the "
                            f"call raised {out}")
                if reference is None:
                    reference = (label, spelled, out)
                elif not agrees(out, reference[2]):
                    return (f"f at {target} = {v} diverges across machine "
                            f"spellings: the {reference[0]} spelling "
                            f"returned {reference[2]!r} but the {label} "
                            f"spelling returned {out!r}")
            elif what == "returned":
                if label == "bool":
                    # bool is Python's own subtype of int: no domain
                    # vocabulary excludes it by name, so a returning
                    # bool spelling is judged on AGREEMENT only (a
                    # raise would also have been acceptable rejection)
                    if reference is not None and not agrees(out, reference[2]):
                        return (f"f at {target} = {v} diverges across "
                                f"machine spellings: the {reference[0]} "
                                f"spelling returned {reference[2]!r} but "
                                f"the bool spelling returned {out!r}")
                    continue
                return (f"{target} = {spelled!r} (the {label} spelling) is "
                        f"excluded by the declared domain's representation "
                        f"policy but returned {out!r}, the type exclusion "
                        f"is asserted, not enforced")
        return True

    rounds = max(len(values), min(trials, len(values) * 4))
    return _probe_trials(fn, facts, target, domain, rng, rounds, trial)


def _builtin_probe(fn, facts, cj, domain: dict, rng: random.Random,
                   trials: int):
    """Empirical half of is_builtin_safe[param]: trials at the domain
    edges of every restricted builtin the parameter is actually passed
    to (log's zero, asin/acos's unit endpoints, sqrt's negatives,
    factorial's negative and non-integer neighbours), clipped to the
    declared domain. A raise or non-finite return at an admitted point
    falsifies; a clean run holds (n)."""
    from .hazards import (_SAFE_RANGE, _admitted_spelling,
                          _restricted_domain_targets)
    target = cj.lhs
    names = _restricted_domain_targets(fn, facts).get(target)
    if not names:
        return None
    bounds = domain.get(target)

    candidates: list = []
    for name in sorted(names):
        if name == "factorial":
            raw = [-1.0, 0.5, -0.5]
        else:
            lo, lo_incl, hi, hi_incl = _SAFE_RANGE[name]
            raw = []
            if not math.isinf(lo):
                raw += ([] if lo_incl else [lo]) + [lo - 1e-6, lo - 1.0]
            if not math.isinf(hi):
                raw += ([] if hi_incl else [hi]) + [hi + 1e-6, hi + 1.0]
        for cand in raw:
            spelled = _admitted_spelling(cand, bounds)
            if spelled is not None and spelled not in candidates:
                candidates.append(spelled)
    return _hazard_value_probe(
        fn, facts, cj, domain, rng, trials, candidates,
        lambda value, what: (f"{target} = {value:.6g} is admitted by the "
                             f"declared domain but lies outside a "
                             f"restricted builtin's own real domain "
                             f"({', '.join(sorted(names))}): the call "
                             f"{what}"))


# --- is_missing_safe[param]: does the function's runtime behavior on a
# missing input honor the declared domain's missing-value policy?
# Missing is included by default; an explicit \ {∅} exclusion is only an
# assertion until the function demonstrably rejects missing input;
# this family is the mechanism that lets a claim actually earn the
# narrower domain. Tests literal NaN-in behavior only: a domain-invalid
# *non-NaN* input that produces NaN downstream is is_pole_safe/
# is_builtin_safe territory, a separable code path (verified empirically
# against numpy: NaN-in never raises even under seterr(all='raise'),
# while domain-invalid inputs go through a different, global-state-
# dependent path). ---------------------------------------------------


def _is_missing_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                            relation: str, domain: dict | None = None,
                            tolerance: float | None = None):
    """Intent:
        The structural half of is_missing_safe[param]: proven when the
        declared domain excludes missing for param AND fn's own body
        guards BOTH missing spellings (NaN and None) with explicit
        raising checks; disproven when the domain includes missing
        (the default) but a raising guard rejects either spelling
        anyway; undecided (None) otherwise, a guard covering only
        one spelling leaves the other to the runtime probe, which
        settles what structure alone can't.

    Notes:
        rhs_src/relation/tolerance are unused, kept for protocol
        uniformity with the other derive-route families. `lhs_src` is
        param itself, same as is_pole_safe/is_builtin_safe. This reads
        only what is actually written in the source: no guard is never
        evidence of acceptance, and a guard is never assumed to cover
        spellings it doesn't test; either gap stays undecided rather
        than guessed.
    """
    from .symbolic import ProofResult
    from .domain import missing_included
    from .hazards import _missing_guard_coverage
    param = lhs_src
    if param not in facts.params:
        return None
    domain = domain or {}
    included = missing_included(domain.get(param))
    coverage = _missing_guard_coverage(facts).get(param, set())
    if not included and coverage >= {"nan", "none"}:
        return ProofResult("proven",
                           sketch=f"{param}'s declared missing-value exclusion is "
                                  "enforced by explicit raising guards for both "
                                  "missing spellings (NaN and None)")
    if included and coverage:
        spelled = "nan" if "nan" in coverage else "None"
        return ProofResult("disproven",
                           sketch=f"the declared domain admits a missing {param} "
                                  "(missing is included by default; no \\ {∅} "
                                  "exclusion is stated) but the body raises on it",
                           counterexample=f"{param} = {spelled} raises by explicit guard")
    return None


def _missing_probe(fn, facts, cj, domain: dict, rng: random.Random,
                   trials: int):
    """Runtime half of is_missing_safe[param]: call fn with a literal
    NaN and a literal None for the claim's own parameter (every other
    parameter freshly sampled inside the declared domain), alternating
    spellings, and check the behavior against the domain's resolved
    missing policy; excluded means every call must raise (whichever
    spelling), included (the default) means no call may raise. The
    two missing spellings only, never a domain-invalid ordinary
    number: missing-in and domain-invalid-producing-NaN are separable
    code paths, and the latter belongs to is_pole_safe/
    is_builtin_safe. Returns (verdict, n_checked, counterexample) or
    None to decline."""
    from .domain import missing_included
    target = cj.lhs
    if target not in facts.params:
        return None
    if facts.param_kinds.get(target) not in ("scalar", "unknown"):
        return None
    included = missing_included(domain.get(target))
    spellings = (("nan", float("nan")), ("None", None))
    state = {"idx": 0}

    def trial(args):
        label, missing_value = spellings[state["idx"] % len(spellings)]
        state["idx"] += 1
        try:
            value = _call_with_target(fn, facts, target, args, missing_value)
        except Exception as exc:
            if included:
                return (f"{target}={label} raised {type(exc).__name__} but the "
                        "declared domain admits a missing value (missing is "
                        "included by default; no \\ {∅} exclusion is stated)")
            return True
        if not included:
            return (f"{target}={label} returned {value!r} but the declared "
                    "domain excludes missing; the exclusion is asserted, "
                    "not enforced")
        return True

    result = _probe_trials(fn, facts, target, domain, rng,
                           max(trials // 4, 8), trial)
    verdict, checked, cx = result
    if verdict == "holds" and len(facts.params) == 1:
        # exhaustive coverage: the missing hazard class is exactly two
        # spellings, and with no other parameter to vary, calling this
        # function at both IS the whole class, an established fact
        return ("proven", checked, None,
                "the missing hazard class is exactly two spellings (NaN "
                "and None); with a single parameter both were called and "
                "behaved per the declared policy, so the examination is "
                "exhaustive")
    return result


class _NamedClaimFamily:
    """One `ClaimFamily` per base claim name, registered below,
    can_handle matches on the claim's own name alone (the registry key
    already did the real matching; this stays uniform with a
    shape-based family's own can_handle signature rather than
    special-casing name-keyed families)."""

    def __init__(self, base_name: str, routes: dict):
        self._base_name = base_name
        self._routes = routes

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return claim_name.startswith(self._base_name)

    def routes(self) -> dict:
        return self._routes


def _guarded_safety_derive(derive):
    """Wrap a safety member's derive half in the family verdict
    contract: a disproof must carry a concrete counterexample (a
    safety falsification without a witness is not evidence), and the
    status vocabulary is closed. A violation raises; it is a family
    implementation bug, never a claim outcome."""
    def run(fn, facts, lhs_src, rhs_src, relation, domain=None,
            tolerance=None):
        proof = derive(fn, facts, lhs_src, rhs_src, relation,
                       domain=domain, tolerance=tolerance)
        if proof is None:
            return None
        if proof.status not in ("proven", "disproven", "undecided"):
            raise ValueError(f"safety derive returned status "
                             f"{proof.status!r}, not in the closed "
                             f"proven/disproven/undecided vocabulary")
        if proof.status == "disproven" and not proof.counterexample:
            raise ValueError("safety derive disproved without a concrete "
                             "counterexample, a safety falsification "
                             "must carry its witness")
        return proof
    return run


def _guarded_safety_probe(probe):
    """Wrap a safety member's empirical half in the family verdict
    contract. Trials may falsify (with a witness), hold, or decline;
    they may claim "proven" ONLY by returning the 4-tuple form
    (verdict, checked, cx, established) with a non-empty
    `established` sketch naming why the coverage was EXHAUSTIVE,
    the hazard class fully enumerated and every case observed. The
    verdict carries surety, so an established empirical examination
    proves; anything short of exhaustive coverage holds at best. A
    contract violation raises, same as the derive guard."""
    def run(fn, facts, cj, domain, rng, trials):
        result = probe(fn, facts, cj, domain, rng, trials)
        if result is None:
            return None
        if len(result) == 4:
            verdict, checked, cx, established = result
        else:
            verdict, checked, cx = result
            established = None
        if verdict == "proven" and not established:
            raise ValueError("safety trials claimed proven without an "
                             "established-coverage sketch, sampling "
                             "alone never proves; only an exhaustive "
                             "examination (stated as such) does")
        if verdict not in ("proven", "falsified", "holds", "skipped"):
            raise ValueError(f"safety probe returned verdict {verdict!r}, "
                             f"outside the closed vocabulary")
        if verdict == "falsified" and not cx:
            raise ValueError("safety probe falsified without a concrete "
                             "counterexample, a safety falsification "
                             "must carry its witness")
        return (verdict, checked, cx, established)
    return run


class SafetyFamily(_NamedClaimFamily):
    """One implementation-safety member: a claim family whose evidence
    concerns a hazard class (where the CODE's runtime behaviour can
    diverge from the mathematics) rather than the claim's own
    algebraic text.

    A member is assembled from injected parts: the derive half (a
    structural or symbolic proof), the optional probe half (targeted
    trials; its presence is what makes route="best" meaningful for
    the member), and the optional suggestion gate naming the
    parameters the member is structurally relevant for. Both halves
    run inside the family verdict contract (see the guards above)."""

    def __init__(self, base_name: str, *, derive, probe=None,
                 suggest_targets=None,
                 probe_route="probe:algorithmic"):
        family_routes = {"derive": _guarded_safety_derive(derive)}
        if probe is not None:
            family_routes["probe:algorithmic"] = _guarded_safety_probe(probe)
        super().__init__(base_name, family_routes)
        self._suggest_targets = suggest_targets
        # the subroute a positive/negative empirical verdict is stamped
        # with: the probe is still found under the "probe:algorithmic"
        # key, but a member whose mechanism is more specific (fuzz +
        # shrink -> "probe:minimal_example") names it here so the record
        # reflects the real mechanism.
        self.probe_route = probe_route

    def suggest_targets(self, fn, facts) -> list:
        """The parameters this member is structurally relevant for,
        the suggestion gate, empty when the member registers none."""
        if self._suggest_targets is None:
            return []
        return sorted(self._suggest_targets(fn, facts))

    def suggested_route(self) -> str:
        """The route a suggestion for this member declares, read off
        what the member actually registers: a member with an empirical
        half cascades ("best"); a derive-only member never pretends
        a fallback exists."""
        return ("best" if "probe:algorithmic" in self._routes else "derive")


_WITNESS_BASES = (0.0, 1.0, -1.0, 2.0, 0.5, 3.0, -2.0)
_WITNESS_OFFSETS = (0.0, 0.5, -0.5, 1.0, -1.0, 1e-3, -1e-3)
_WITNESS_SCALAR_KINDS = frozenset({"scalar", "int", "unknown"})
_WITNESS_MAX_POINTS = 400
_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})


def _gap_satisfies(rel: str, gap_value: float) -> "bool | None":
    """Intent:
        Whether `lhs rel rhs` holds, given `gap_value = lhs - rhs`, or
        None when the gap is too close to zero for the reading to be
        trusted without being exactly zero.
    """
    if gap_value != 0.0 and abs(gap_value) < 1e-12:
        return None
    return {"==": gap_value == 0.0, "!=": gap_value != 0.0,
            "<": gap_value < 0.0, "<=": gap_value <= 0.0,
            ">": gap_value > 0.0, ">=": gap_value >= 0.0}.get(rel)


def _gap_at(gap, point: dict) -> "float | None":
    """Intent:
        The numeric value of a sympy expression at `point` (parameter
        name to number), or None when it is not a finite real number.
    """
    import sympy as _sympy
    try:
        value = gap.subs({s: _sympy.Float(point[s.name])
                          for s in gap.free_symbols if s.name in point}).evalf()
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if value.free_symbols or not value.is_real or not value.is_finite:
        return None
    return float(value)


def _definedness_witness(fn, facts, gaps: list, says_defined, domain,
                         premises: list) -> "tuple[dict | None, int]":
    """Intent:
        A concrete point where the real `fn` disagrees with a
        definedness claim: it raises where `says_defined(point)` is
        True, or returns where it is False. Returns `(point, executed)`,
        `point` None when no candidate reproduces, `executed` the number
        of candidate calls actually made.

    Notes:
        Candidates come in two passes, each executed as it is produced
        so the search stops at the first witness: a small grid of base
        values, then points around the zero sets of `gaps` (sympy
        expressions over the parameter symbols: the computed region's
        guards and the stated region), each gap solved for one
        parameter with the others held at a base value, the solution
        offset a little each way. A candidate must lie in `domain` and
        satisfy every premise in `premises` (sympy `(gap, relation)`
        pairs). Only scalar parameters are searched, and only a
        function whose signature binds them. The whole search runs
        under the fast wall-clock cap; a cap that fires ends it.
    """
    import inspect
    import itertools

    import sympy as _sympy

    from ._timeout import FAST_TIMEOUT_SECONDS as _FAST
    from ._timeout import _with_timeout as _capped
    from .domain import domain_contains

    params = list(facts.params)
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in params}
    if not params or any(k not in _WITNESS_SCALAR_KINDS for k in kinds.values()):
        return None, 0
    try:
        signature = inspect.signature(fn)
        signature.bind(**{p: 0 for p in params})
    except (TypeError, ValueError):
        return None, 0

    def grid():
        for base in _WITNESS_BASES:
            yield {p: base for p in params}
        for p in params:
            for value in _WITNESS_BASES:
                yield {**{q: 1.0 for q in params}, p: value}

    def near_zero_sets():
        for base in _WITNESS_BASES:
            for gap in gaps:
                for p in params:
                    sym = _sympy.Symbol(p, real=True)
                    if sym not in gap.free_symbols:
                        continue
                    held = gap.subs({_sympy.Symbol(q, real=True): base
                                     for q in params if q != p})
                    try:
                        roots = _sympy.solve(held, sym)
                    except (NotImplementedError, ValueError, TypeError):
                        continue
                    for root in roots:
                        if not getattr(root, "is_real", False) or root.free_symbols:
                            continue
                        for off in _WITNESS_OFFSETS:
                            yield {**{q: base for q in params},
                                   p: float(root) + off}

    def admitted(point: dict) -> bool:
        for p, v in point.items():
            if domain and p in domain:
                try:
                    if not domain_contains(v, domain[p]):
                        return False
                except (TypeError, ValueError):
                    return False
        for gap, rel in premises:
            value = _gap_at(gap, point)
            if value is None or _gap_satisfies(rel, value) is not True:
                return False
        return True

    executed = 0

    def search():
        nonlocal executed
        seen: set = set()
        for point in itertools.chain(grid(), near_zero_sets()):
            point = {p: (float(round(v)) if kinds[p] == "int" else v)
                     for p, v in point.items()}
            key = tuple(point[p] for p in params)
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > _WITNESS_MAX_POINTS:
                return None
            if not admitted(point):
                continue
            claimed = says_defined(point)
            if claimed is None:
                continue
            call = {p: (int(v) if kinds[p] == "int" else v)
                    for p, v in point.items()}
            executed += 1
            try:
                fn(**call)
            except Exception:
                returned = False
            else:
                returned = True
            if returned != claimed:
                return call
        return None

    try:
        found = _capped(search, _FAST)
    except TimeoutError:
        found = None
    return found, executed


def _witnessed_disproof(sketch: str, fn, facts, gaps, says_defined, domain,
                        premises):
    """Intent:
        The is_defined disproof as it may be reported: `disproven` with
        the executed witness as its counterexample when one reproduces,
        otherwise `undecided` carrying the corroboration flags (and the
        unexecutable flag when no candidate could be called at all).
    """
    from .gates import _fmt_point
    from .symbolic import ProofResult

    point, executed = _definedness_witness(fn, facts, gaps, says_defined,
                                           domain, premises)
    if point is not None:
        return ProofResult(
            "disproven", sketch=sketch,
            counterexample=_fmt_point(point, list(facts.params)),
            meta={"mathema.corroboration": "reproduced",
                  "mathema.witness_executed": True})
    meta = {"mathema.corroboration": "uncorroborated"}
    if executed == 0:
        meta["mathema.corroboration_unexecutable"] = True
        why = "no point in the domain could be executed"
    else:
        why = (f"no executed point reproduced it ({executed} points "
               f"checked in the domain)")
    return ProofResult(
        "undecided",
        sketch=f"{sketch}; uncorroborated disproof: {why}, and a "
               f"falsification needs an executed witness",
        meta=meta)


def _is_defined_derive(fn, facts, lhs_src: str, rhs_src: str,
                       relation: str, domain: dict | None = None,
                       tolerance: float | None = None,
                       assumption: list | None = None):
    """Intent:
        Region equivalence for a declared `is_defined` claim: the
        stated relation must match the freshly computed definedness
        region of the CURRENT body. Equivalent -> proven (drift-free);
        different -> disproven, with an executed witness (a point in
        the domain and premises where the real function raises though
        the claim says defined, or returns though the claim says it
        raises); else undecided with the fresh region in the sketch.
        The claim carries the domain and semantics; the live body
        validates it.

    Notes:
        Always returns a ProofResult, never None: an is_defined claim
        must not fall through to the ordinary relation prover, whose
        reading (is the relation TRUE?) is a different question from
        region equivalence. A structural disproof no executed point
        reproduces comes back undecided with the corroboration flags
        (`_witnessed_disproof`).
    """
    import ast as _ast

    import sympy as _sympy

    from .conjecture import _definedness_region
    from .grammar import normalize as _normalize
    from .symbolic import ProofResult
    from .symbolic._base import NotSymbolic, _expr_to_sympy

    computed = _definedness_region(fn, facts)

    def to_expr(src: str):
        env = {p: _sympy.Symbol(p, real=True) for p in facts.params}
        try:
            value = _expr_to_sympy(_ast.parse(_normalize(src),
                                              mode="eval").body, env)
        except (NotSymbolic, SyntaxError):
            return None
        return None if isinstance(value, tuple) else value

    # the SAME structural region the suggestion and expansion read;
    # one source, so the family can never disagree with them
    from .conjecture import _definedness_region_structured
    from .symbolic._base import REL_TEXT as rel_of
    computed_rels = [(rel_of[type(rel)], rel.lhs - rel.rhs)
                     for rel in _definedness_region_structured(fn, facts)]
    computed_gaps = [gap for _rel, gap in computed_rels]

    # the premises a witness must satisfy, as (gap, relation) pairs; a
    # premise with no numeric reading leaves no admissible witness
    premises: list = []
    for p_lhs, p_rel, p_rhs in assumption or ():
        p_l, p_r = to_expr(p_lhs), to_expr(p_rhs or "0")
        if p_l is None or p_r is None or p_rel not in _COMPARISONS:
            premises = [(_sympy.nan, "==")]
            break
        premises.append((p_l - p_r, p_rel))

    def disproof(sketch: str, gaps: list, says_defined):
        return _witnessed_disproof(sketch, fn, facts, gaps, says_defined,
                                   domain, premises)

    if relation == "is_defined":
        # the BARE predicate (`is_defined(f)` / `f is defined`) states
        # no region, so it reads as the other half of the overload:
        # f is defined EVERYWHERE. Proven when the body has no raise
        # region at all; falsified when it has one and a point in the
        # domain executes and raises. A stated region falls through
        # to the restriction reading below.
        if not computed:
            return ProofResult(
                "proven",
                sketch="is_defined: the body has no raise region, so "
                       "every call returns and f is defined on the whole "
                       "domain")
        return disproof(
            "is_defined: f is not defined everywhere, it returns "
            "only on " + " and ".join(computed)
            + "; state that region to claim the restriction",
            computed_gaps, lambda point: True)

    stated_l, stated_r = to_expr(lhs_src), to_expr(rhs_src or "0")
    if stated_l is None or stated_r is None:
        return ProofResult("undecided", sketch="is_defined: the stated "
                           "region isn't expressible over the function's "
                           "own parameters")
    stated_gap = stated_l - stated_r

    def stated_says_defined(point: dict) -> "bool | None":
        value = _gap_at(stated_gap, point)
        return None if value is None else _gap_satisfies(relation, value)

    witness_gaps = computed_gaps + [stated_gap]
    if not computed:
        return disproof(
            "is_defined: the current body has no raise regions at "
            "all; every call returns, so the definedness region "
            "is the whole domain, not the stated restriction. "
            "Claim totality with the bare `is_defined(f)`, which "
            "states no region",
            witness_gaps, stated_says_defined)
    if not computed_rels:
        return ProofResult("undecided", sketch="is_defined: computed region "
                           "not comparable")
    mirror = {">=": "<=", "<=": ">=", ">": "<", "<": ">"}
    from ._timeout import FAST_TIMEOUT_SECONDS as _FAST
    from ._timeout import _with_timeout as _capped

    def matches(comp_rel: str, comp_gap) -> bool:
        # note: a mirrored spelling (a >= b vs b <= a) compares with
        # the stated gap negated; == and != also accept the summed
        # form (A == -B states the same zero-set)
        gap = stated_gap
        if relation != comp_rel:
            if mirror.get(relation) == comp_rel:
                gap = -stated_gap
            else:
                return False
        try:
            diff = _capped(lambda: _sympy.simplify(gap - comp_gap), _FAST)
        except TimeoutError:
            raise
        except Exception:
            return False
        if diff == 0:
            return True
        if relation in ("==", "!="):
            try:
                summed = _capped(lambda: _sympy.simplify(gap + comp_gap),
                                 _FAST)
            except TimeoutError:
                raise
            except Exception:
                return False
            return summed == 0
        return False

    region_text = " and ".join(computed) if computed else "(empty)"
    for k, (comp_rel, comp_gap) in enumerate(computed_rels):
        try:
            if matches(comp_rel, comp_gap):
                part = ("" if len(computed_rels) == 1
                        else f" (conjunct {k + 1} of {len(computed_rels)})")
                return ProofResult(
                    "proven",
                    sketch=f"is_defined: the stated region matches the "
                           f"computed definedness region of the current "
                           f"body{part}, full region: {region_text}",
                    meta={"mathema.derive_route": "definedness_equivalence"})
        except TimeoutError:
            raise
    # provable drift: same relation as some conjunct, constant offset
    for comp_rel, comp_gap in computed_rels:
        gap = stated_gap
        if relation != comp_rel:
            if mirror.get(relation) == comp_rel:
                gap = -stated_gap
            else:
                continue
        try:
            diff = _capped(lambda: _sympy.simplify(gap - comp_gap), _FAST)
        except Exception:
            continue
        if diff is not None and diff.is_number and diff != 0:
            return disproof(
                f"is_defined: the stated region provably differs "
                f"from the current body's computed definedness "
                f"region, fresh region: {region_text}",
                witness_gaps, stated_says_defined)
    undecided_sketch = (f"is_defined: couldn't decide equivalence with the "
                        f"computed region, fresh region: {region_text}")
    # an executed disagreement settles what the structural comparison
    # could not
    point, _executed = _definedness_witness(fn, facts, witness_gaps,
                                            stated_says_defined, domain,
                                            premises)
    if point is not None:
        from .gates import _fmt_point
        return ProofResult(
            "disproven",
            sketch=f"is_defined: the stated region disagrees with the "
                   f"current body at an executed point, fresh region: "
                   f"{region_text}",
            counterexample=_fmt_point(point, list(facts.params)),
            meta={"mathema.corroboration": "reproduced",
                  "mathema.witness_executed": True})
    return ProofResult("undecided", sketch=undecided_sketch)


def _matrix_property(name: str):
    from .matrices import PROPERTIES
    return PROPERTIES.get(name)


def _synth_matrix(n: int, rng: random.Random) -> list:
    return [[rng.uniform(-5, 5) for _ in range(n)] for _ in range(n)]


def _violating_matrix(prop, n: int, rng: random.Random,
                      tries: int = 20) -> "list | None":
    """A random n-by-n matrix that does NOT have `prop`, for the guard
    check; None when none turned up (a property almost every random
    matrix satisfies, so the guard question is not meaningful)."""
    for _ in range(tries):
        m = _synth_matrix(n, rng)
        if prop.check(m) is False:
            return m
    return None


def _matrix_output_probe(prop):
    """The output/expression check: per trial synthesize every
    parameter, evaluate the predicate's argument expression (which
    calls `f` and may combine matrices), and test the resulting value
    for the property. Holds when every evaluable value has it,
    falsifies with the witnessing arguments when one does not, skips
    when the property could not be decided on any value (a spectral
    check with no numpy)."""
    def probe(fn, facts, cj, domain, rng, trials):
        import ast as _ast

        try:
            arg_ast = _ast.parse(cj.lhs, mode="eval").body
        except SyntaxError:
            return None
        undecided = [0]

        def trial(args):
            filled = [_synth_matrix(rng.randint(1, 5), rng)
                      if a is None else a for a in args]
            env = dict(zip(facts.params, filled))
            try:
                value = _eval_matrix_expr(arg_ast, env, fn)
            except Exception:
                return None
            got = prop.check(value)
            if got is None:
                undecided[0] += 1
                return None
            if got is True:
                return True
            return f"{_fmt(tuple(filled))}: result is not {prop.name[3:]}"

        verdict, checked, cx = _probe_trials(
            fn, facts, _first_matrix_param(facts), domain, rng, trials, trial)
        if checked == 0 and undecided[0]:
            return ("skipped", 0, None,
                    None)
        return (verdict, checked, cx, None)
    return probe


def _matrix_guard_probe(prop):
    """The precondition/guard check for a bare-parameter predicate
    (`is_symmetric(A)`): does the function REJECT an argument that
    lacks the property, the value-analogue of excluded_outside_domain.
    Holds when a synthesized violating input raises or returns None;
    falsifies with that input when the function silently accepts it."""
    def probe(fn, facts, cj, domain, rng, trials):
        target = cj.lhs.strip()
        if target not in facts.params:
            return None
        checked = 0
        for _ in range(trials):
            bad = _violating_matrix(prop, rng.randint(2, 5), rng)
            if bad is None:
                continue
            checked += 1
            args = _synth_other_params(fn, facts, target, domain, rng)
            try:
                out = _call_with_target(fn, facts, target, args, bad)
            except Exception:
                continue     # rejected: the guard fired
            if out is None:
                continue     # a graceful decline is a guard too
            return ("falsified", checked,
                    f"{prop.name[3:]} not enforced: accepted "
                    f"{_fmt(tuple([bad]))}", None)
        if checked == 0:
            return ("skipped", 0, None, None)
        return ("holds", checked, None, None)
    return probe


def _first_matrix_param(facts) -> str:
    for p in facts.params:
        if facts.param_kinds.get(p) == "sequence":
            return p
    return facts.params[0] if facts.params else ""


def _eval_matrix_expr(node, env: dict, fn):
    """Evaluate a matrix predicate's argument expression over `env`:
    `f(...)` calls the real function, `A @ B`/`A.T`/`det`/`inv`/
    `trace` and elementwise `+`/`-`/scalar-`*` are computed on concrete
    values. numpy when present (fast, full operator set); a small
    pure-Python core otherwise for the common shapes."""
    import ast as _ast

    def ev(n):
        if isinstance(n, _ast.Name):
            return env[n.id]
        if isinstance(n, _ast.Constant):
            return n.value
        if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name):
            args = [ev(a) for a in n.args]
            if n.func.id == "f":
                return fn(*args)
            return _matrix_call(n.func.id, args)
        if isinstance(n, _ast.Attribute) and n.attr == "T":
            return _transpose(ev(n.value))
        if isinstance(n, _ast.BinOp):
            return _matrix_binop(n.op, ev(n.left), ev(n.right))
        raise ValueError(f"unsupported matrix expression {_ast.unparse(n)!r}")

    return ev(node)


def _to_np(value):
    from .matrices import _numpy
    np = _numpy()
    return (np, np.asarray(value, dtype=float)) if np is not None else (None, value)


def _transpose(m):
    np, a = _to_np(m)
    if np is not None:
        return a.T
    return [list(row) for row in zip(*m)]


def _matrix_call(name: str, args: list):
    np, _ = _to_np(args[0]) if args else (None, None)
    if name == "det":
        if np is None:
            raise ValueError("det needs numpy")
        return float(np.linalg.det(np.asarray(args[0], dtype=float)))
    if name == "inv":
        if np is None:
            raise ValueError("inv needs numpy")
        return np.linalg.inv(np.asarray(args[0], dtype=float))
    if name == "trace":
        a = args[0]
        return sum(a[i][i] for i in range(len(a))) if np is None             else float(np.trace(np.asarray(a, dtype=float)))
    if name == "transpose":
        return _transpose(args[0])
    raise ValueError(f"unsupported matrix function {name!r}")


def _matrix_binop(op, left, right):
    import ast as _ast

    from .matrices import _numpy
    np = _numpy()
    if isinstance(op, _ast.MatMult):
        if np is not None:
            return np.asarray(left, dtype=float) @ np.asarray(right, dtype=float)
        n, m, p = len(left), len(right), len(right[0])
        return [[sum(left[i][k] * right[k][j] for k in range(m))
                 for j in range(p)] for i in range(n)]
    if isinstance(op, (_ast.Add, _ast.Sub)):
        sign = 1 if isinstance(op, _ast.Add) else -1
        if np is not None:
            return np.asarray(left, dtype=float) + sign * np.asarray(right, dtype=float)
        return [[left[i][j] + sign * right[i][j] for j in range(len(left[0]))]
                for i in range(len(left))]
    if isinstance(op, _ast.Mult):
        scalar, mat = (left, right) if not isinstance(left, list) else (right, left)
        if np is not None:
            return float(scalar) * np.asarray(mat, dtype=float)
        return [[scalar * v for v in row] for row in mat]
    raise ValueError("unsupported matrix operator")


_MATRIX_PROBE_SEED = 0x9E3779B9


def _random_matrix(rows: int, cols: int, rng: random.Random) -> list:
    """A plain rows-by-cols matrix of reals, for a matrix parameter that
    carries a shape but no structure to synthesise from."""
    return [[rng.uniform(-5, 5) for _ in range(cols)] for _ in range(rows)]


def _as_list(value):
    """A sampled matrix as nested Python lists, whether it came back a
    numpy array or already a list, so a counterexample renders plainly."""
    return value.tolist() if hasattr(value, "tolist") else value


def _matrix_close(a, b, tol: float) -> bool:
    """Whether two evaluated results (each a scalar or a matrix) agree to
    `tol`. numpy when present, an elementwise walk otherwise."""
    from .matrices import _numpy
    np = _numpy()
    if np is not None:
        aa, bb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        return aa.shape == bb.shape and bool(
            np.allclose(aa, bb, rtol=0, atol=tol))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    try:
        return (len(a) == len(b)
                and all(_matrix_close(x, y, tol) for x, y in zip(a, b)))
    except TypeError:
        return False


def _relation_holds(lv, rv, relation: str, tol: float) -> bool:
    """Whether a sampled draw satisfies the claim's relation: `==`/`~=`
    by closeness, `!=` by its negation, and the orderings on the scalar
    results (a determinant, a trace). A strict `<`/`>` gets no tolerance
    credit (`0 > 0` must fail); a closed `<=`/`>=` gets the slack a float
    wobble can need, mirroring the ordinary probe's own rule. Raises
    TypeError when an ordering is asked of matrix-valued sides (an
    undefined matrix ordering), which the caller treats as unsampleable."""
    if relation in ("==", "~="):
        return _matrix_close(lv, rv, tol)
    if relation == "!=":
        return not _matrix_close(lv, rv, tol)
    a, b = float(lv), float(rv)
    if relation == "<=":
        return a <= b + tol
    if relation == ">=":
        return a >= b - tol
    if relation == "<":
        return a < b
    return a > b


def matrix_relation_probe(cj, fn, dims: dict, structures: dict,
                          statement: str, note: str,
                          rounds: int = 40) -> "Probe | None":
    """Sample concrete matrices for a matrix-algebra relation claim the
    symbolic backend could not close, and decide it by evaluation:
    `holds` when both sides agree on every draw, `falsified` with the
    witnessing matrices when a draw disagrees. Structure markers and
    premises (`structures`) narrow each draw to a matrix that has the
    property. Returns None when the claim is not sampleable here (an
    operation such as `det`/`inv` that needs numpy while numpy is
    absent, or an expression outside the evaluation core); the caller
    then reports the honest derive `unknown`."""
    import ast as _ast

    from .linalg import undeclared_matrix_operands
    from .matrices import synth_for
    from .records import Probe
    try:
        lhs_ast = _ast.parse(cj.lhs, mode="eval").body
        rhs_ast = _ast.parse(cj.rhs or "", mode="eval").body
    except SyntaxError:
        return None
    if undeclared_matrix_operands((cj.lhs, cj.rhs), dims):
        # a name used as a matrix that `dims` never sized cannot be put
        # in `env`, so every draw below would fail inside the per-round
        # `except Exception` and the loop would spend its whole budget
        # to arrive at the same decline. The symbolic route carries the
        # reason on the result the caller reports.
        return None
    tol = cj.tolerance if cj.tolerance is not None else 1e-6
    rng = random.Random(_MATRIX_PROBE_SEED)
    checked = 0
    for _ in range(rounds):
        sizes: dict = {}
        env: dict = {}
        for p, (rd, cd) in dims.items():
            r = rd if isinstance(rd, int) else sizes.setdefault(
                rd, rng.randint(2, 4))
            c = cd if isinstance(cd, int) else sizes.setdefault(
                cd, rng.randint(2, 4))
            props = structures.get(p, ())
            env[p] = (synth_for(props, r, rng) if props and r == c
                      else _random_matrix(r, c, rng))
        try:
            lv = _eval_matrix_expr(lhs_ast, env, fn)
            rv = _eval_matrix_expr(rhs_ast, env, fn)
        except ValueError:
            return None       # needs numpy (det/inv), or outside the core
        except Exception:
            continue          # a degenerate draw (e.g. a singular inv)
        try:
            holds = _relation_holds(lv, rv, cj.relation, tol)
        except TypeError:
            return None       # an ordering over matrix-valued sides: undefined
        checked += 1
        if not holds:
            witness = _fmt(tuple(_as_list(env[p]) for p in dims),
                           names=tuple(dims))
            return Probe(cj.name, statement, "falsified", n=checked,
                         counterexample=witness, note=note, route="probe",
                         sketch="a sampled matrix violates the relation")
    if checked == 0:
        return None
    return Probe(cj.name, statement, "holds", n=checked, note=note,
                 route="probe",
                 sketch=f"relation held on {checked} sampled matrix draws")


class MatrixPropertyFamily:
    """The claim family for every matrix structure predicate. One
    class, driven by the property registry: `is_symmetric(f(A))`
    checks the output, `is_symmetric(A)` checks that the function
    guards the precondition. The examine route runs the empirical
    check (a symbolic derive half lands with the MatrixSymbol
    backend)."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        base = claim_name.split("[", 1)[0]
        return _matrix_property(base) is not None

    def routes(self) -> dict:
        return {"probe:algorithmic": self._probe}

    def _probe(self, fn, facts, cj, domain, rng, trials):
        prop = _matrix_property(cj.relation)
        if prop is None:
            return None
        bare = cj.lhs.strip() in facts.params
        inner = (_matrix_guard_probe(prop) if bare
                 else _matrix_output_probe(prop))
        return inner(fn, facts, cj, domain, rng, trials)


def _check_sorted_output(out):
    """True when `out` is a sorted sequence, False when out of order,
    None when it is not a sequence or its elements do not order."""
    try:
        seq = list(out)
    except TypeError:
        return None
    try:
        return seq == sorted(seq)
    except TypeError:
        return None


def _check_output_never_none(out):
    """True unless the output is None."""
    return out is not None


_OUTPUT_CHECKS = {
    "is_sorted_output": _check_sorted_output,
    "output_never_none": _check_output_never_none,
}


def _output_predicate_probe(check):
    """A probe over a function's OUTPUT value: per trial synthesize every
    argument by its kind, call f, and test the returned value with
    `check` (True has the property, False does not with a witness, None
    undecided/uncallable this round)."""
    def probe(fn, facts, cj, domain, rng, trials):
        def trial(_args):
            filled = [_synth(facts.param_kinds.get(p, "scalar"), rng,
                             (domain or {}).get(p)) for p in facts.params]
            try:
                with _pinned_float_env():
                    out = fn(*filled)
            except Exception:
                return None
            got = check(out)
            if got is None:
                return None
            if got is True:
                return True
            return f"{_fmt(tuple(filled))}: output {out!r} fails {cj.relation}"
        target = facts.params[0] if facts.params else ""
        return _probe_trials(fn, facts, target, domain, rng, trials, trial)
    return probe


class OutputPredicateFamily:
    """One output-contract predicate over a function's OUTPUT value
    (`is_sorted_output(f(xs))`, `output_never_none(f(x))`): sample the
    arguments, call f, test the returned value. Empirical only, the
    property is of the runtime value, not of the code, so there is no
    derive half."""

    def __init__(self, name: str, check):
        self._name = name
        self._probe = _output_predicate_probe(check)

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return claim_name.split("[", 1)[0] == self._name

    def routes(self) -> dict:
        return {"probe:algorithmic": self._probe}


def _is_nonfinite(out) -> bool:
    """True when a value is a silent non-finite number (nan/inf), scalar
    or numpy array; False for a genuinely non-numeric value, which is not
    this predicate's concern."""
    import math
    if isinstance(out, bool):
        return False
    if isinstance(out, (int, float)):
        return math.isnan(out) or math.isinf(out)
    try:
        import numpy as np
    except ImportError:
        return False
    try:
        arr = np.asarray(out, dtype=float)
    except (TypeError, ValueError):
        return False
    return not bool(np.isfinite(arr).all())


def _is_compendium_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                               relation: str, domain: dict | None = None,
                               tolerance: float | None = None):
    """Structural half of is_compendium_safe: decline. Whether a covered
    library call ever reaches its nan region over the declared domain is
    established empirically by the probe (which samples the domain and
    the boundary specials), not proved symbolically here."""
    return None


def _compendium_probe(fn, facts, cj, domain: dict, rng, trials: int):
    """Empirical half of is_compendium_safe(<library>): sample the
    function's inputs (respecting a declared domain, and hitting the
    negative / out-of-unit boundary specials that trigger a covered
    library's nan regions), call f, and check the output is FINITE. A
    silent nan/inf produced through an unguarded call into a covered
    library function (numpy.sqrt on a negative, numpy.arcsin past 1) is
    the counterexample; a finite result on every trial holds. Declines
    when f does not call a covered function of the named library."""
    from .compendium import libraries_called
    library = cj.lhs.strip()
    if library not in libraries_called(fn, facts):
        return None

    # empty-sequence trials up front: an empty reduction (numpy.mean of
    # []) returns nan silently, and the random sampler draws 2..8-element
    # sequences, never the empty boundary. One empty trial per sequence
    # parameter catches it.
    empties = [p for p in facts.params
               if facts.param_kinds.get(p) == "sequence"]

    def _sample(force_empty=None):
        return [[] if p == force_empty
                else _synth(facts.param_kinds.get(p, "scalar"), rng,
                            (domain or {}).get(p))
                for p in facts.params]

    def trial(_args):
        filled = _sample(empties.pop() if empties else None)
        try:
            with _pinned_float_env():
                out = fn(*filled)
        except Exception:
            return None
        if _is_nonfinite(out):
            return (f"{_fmt(tuple(filled))}: output {out!r} is a silent "
                    f"non-finite value from an unguarded {library} call")
        return True

    target = facts.params[0] if facts.params else ""
    return _probe_trials(fn, facts, target, domain, rng,
                         max(trials, len(facts.params) + 4), trial)


def _register_builtin_claim_families() -> None:
    from . import families as _families
    import functools as _functools
    from .matrices import PROPERTIES as _MATRIX_PROPS
    _matrix_family = MatrixPropertyFamily()
    for _name in _MATRIX_PROPS:
        _families.register(_name, _matrix_family)
    # output-contract predicates over a function's OUTPUT value
    for _oname, _ocheck in _OUTPUT_CHECKS.items():
        _families.register(_oname, OutputPredicateFamily(_oname, _ocheck))
    _families.register("monotonic_increasing", _NamedClaimFamily(
        "monotonic_increasing",
        {"probe:algorithmic": _functools.partial(_monotone_probe, increasing=True)}))
    _families.register("monotonic_decreasing", _NamedClaimFamily(
        "monotonic_decreasing",
        {"probe:algorithmic": _functools.partial(_monotone_probe, increasing=False)}))
    for _kind in ("affine", "convex", "concave"):
        _families.register(_kind, _NamedClaimFamily(
            _kind, {"probe:algorithmic": _functools.partial(_second_difference_probe, kind=_kind)}))
    _families.register("is_defined", _NamedClaimFamily(
        "is_defined", {"derive": _is_defined_derive}))
    # the implementation-safety members, one SafetyFamily each: the
    # derive/probe halves and the suggestion gate are the member's
    # injected parts, and every half runs inside the family verdict
    # contract. is_missing_safe carries a real probe fallback, unlike
    # the other two domain-safety predicates: its runtime half
    # (calling fn with a literal NaN) is empirical, so it reports
    # under a probe route, never relabeled as derive.
    _families.register("is_numerically_stable", SafetyFamily(
        "is_numerically_stable", derive=_is_numerically_stable_derive))
    _families.register("is_builtin_safe", SafetyFamily(
        "is_builtin_safe", derive=_is_builtin_safe_derive,
        probe=_builtin_probe,
        suggest_targets=_restricted_domain_targets))
    _families.register("is_pole_safe", SafetyFamily(
        "is_pole_safe", derive=_is_pole_safe_derive,
        probe=_pole_probe,
        suggest_targets=_pole_bearing_params))
    _families.register("is_missing_safe", SafetyFamily(
        "is_missing_safe", derive=_is_missing_safe_derive,
        probe=_missing_probe,
        suggest_targets=lambda fn, facts: _missing_guard_params(facts)))
    from .hazards import _overflow_prone_params, _type_discipline_params
    _families.register("is_extremity_safe", SafetyFamily(
        "is_extremity_safe", derive=_is_extremity_safe_derive,
        probe=_extreme_probe,
        suggest_targets=_overflow_prone_params))
    _families.register("is_representation_safe", SafetyFamily(
        "is_representation_safe", derive=_is_representation_safe_derive,
        probe=_representation_probe,
        suggest_targets=_type_discipline_params))
    from .hazards import _emptiness_guard_params
    _families.register("is_empty_safe", SafetyFamily(
        "is_empty_safe", derive=_is_empty_safe_derive,
        probe=_empty_probe,
        suggest_targets=lambda fn, facts: _emptiness_guard_params(facts)))
    # is_arbitrary_input_safe fuzzes a string parameter and shrinks any
    # crash to a minimal witness, so its empirical verdict is stamped
    # probe:minimal_example. Suggested for every bare-string parameter.
    from .hazards import _string_input_params
    _families.register("is_arbitrary_input_safe", SafetyFamily(
        "is_arbitrary_input_safe", derive=_is_arbitrary_input_safe_derive,
        probe=_arbitrary_input_probe,
        suggest_targets=lambda fn, facts: _string_input_params(facts),
        probe_route="probe:minimal_example"))
    # is_compendium_safe(<library>): the function never silently produces
    # a non-finite output (nan/inf) through an unguarded call into a
    # compendium-covered library function. Parameterised by library
    # (is_compendium_safe[numpy]); expandable by adding a compendium YAML.
    from .compendium import libraries_called as _libs_called
    _families.register("is_compendium_safe", SafetyFamily(
        "is_compendium_safe", derive=_is_compendium_safe_derive,
        probe=_compendium_probe,
        suggest_targets=lambda fn, facts: sorted(_libs_called(fn, facts))))
    # excluded_outside_domain is never battery-suggested (no
    # suggest_targets): it is declared, by the author, the
    # `excluding` keyword, or @enforce_domain's auto-declaration
    _families.register("excluded_outside_domain", SafetyFamily(
        "excluded_outside_domain", derive=_excluded_outside_domain_derive,
        probe=_excluded_probe))
    # the stateless cluster's name-keyed members (claim NAMES, not
    # predicate relations). is_deterministic is the STRONG one: the
    # generic f(...) == f(...) re-evaluation loop is its empirical
    # half, so only a derive half registers. is_reproducible is
    # weaker (up to an RNG seed): its probe runs paired calls with
    # the recognized RNG states captured and restored.
    _families.register("is_deterministic", SafetyFamily(
        "is_deterministic", derive=_is_deterministic_derive))
    _families.register("is_reproducible", SafetyFamily(
        "is_reproducible", derive=_is_reproducible_derive,
        probe=_reproducible_probe))
    _families.register("is_state_safe", SafetyFamily(
        "is_state_safe", derive=_is_state_safe_derive,
        probe=_state_probe))
