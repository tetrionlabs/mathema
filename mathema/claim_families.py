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
  at all (`is_numerically_stable`'s pole-containment disproof,
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

from ._signatures import module_scope
import math
import random

from ._sampling import _finite_bounds as _finite_bounds, _synth_scalar as _synth_scalar
from .f import _is_nonfinite as _is_nonfinite
from .grammar import Domain
# hazard knowledge (which parameters face which hazard kinds, and the
# restricted builtins' own accepted ranges) lives in mathema.hazards,
# the shared registry; re-exported names keep this module's public
# shape for existing importers.
from .hazards import (_SAFE_RANGE as _SAFE_RANGE,
                      _missing_guard_params as _missing_guard_params,
                      _pole_bearing_params as _pole_bearing_params,
                      _restricted_domain_targets as _restricted_domain_targets)
from .probing import (_fmt, _pinned_float_env, _points_for_probe, _pole_safety,
                      _poles_by_var, _synth, call_arguments)
from .runtime_types import SEQUENCE_KINDS
from ._signatures import callable_signature

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
        args.append(_synth(k, rng, domain.get(p) if k not in SEQUENCE_KINDS
                           else None))
    return args


def _call_with_target(fn, facts, target: str, args: list, value):
    values = dict(zip(facts.params, args))
    values[target] = value
    call_args, call_kwargs = call_arguments(fn, facts.params, values)
    return fn(*call_args, **call_kwargs)


def _placed(values: dict, rng: random.Random, keep=(),
            solve: bool = True) -> "dict | None":
    """Intent:
        `values` (parameter to drawn value) on the surface of the
        running claim's equality premises (`_premises.current()`),
        leaving the parameters in `keep` as drawn: a premise-drawn
        parameter is redrawn on its surface and, when `solve`, the
        solved equality's variable is computed from the others. None
        when the solved value falls outside its declared bound (the
        point is not a trial); `values` unchanged when the claim has
        no premise.
    """
    from . import _premises
    guard = _premises.current()
    if guard is None:
        return values
    only = frozenset(values) - frozenset(keep)
    return guard.place(values, rng, only=only, solve=solve)


def _admitted(values: dict) -> bool:
    """Whether `values` is inside the running claim's premises; True
    when the claim has none."""
    from . import _premises
    guard = _premises.current()
    return guard is None or guard.admits_point(values)


def _probe_trials(fn, facts, target: str, domain: dict, rng: random.Random,
                  trials: int, trial):
    """Intent:
        The one trial loop every probe:algorithmic technique runs:
        synthesize the non-target arguments (a parameter an equality
        premise fixes is drawn on its surface), hand them to `trial`,
        count only the evaluable rounds, stop at the first
        counterexample. A round whose call lies outside the claim's
        premises (`_premises.PremiseRejected`) is not a trial.

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
    from ._premises import PremiseRejected
    checked = 0
    for _ in range(trials):
        args = _synth_other_params(fn, facts, target, domain, rng)
        placed = _placed(dict(zip(facts.params, args)), rng, keep=(target,),
                         solve=False)
        if placed is None:
            continue
        args = [placed[p] for p in facts.params]
        try:
            outcome = trial(args)
        except PremiseRejected:
            # a call outside the claim's premises is not a trial
            continue
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


def _held_text(facts, target: str, args: list) -> str:
    """Intent:
        The parameters a pairwise trial held fixed while it moved
        `target`, as `name = value` pairs (a large container by its
        shape and a first row); empty for a one-parameter function.
    """
    from ._shapes import witness_text
    return ", ".join(f"{p} = {witness_text(v) or _witness_value(v)}"
                     for p, v in zip(facts.params, args) if p != target)


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
        held = _held_text(facts, target, args)
        return (f"{target}={x1:.6g} -> {v1!r}, {target}={x2:.6g} -> {v2!r}"
                f"{f' at {held}' if held else ''} (not {direction})")

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


def _raise_or_nonfinite(out) -> "str | None":
    """What went wrong with a call's return value at a hazard point
    (`returned inf`, `returned nan`), or None when the value is finite
    or not a number at all (a non-numeric return is out of scope for a
    numeric-hazard check)."""
    try:
        as_float = float(out)
    except (TypeError, ValueError):
        return None
    if as_float != as_float or math.isinf(as_float):
        return f"returned {out!r}"
    return None


def _executed_family_witness(fn, facts, target: str, value, domain: dict,
                             failure=None, draws: int = 8):
    """Intent:
        Run the real function with `target` fixed at `value` (every
        other parameter drawn inside the declared domain) and report
        the first failure: `raised <Exception>` for a raise, else
        whatever `failure(returned_value)` names. Returns
        (what_happened or None, number_of_calls_made).

    Notes:
        With a single parameter one call is the whole question; with
        more, up to `draws` draws of the other parameters are tried,
        from a fixed seed so the witness is reproducible. A failing
        call is a witness for the claim at that point; a clean run at
        every draw is not evidence the other way, only the absence of
        a witness.
    """
    rng = random.Random(0)
    rounds = 1 if len(facts.params) == 1 else draws
    executed = 0
    for _ in range(rounds):
        args = _synth_other_params(fn, facts, target, domain, rng)
        executed += 1
        try:
            with _pinned_float_env():
                out = _call_with_target(fn, facts, target, args, value)
        except Exception as exc:
            return f"raised {type(exc).__name__}", executed
        what = failure(out) if failure is not None else None
        if what is not None:
            return what, executed
    return None, executed


def _uncorroborated_family_disproof(sketch: str, why: str,
                                    reason: "str | None" = None):
    """Intent:
        A family's structural disproof that no executed call
        reproduced, as it may be reported: `undecided`, carrying the
        corroboration flag every uncorroborated disproof carries, and
        `reason` as `mathema.corroboration_reason` when given.
    """
    from .symbolic import ProofResult
    meta = {"mathema.corroboration": "uncorroborated"}
    if reason is not None:
        meta["mathema.corroboration_reason"] = reason
    return ProofResult(
        "undecided",
        sketch=f"{sketch}; uncorroborated disproof: {why}, and a "
               f"falsification needs an executed witness",
        meta=meta)


def _pole_exclusion_proof(fn, facts, domain: dict, params,
                          proven_sketch: str):
    """Intent:
        The pole-vs-declared-domain containment proof both pole-hazard
        derive routes share: when any of `params` has a pole provably
        inside its own bound, the real function is called there
        (`_witnessed_pole`), proven with `proven_sketch` when every
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
            return _witnessed_pole(fn, facts, domain, p, contained[0])
        if verdict == "undecided":
            return None
    if not checked_any:
        return None
    return ProofResult("proven", sketch=proven_sketch)


def _witnessed_pole(fn, facts, domain: dict, param: str, pole_text: str):
    """Intent:
        The pole-containment disproof as it may be reported: the real
        function is called at the pole's machine spelling; a raise or
        a non-finite return there is `disproven` with that executed
        witness, anything else is the uncorroborated `undecided`.

    Notes:
        An irrational pole (sqrt(2)) has no exact float spelling, so
        the call lands beside it, where the code may well return a
        large finite value: the pole exists in exact arithmetic and
        floating point does not reproduce it, so the disproof is not
        reported as one, and its reason says so.
    """
    import sympy
    from .hazards import _admitted_spelling
    from .symbolic import ProofResult
    sketch = f"{param} = {pole_text} is a pole inside the declared domain"
    try:
        value = _admitted_spelling(float(sympy.sympify(pole_text)),
                                   domain.get(param))
    except Exception:
        value = None
    if value is None:
        return _uncorroborated_family_disproof(
            sketch, f"the pole {pole_text} has no machine spelling the "
                    f"domain admits, so no call could be made there")
    what, executed = _executed_family_witness(
        fn, facts, param, value, domain, failure=_raise_or_nonfinite)
    if what is None:
        from .corroboration import (EXACT_ARITHMETIC_ONLY,
                                    EXACT_ARITHMETIC_ONLY_NOTE)
        return _uncorroborated_family_disproof(
            sketch, f"{EXACT_ARITHMETIC_ONLY_NOTE}: the call at "
                    f"{param} = {value!r} returned a finite value "
                    f"({executed} call(s) made)",
            reason=EXACT_ARITHMETIC_ONLY)
    spelled = (f"{param} = {value!r}" if pole_text == repr(value)
               else f"{param} = {value!r} (the pole {pole_text})")
    return ProofResult(
        "disproven", sketch=sketch,
        counterexample=f"{spelled} {what}",
        meta={"mathema.corroboration": "reproduced",
              "mathema.witness_executed": True})


def _is_numerically_stable_derive(fn, facts, lhs_src: str, rhs_src: str,
                               relation: str, domain: dict | None = None,
                               tolerance: float | None = None):
    """Intent:
        A derive-route half for is_numerically_stable: when a
        declared-domain parameter's own pole provably lies inside its
        bound (the reasoning is_pole_safe[param] uses, via the shared
        _pole_exclusion_proof), disproven if the executed call there
        raises or returns a non-finite value, else the uncorroborated
        undecided; None (falling through to the probe check) otherwise.

    Notes:
        Pole exclusion never proves the claim. `finite_no_error(f, ...)
        == 1` also fails on an overflow (exp past 709.78) and on a NaN,
        neither of which is a pole, so with every pole excluded the
        claim is still open and the probe decides it. lhs_src/rhs_src/
        relation are unused, kept for protocol uniformity with every
        other derive-route family.
    """
    domain = domain or {}
    if not domain:
        return None
    proof = _pole_exclusion_proof(
        fn, facts, domain, list(domain),
        proven_sketch="every declared-domain parameter's own poles are "
                      "excluded by its bound")
    if proof is None or proof.status == "proven":
        return None
    return proof


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
        every other name. Every other name here reduces to "is dom a
        subset of this function's own safe range" (its `_SAFE_RANGE`
        row) via _domain_pieces/_range_piece_verdict/
        _combine_piece_verdicts, the same three-step shape whichever
        name it is.
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
        found for it, disproven when one is provably inside and the
        executed call there fails, undecided otherwise (falling through to _pole_probe's admitted-pole
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
    if facts.param_kinds.get(target) in SEQUENCE_KINDS:
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
    from .records import operational_range
    target = cj.lhs
    if target not in facts.params:
        return None
    pinf = operational_range(cj)
    candidates = _extreme_candidates(domain.get(target),
                                     pseudo_infinity=pinf)
    return _hazard_value_probe(
        fn, facts, cj, domain, rng, trials, candidates,
        lambda value, what: (f"{target} = {value:.6g} is admitted by the "
                             f"declared domain but the computation "
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
    from ._process_state import writer_calls
    from .hazards import _write_free
    from .symbolic import ProofResult, lift
    if writer_calls(fn, facts):
        # a bare call of a process-state writer (os.putenv, random.seed,
        # a draw from the global generator) is a write site the
        # certificate below does not see
        return None
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
    snapshot the function's module globals (data entries only) and the
    process-wide state (`_process_state`) before a call, compare after,
    an observed mutation falsifies naming the mutated target. The
    process-wide state is put back after every call. Clean rounds hold:
    an unexecuted branch may still hide a write, so trials never
    establish this fact."""
    import copy
    import types

    from . import _process_state
    if not facts.params:
        return None
    target = facts.params[0]
    module_dict = module_scope(fn)

    def data_globals():
        out = {}
        for name, value in module_dict.items():
            if name.startswith("__"):
                continue
            if isinstance(value, (types.ModuleType, types.FunctionType,
                                  types.BuiltinFunctionType, types.MethodType,
                                  type)):
                continue
            out[name] = value
        return out

    def trial(args):
        call_args = list(args)
        call_args[facts.params.index(target)] = _synth(
            facts.param_kinds.get(target, "unknown"), rng,
            domain.get(target))
        placed = _placed(dict(zip(facts.params, call_args)), rng)
        if placed is None:
            return None
        call_args = [placed[p] for p in facts.params]
        try:
            originals = copy.deepcopy(call_args)
        except Exception:
            return None
        before = data_globals()
        try:
            before_copy = {k: copy.deepcopy(v) for k, v in before.items()}
        except Exception:
            before_copy = None
        isolation = None
        raised = None
        try:
            with _process_state.isolated(fn) as isolation, \
                    _pinned_float_env():
                fn(*call_args)
        except Exception as exc:
            raised = exc
        finally:
            if isolation is not None and isolation.restore_failed:
                restore_failed.extend(isolation.restore_failed)
        env_calls = isolation.c_environ_calls
        changed = isolation.changes()
        then = (f", and then raised {type(raised).__name__}"
                if raised is not None else "")
        called = (f"calling {getattr(fn, '__name__', 'f')} with "
                  + ", ".join(f"{p} = {_witness_value(v)}"
                              for p, v in zip(facts.params, originals)))
        if changed:
            return f"{called} changed {'; '.join(changed)}{then}"
        if raised is not None and not env_calls:
            return None   # a raising point that changed nothing says nothing
        if env_calls:
            # a direct os.putenv or os.unsetenv: a write to the C
            # environment, which os.environ does not show
            writer, name = env_calls[0]
            return (f"{called} ran {writer}({name!r}), which changes the "
                    f"environment this process passes to its subprocesses, "
                    f"where os.environ cannot see it{then}")
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

    restore_failed: list = []
    result = _probe_trials(fn, facts, target, domain, rng,
                           max(trials // 4, 8), trial)
    if restore_failed:
        said = sorted(set(restore_failed))
        return (*result, None, {
            "mathema.restore_failed": said,
            "mathema.caveat": ("mathema could not put the process back "
                               "after a trial: " + "; ".join(said))})
    return result


def _excluded_outside_domain_derive(fn, facts, lhs_src: str, rhs_src: str,
                                    relation: str, domain: dict | None = None,
                                    tolerance: float | None = None):
    """Intent:
        The structural half of excluded_outside_domain[param]: the
        function must raise on any input outside param's declared
        domain. Proven when the function is wrapped by
        @enforce_domain (values) or @enforce_dimensions (shape) covering
        this parameter, rejection by construction, the wrapper checks
        every call before the body runs. Undecided (None) otherwise:
        the trials at concrete out-of-domain values decide empirically.

    Notes:
        This claim is never battery-suggested: it is DECLARED,
        explicitly, via the `excluding` keyword, or automatically by
        @enforce_domain or @enforce_dimensions itself (the decorator
        that makes it true also declares it). rhs_src/relation/tolerance
        kept for protocol uniformity.
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
    shaped = getattr(fn, "__mathema_enforced_dimensions__", None)
    if shaped is not None and param in shaped:
        from ._shapes import expected
        return ProofResult(
            "proven",
            sketch=f"rejection by construction: the enforce_dimensions "
                   f"wrapper checks {param}'s shape ({expected(shaped[param])}) "
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
    language_bound = getattr(bounds, "base_type", None) == "L"
    if language_bound:
        # a language's own near non-members, each named for the language
        # it lies outside; a language admitting every value of its kind
        # has no outside to draw, which is a skip with the reason
        names, candidates = _outside_language(bounds, rng)
        if not candidates:
            return ("skipped", 0,
                    f"L[{names}] has no outside this route can draw: "
                    f"every value of its kind is a member")
    else:
        candidates = [c for c in _out_of_domain_candidates(bounds)
                      if not is_missing(c)]   # missing spellings are
        # is_missing_safe's own hazard, not this member's
    from . import _shapes
    # a space domain (`R^(30,15)`, `[0, 1]^30`) has an outside of its
    # own: a value of another shape, its elements inside the domain
    space_dims = _shapes.dims_of(bounds) if not language_bound else ()
    if not candidates and not space_dims:
        return None
    element_bound = bounds
    if space_dims:
        import dataclasses
        element_bound = dataclasses.replace(bounds, dims=())
    sequence_target = ((facts.param_kinds.get(target) in SEQUENCE_KINDS
                        or bool(space_dims)) and not language_bound)
    # the function receives each value as its own runtime type
    from .runtime_types import calling
    call = calling(fn, facts)
    state = {"idx": 0}
    # every shape just outside the space, each tried in turn: a fixed
    # axis one up and one down, one rank up, one rank down
    outsides = _shapes.outside_shapes(bounds) if space_dims else []
    cycle = len(candidates) + len(outsides)

    def trial(args):
        slot = state["idx"] % cycle
        state["idx"] += 1
        if slot >= len(candidates):
            shape = outsides[slot - len(candidates)]
            value = _shapes.build_shape(
                shape, lambda: _synth("float", rng, element_bound))
            spelled = (f"{target} of shape {_shapes.shape_text(shape)} is "
                       f"outside the declared domain "
                       f"{_shapes.space_text(bounds)}")
        elif language_bound:
            bad = candidates[slot]
            value = bad
            spelled = (f"{target} = {_witness_value(bad)} "
                       f"(outside L[{names}]{_why_outside(bad, bounds)})")
        elif sequence_target:
            # a sequence parameter is violated one ELEMENT at a time:
            # a fresh in-domain sequence with one out-of-domain entry,
            # of the shape the space fixes when it fixes one
            bad = candidates[slot]
            if space_dims:
                seq = _shapes.shaped(
                    bounds, rng, lambda: _synth("float", rng, element_bound))
                leaf = seq
                while leaf and isinstance(leaf[0], list):
                    leaf = leaf[0]
                leaf[rng.randrange(len(leaf))] = bad
            else:
                seq = [rng.uniform(-10, 10) for _ in range(4)]
                seq[rng.randrange(len(seq))] = bad
            value = seq
            spelled = f"{target}[...] = {bad!r}"
        else:
            bad = candidates[slot]
            value = bad
            spelled = f"{target} = {bad!r}"
        try:
            out = _call_with_target(call, facts, target, args, value)
        except Exception:
            return True   # rejected, as the claim demands
        if spelled.endswith(_shapes.space_text(bounds)):
            # the shape round's sentence already says where the value lies
            from .probing import _fmt_value
            return (f"{spelled} but was accepted (returned {_fmt_value(out)}); "
                    f"the exclusion is asserted, not enforced")
        return (f"{spelled} is outside the declared domain but was "
                f"accepted (returned {out!r}); the exclusion is "
                f"asserted, not enforced")

    rounds = max(cycle, min(trials, cycle * 4))
    return _probe_trials(fn, facts, target, domain, rng, rounds, trial)


def _language_pieces(bounds) -> list:
    """Intent:
        `[(name, language)]` for every language piece of a language
        bound, resolved through the registry.
    """
    from .domain import LanguageRef
    from .languages import resolve_language
    return [(piece.text, resolve_language(piece)) for piece in bounds.pieces
            if isinstance(piece, LanguageRef)]


def _language_names(bounds) -> str:
    return " | ".join(name for name, _ in _language_pieces(bounds))


def _outside_language(bounds, rng: random.Random) -> "tuple[str, list]":
    """Intent:
        `(names, values)`: up to eight distinct near non-members per
        language piece, each checked against the WHOLE bound (a value
        outside one language of a union may lie inside another), and
        the joined language names for the witness. Missing values are
        `is_missing_safe`'s hazard and are left out.
    """
    from .domain import domain_contains, is_missing
    pieces = _language_pieces(bounds)
    out: list = []
    for _, language in pieces:
        for _ in range(8):
            value = language.outside(rng)
            if value is None or is_missing(value):
                continue
            if domain_contains(value, bounds):
                continue
            if not any(value == seen for seen in out):
                out.append(value)
    return " | ".join(name for name, _ in pieces), out


def _witness_value(value) -> str:
    """A witness value as a counterexample shows it: a string by its
    repr, anything else as the probe formats it, so a record with only a
    default repr shows its fields."""
    if isinstance(value, str):
        return repr(value)
    from .probing import _fmt_value
    return _fmt_value(value)


def _why_outside(value, bounds) -> str:
    """Intent:
        Why `value` is not a member, as the witness states it: the first
        problem the bound's first language explains, ` at <path>: <why>`,
        or `: <why>` for the value as a whole; empty when no language
        explains it.
    """
    for _, language in _language_pieces(bounds):
        try:
            problems = language.explain(value) or []
        except Exception:
            continue
        if problems:
            first = problems[0]
            where = f" at {first.path}" if first.path else ""
            return f"{where}: {first.predicate}"
    return ""


def _language_corpus(bounds, rng: random.Random) -> "tuple[str, list]":
    """Intent:
        The fuzz corpus for a parameter bound to a language:
        `(label, [(value, side)])` with the language's own hazards and
        four draws, each on the side of the claim's domain it falls (a
        value the claim excludes is outside), then its near non-members
        outside, so a crash is reported for the side it happened on;
        `label` names the domain as the claim writes it.
    """
    from .domain import domain_contains, is_missing, render_domain
    names, outsides = _outside_language(bounds, rng)
    drawn: list = []
    for _, language in _language_pieces(bounds):
        drawn.extend(h.value for h in language.hazards())
        drawn.extend(language.sample(rng) for _ in range(4))
    if any(not is_missing(v) for v in getattr(bounds, "excluded", ()) or ()):
        # a value the claim excludes is outside its domain, and the label
        # is the domain as written, exclusion included
        label = render_domain(bounds, show_missing=False, ascii_mode=True)
    else:
        label = f"L[{names}]"
    sides = [(v, "inside" if domain_contains(v, bounds) else "outside") for v in drawn]
    return label, sides + [(v, "outside") for v in outsides]


def _shrink_in_language(value, still_fails, bounds):
    """Intent:
        A smaller witness that `still_fails`, tried first through each
        language's own `shrink` candidates (which stay members) and
        then through the generic deletion shrinker; `still_fails`
        carries the side condition, so the witness never crosses the
        language boundary.
    """
    from ._shrink import shrink
    best = value
    changed = True
    while changed:
        changed = False
        for _, language in _language_pieces(bounds):
            for candidate in language.shrink(best):
                if len(str(candidate)) < len(str(best)) and still_fails(candidate):
                    best, changed = candidate, True
                    break
            if changed:
                break
    return shrink(best, still_fails)


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
        COMPUTATION's claim. Deterministic implies reproducible
        (the weaker, up-to-a-seed member below). rhs_src/relation/
        tolerance kept for protocol uniformity.
    """
    from ._process_state import hidden_reads
    from .symbolic import ProofResult, lift
    if hidden_reads(fn, facts):
        # a read of the clock, the environment or a file is an input
        # the lift does not see
        return None
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


def _same_float(a: float, b: float) -> bool:
    """Two floats agree exactly, the sign of zero included; a NaN agrees
    with a NaN whatever its payload."""
    if a != a and b != b:
        return True
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


def _same_kind(first, second) -> "bool | None":
    """Whether two outcomes of the same call agree by kind: floats
    exactly (the sign of zero counts, a NaN agrees with a NaN), element
    by element inside a list, tuple or dict, arrays by their entries the
    same way, and the same exception type (an outcome that raised is its
    exception's type). None when the comparison cannot tell: an object
    with no equality of its own (two equal ones are two identities) or
    an iterator (comparing it would consume it)."""
    import collections.abc
    first_raised = isinstance(first, type) and issubclass(first, BaseException)
    second_raised = isinstance(second, type) and issubclass(second, BaseException)
    if first_raised or second_raised:
        return first is second
    if isinstance(first, float) and isinstance(second, float):
        return _same_float(first, second)
    if (isinstance(first, (list, tuple)) and isinstance(second, (list, tuple))
            and type(first) is type(second)):
        if len(first) != len(second):
            return False
        verdicts = [_same_kind(a, b) for a, b in zip(first, second)]
        if False in verdicts:
            return False
        return None if None in verdicts else True
    if isinstance(first, dict) and isinstance(second, dict):
        if first.keys() != second.keys():
            return False
        return _same_kind([first[k] for k in first], [second[k] for k in first])
    try:
        import numpy
        if isinstance(first, numpy.ndarray) and isinstance(second, numpy.ndarray):
            if first.shape != second.shape or first.dtype != second.dtype:
                return False
            if first.dtype.kind in "fc":
                return bool(numpy.array_equal(first, second, equal_nan=True)
                            and numpy.array_equal(numpy.signbit(first.real),
                                                  numpy.signbit(second.real)))
            return bool(numpy.array_equal(first, second))
    except ImportError:
        pass
    if isinstance(first, collections.abc.Iterator) \
            or isinstance(second, collections.abc.Iterator):
        return None
    if type(first) is type(second) and type(first).__eq__ is object.__eq__:
        return None
    return _same_result(first, second)


def _outcome_text(outcome) -> str:
    if isinstance(outcome, type) and issubclass(outcome, BaseException):
        return f"raised {outcome.__name__}"
    return f"returned {outcome!r}"


def _deterministic_probe(fn, facts, cj, domain: dict, rng: random.Random,
                         trials: int):
    """Empirical half of is_deterministic: two calls at the same inputs
    (each given its own copy of the arguments) compared by kind
    (`_same_kind`). Divergence falsifies with both outcomes as witness;
    agreement across trials holds. A body that reads the clock, the
    environment or a file (`_process_state.hidden_reads`) holds with a
    note naming the read, since two back-to-back calls cannot see it
    change."""
    import copy

    from ._process_state import hidden_reads
    if not facts.params:
        return None
    target = facts.params[0]

    def outcome(call_args):
        try:
            with _pinned_float_env():
                return fn(*call_args)
        except Exception as exc:
            return type(exc)

    def trial(args):
        call_args = list(args)
        call_args[facts.params.index(target)] = _synth(
            facts.param_kinds.get(target, "unknown"), rng, domain.get(target))
        placed = _placed(dict(zip(facts.params, call_args)), rng)
        if placed is None:
            return None
        call_args = [placed[p] for p in facts.params]
        try:
            second_args = copy.deepcopy(call_args)
        except Exception:
            return None
        first, second = outcome(call_args), outcome(second_args)
        agree = _same_kind(first, second)
        if agree is None:
            # the comparison cannot tell; not a trial
            uncomparable.append(type(first).__name__)
            return None
        if agree:
            return True
        shown = ", ".join(f"{p} = {_witness_value(v)}"
                          for p, v in zip(facts.params, second_args))
        returned = [not (isinstance(o, type) and issubclass(o, BaseException))
                    for o in (first, second)]
        if all(returned):
            return f"at {shown}, two calls returned {first!r} and {second!r}"
        return (f"at {shown}, the first call {_outcome_text(first)} and the "
                f"second {_outcome_text(second)}")

    uncomparable: list = []
    result = _probe_trials(fn, facts, target, domain, rng, trials, trial)
    if result[0] == "skipped" and uncomparable:
        return ("skipped", 0,
                f"two calls return {uncomparable[0]} values, which have "
                f"no equality of their own or are consumed by comparing "
                f"them, so paired calls cannot tell whether they agree")
    reads = hidden_reads(fn, facts)
    if result[0] == "holds" and reads:
        return (*result, None, {"mathema.caveat": (
            f"the body reads {', '.join(reads)}, which does not change "
            f"between two back-to-back calls, so this holds only while it "
            f"stays as it is")})
    return result


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


#: parameter names read as a seed or a random generator
_SEED_NAMES = frozenset({"seed", "rng", "random_state", "key"})


def _seed_annotation_kind(annotation) -> "str | None":
    """Intent:
        Which generator type a parameter annotation names:
        `"generator"` (numpy's `Generator`), `"random_state"` (numpy's
        `RandomState`), `"random"` (`random.Random`), or None. A string
        annotation is read by its last dotted name.
    """
    if annotation is None:
        return None
    text = annotation if isinstance(annotation, str) else (
        f"{getattr(annotation, '__module__', '')}."
        f"{getattr(annotation, '__qualname__', repr(annotation))}")
    last = text.strip("'\" ").rsplit(".", 1)[-1]
    if last == "Generator" and ("numpy" in text or "np." in text
                                or text.strip("'\" ") == "Generator"):
        return "generator"
    if last == "RandomState":
        return "random_state"
    if last == "Random" and ("random" in text.lower()):
        return "random"
    return None


def seed_parameter(fn, facts) -> "str | None":
    """Intent:
        The parameter that seeds `fn`'s randomness: one named `seed`,
        `rng`, `random_state` or `key`, or one annotated as a numpy
        `Generator` or `RandomState` or a `random.Random`; the first
        such parameter, or None when the function takes none.
    """
    import inspect
    try:
        signature = callable_signature(fn)
    except (TypeError, ValueError):
        signature = None
    for p in facts.params:
        if p in _SEED_NAMES:
            return p
        if signature is not None and p in signature.parameters:
            annotation = signature.parameters[p].annotation
            if annotation is not inspect.Parameter.empty \
                    and _seed_annotation_kind(annotation) is not None:
                return p
    return None


def _seed_factory(fn, param: str):
    """Intent:
        A function from an integer seed to the value `param` is passed:
        a fresh numpy `Generator`, `RandomState` or `random.Random`
        seeded with it when the annotation names one, else the integer
        itself.
    """
    import inspect
    try:
        annotation = callable_signature(fn).parameters[param].annotation
    except (TypeError, ValueError, KeyError):
        annotation = None
    kind = (None if annotation is inspect.Parameter.empty
            else _seed_annotation_kind(annotation))
    if kind == "generator":
        import numpy
        return numpy.random.default_rng
    if kind == "random_state":
        import numpy
        return numpy.random.RandomState
    if kind == "random":
        return random.Random
    return lambda s: s


def _same_result(first, second) -> bool:
    """Whether two results of the same call agree: equal values, equal
    arrays, or NaN in the same places."""
    try:
        import numpy
        if isinstance(first, numpy.ndarray) or isinstance(second,
                                                          numpy.ndarray):
            return bool(numpy.array_equal(numpy.asarray(first),
                                          numpy.asarray(second),
                                          equal_nan=True))
    except ImportError:
        pass
    try:
        if first == second:
            return True
    except Exception:
        return False
    return (isinstance(first, float) and isinstance(second, float)
            and first != first and second != second)


def _reproducible_probe(fn, facts, cj, domain: dict, rng: random.Random,
                        trials: int):
    """Empirical half of is_reproducible: two calls at the same inputs
    with the same seed must return the same value. When the function
    takes a seed or a generator (`seed_parameter`), the seed is held
    fixed across the pair (a fresh generator of the annotated type,
    built from the same integer seed, for each call) and every other
    argument is drawn once and passed to both. Otherwise the recognized
    global RNG state (the stdlib `random` global state, and numpy's
    legacy global state when numpy is importable) is captured and
    restored between the two calls. Divergence falsifies with the pair
    as witness; a raising point says nothing about seeds and is not
    counted. Agreement across trials holds (specific seeds were tested,
    not all)."""
    if not facts.params:
        return None
    seed = seed_parameter(fn, facts)
    target = seed if seed is not None else facts.params[0]
    build = _seed_factory(fn, seed) if seed is not None else None

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
        index = facts.params.index(target)
        if build is not None:
            fixed = rng.randint(0, 2 ** 31 - 1)
            call_args[index] = build(fixed)
        else:
            call_args[index] = _synth(
                facts.param_kinds.get(target, "unknown"), rng,
                domain.get(target))
        placed = _placed(dict(zip(facts.params, call_args)), rng,
                         keep=(target,) if build is not None else ())
        if placed is None:
            return None
        call_args = [placed[p] for p in facts.params]
        captured = [(setter, getter()) for _, getter, setter in rng_states()]
        try:
            with _pinned_float_env():
                first = fn(*call_args)
        except Exception:
            return None   # a raising point says nothing about seeds
        for setter, state in captured:
            setter(state)
        if build is not None:
            call_args[index] = build(fixed)
        try:
            with _pinned_float_env():
                second = fn(*call_args)
        except Exception as exc:
            return (f"same inputs, same seed: the first call returned "
                    f"{first!r} but the second raised "
                    f"{type(exc).__name__}")
        if not _same_result(first, second):
            if build is not None:
                return (f"same inputs, the same {seed} ({fixed}), "
                        f"different results: {first!r} then {second!r}, "
                        f"the computation is not reproducible from its "
                        f"seed")
            return (f"same inputs, same restored RNG state, different "
                    f"results: {first!r} then {second!r}, the "
                    f"computation is not reproducible up to its seed")
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
    if facts.param_kinds.get(param) not in SEQUENCE_KINDS:
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
    if facts.param_kinds.get(target) not in SEQUENCE_KINDS:
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
    from .domain import domain_contains

    target = cj.lhs
    bound = domain.get(target)
    language_bound = getattr(bound, "base_type", None) == "L"
    if facts.param_kinds.get(target) != "string" and not language_bound:
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

    if language_bound:
        # the declared language's own hazards and members, then its
        # near non-members: a crash is reported for the side it happened
        # on, and the witness shrinks without crossing the boundary
        names, corpus = _language_corpus(bound, rng)
    else:
        names = ""
        corpus = [(v, None) for v in
                  list(_STRING_SPECIALS) + [_synth_string(rng) for _ in range(8)]]
    state = {"i": 0}

    def trial(args):
        if state["i"] >= len(corpus):
            return True
        value, side = corpus[state["i"]]
        state["i"] += 1
        exc = crash_on(args, value)
        if exc is None:
            return True
        if side is None:
            minimal = shrink(value, lambda s: crash_on(args, s) is not None)
            return (f"{target} = {minimal!r} raised {exc} on arbitrary input, "
                    f"an unguarded crash, not a declared rejection")
        inside = side == "inside"

        def still_fails(s):
            return (crash_on(args, s) is not None
                    and bool(domain_contains(s, bound)) == inside)

        minimal = _shrink_in_language(value, still_fails, bound)
        return (f"{target} = {_witness_value(minimal)} ({side} {names}) raised {exc} on "
                f"arbitrary input, an unguarded crash, not a declared "
                f"rejection")

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
    if facts.param_kinds.get(target) in SEQUENCE_KINDS:
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
        raising checks; when the domain includes missing (the default)
        but a raising guard names a spelling, the function is called
        with that spelling: disproven with the executed raise as the
        witness, else the uncorroborated undecided; undecided (None)
        otherwise, a guard covering only
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
        sketch = (f"the declared domain admits a missing {param} (missing "
                  "is included by default; no \\ {∅} exclusion is stated) "
                  "but the body has a raising guard for it")
        spellings = [(label, value) for key, label, value in
                     (("nan", "nan", float("nan")), ("none", "None", None))
                     if key in coverage]
        executed = 0
        for label, value in spellings:
            what, calls = _executed_family_witness(fn, facts, param, value,
                                                   domain)
            executed += calls
            if what is not None:
                return ProofResult(
                    "disproven", sketch=sketch,
                    counterexample=f"{param} = {label} {what}",
                    meta={"mathema.corroboration": "reproduced",
                          "mathema.witness_executed": True})
        return _uncorroborated_family_disproof(
            sketch, f"no call with a missing {param} raised ({executed} "
                    f"call(s) made)")
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


def _guarded_safety_derive(derive, outside_domain: bool = False):
    """Wrap a safety member's derive half in the family verdict
    contract: a disproof must carry a concrete counterexample (a
    safety falsification without a witness is not evidence), and the
    status vocabulary is closed. A violation raises; it is a family
    implementation bug, never a claim outcome.

    The claim's premises (`assumption`) reach the derive half as a
    narrower domain (`_premises.narrowed_domain`): each conjunct that
    bounds one scalar parameter by a number narrows that parameter's
    interval, so a proof covers the premise region and a disproof's
    witness lies inside it. When some conjunct cannot be folded in, a
    proof over the wider domain still covers the premise region, but a
    disproof's witness may lie outside it, so the disproof becomes
    undecided and the probe route decides over admitted points. A
    member whose trials set its own parameter outside the domain
    (`outside_domain`) keeps that parameter's declared bound."""
    def run(fn, facts, lhs_src, rhs_src, relation, domain=None,
            tolerance=None, assumption=None):
        complete = True
        if assumption:
            from ._premises import narrowed_domain
            keep = frozenset({lhs_src.strip()}) if outside_domain \
                else frozenset()
            domain, complete = narrowed_domain(
                domain or {}, assumption, facts.param_kinds, keep=keep)
        proof = derive(fn, facts, lhs_src, rhs_src, relation,
                       domain=domain, tolerance=tolerance)
        if proof is None:
            return None
        if proof.status == "disproven" and not complete:
            from .symbolic import ProofResult
            return ProofResult(
                "undecided",
                sketch=f"{proof.sketch}; the witness "
                       f"({proof.counterexample}) is not known to satisfy "
                       f"the claim's premises, so a falsification is left "
                       f"to execution at admitted points")
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


def split_probe_result(result) -> tuple:
    """Intent:
        A family probe's result as `(verdict, checked, cx, established,
        meta)`. The accepted forms are `(verdict, checked, cx)` and
        `(verdict, checked, cx, established)`, either one optionally
        followed by a mapping merged into the record's `meta`; a missing
        sketch or mapping comes back as `None`.
    Raises:
        ValueError: the result has neither three nor four elements
        before the optional mapping.
    """
    from collections.abc import Mapping
    items = tuple(result)
    meta = None
    if len(items) in (4, 5) and isinstance(items[-1], Mapping):
        meta, items = dict(items[-1]), items[:-1]
    if len(items) == 3:
        verdict, checked, cx = items
        established = None
    elif len(items) == 4:
        verdict, checked, cx, established = items
    else:
        raise ValueError(f"a family probe returned {len(tuple(result))} "
                         f"elements; expected (verdict, checked, cx), "
                         f"optionally with an established sketch, then "
                         f"optionally a meta mapping")
    return verdict, checked, cx, established, meta


def _guarded_safety_probe(probe):
    """Wrap a safety member's empirical half in the family verdict
    contract. Trials may falsify (with a witness), hold, decline, or
    report `unknown` (the member examined the function and could not
    settle it, a roll-up with an unsettled child); they may claim
    "proven" ONLY by returning the 4-tuple form (verdict, checked, cx,
    established) with a non-empty `established` sketch naming why the
    coverage was EXHAUSTIVE, the hazard class fully enumerated and
    every case observed. The verdict carries surety, so an established
    empirical examination proves; anything short of exhaustive
    coverage holds at best. A trailing meta mapping (see `split_probe_result`)
    passes through untouched. A contract violation raises, same
    as the derive guard."""
    def run(fn, facts, cj, domain, rng, trials):
        result = probe(fn, facts, cj, domain, rng, trials)
        if result is None:
            return None
        verdict, checked, cx, established, meta = split_probe_result(result)
        if verdict == "proven" and not established:
            raise ValueError("safety trials claimed proven without an "
                             "established-coverage sketch, sampling "
                             "alone never proves; only an exhaustive "
                             "examination (stated as such) does")
        if verdict not in ("proven", "falsified", "holds", "skipped",
                           "unknown"):
            raise ValueError(f"safety probe returned verdict {verdict!r}, "
                             f"outside the closed vocabulary")
        if verdict == "falsified" and not cx:
            raise ValueError("safety probe falsified without a concrete "
                             "counterexample, a safety falsification "
                             "must carry its witness")
        if meta is None:
            return (verdict, checked, cx, established)
        return (verdict, checked, cx, established, meta)
    return run


#: the safety families whose trials set their own parameter outside the
#: domain on purpose (a missing value, the empty sequence, a value past
#: the domain's edge, a string off the corpus): the premises hold every
#: other parameter, never the target itself
_OUTSIDE_DOMAIN_FAMILIES = frozenset({
    "is_missing_safe", "is_empty_safe", "excluded_outside_domain",
    "is_arbitrary_input_safe"})


class SafetyFamily(_NamedClaimFamily):
    """One computation-safety member: a claim family whose evidence
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
                 probe_route="probe:algorithmic",
                 whole_function: bool = False,
                 reserved: "str | None" = None):
        family_routes = {"derive": _guarded_safety_derive(
            derive, outside_domain=base_name in _OUTSIDE_DOMAIN_FAMILIES)}
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
        # a member that examines the whole function at once: its `(f)`
        # spelling is adjudicated as one claim, not expanded into the
        # conjunction over every numeric parameter
        self.whole_function = whole_function
        # a member defined but not adjudicated in this release: both
        # halves report `skipped` with this reason, so a claim naming it
        # is a known claim that is not yet decided, never a misspelling
        self.reserved = reserved

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
        signature = callable_signature(fn)
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
        Returns a ProofResult whenever the function has Python source:
        an is_defined claim must not fall through to the ordinary
        relation prover, whose reading (is the relation TRUE?) is a
        different question from region equivalence. A structural
        disproof no executed point reproduces comes back undecided with
        the corroboration flags (`_witnessed_disproof`). With no source
        (`facts.tree is None`) there is no body to compute a region
        from, and it declines (None); the probe half
        (`_is_defined_probe`) adjudicates by execution.
    """
    if facts.tree is None:
        return None
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
                # which conjunct of how many matched: an unindexed row
                # (which names the whole region) is proven by it only
                # when there is one, and a chained row's links must
                # cover them all
                return ProofResult(
                    "proven",
                    sketch=f"is_defined: the stated region matches the "
                           f"computed definedness region of the current "
                           f"body{part}, full region: {region_text}",
                    meta={"mathema.derive_route": "definedness_equivalence",
                          "mathema.definedness_conjunct":
                              [k + 1, len(computed_rels)]})
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


def _has_value(out, exc) -> bool:
    """Whether an executed call had a value: it returned, and the
    result is finite. A raise, a nan and an infinity are no value."""
    return exc is None and not _is_nonfinite(out)


def _no_overflow(out, exc) -> bool:
    """Whether an executed call stayed inside float range: it neither
    raised an OverflowError (or a FloatingPointError reporting an
    overflow) nor returned an infinity. A nan, a finite value and any
    other raise are not an overflow."""
    from .probing import holds_inf
    if exc is not None:
        return not (isinstance(exc, OverflowError)
                    or (isinstance(exc, FloatingPointError)
                        and "overflow" in str(exc).lower()))
    return not holds_inf(out)


#: the two region families (`conjecture.REGION_ROW_STRATA`): what an
#: executed call must do inside the stated region
_REGION_SAFE = {"is_defined": _has_value, "is_overflow_safe": _no_overflow}

#: the words the record uses for each outcome of a region family
_REGION_WORDS: dict = {
    "is_defined": {
        "bare": "so it is not defined on the whole domain",
        "outside": "a value outside the stated region",
        "sampled_bare": "{checked} executed points in the domain, each "
                        "returning a finite value",
        "sampled_conjunct": "{n_out} executed points outside the stated "
                            "conjunct returned no value and {n_in} were "
                            "sampled inside it, where the region's other "
                            "conjuncts decide",
        "sampled": "{n_in} executed points inside the stated region "
                   "returned a finite value and {n_out} outside it "
                   "returned no value",
    },
    "is_overflow_safe": {
        "bare": "so it is not overflow-safe on the whole domain",
        "outside": "no overflow outside the stated region",
        "sampled_bare": "{checked} executed points in the domain, none "
                        "overflowing",
        "sampled_conjunct": "{n_out} executed points outside the stated "
                            "conjunct overflowed and {n_in} were sampled "
                            "inside it, where the region's other conjuncts "
                            "decide",
        "sampled": "{n_in} executed points inside the stated region "
                   "returned without overflow and {n_out} outside it "
                   "overflowed",
    },
}


def _region_interval(region, symbol):
    """Intent:
        The real interval a one-parameter region describes, as
        `(lo, hi, closed_lo, closed_hi)` with infinite ends where the
        region is unbounded, or None when the region is not one
        interval in that symbol (another variable, a union, an
        unsolvable relation). Each conjunct is solved on its own under
        the fast wall-clock cap and the results intersected.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    parts = list(region.args) if isinstance(region, sympy.And) else [region]
    hull = sympy.S.Reals
    for part in parts:
        if not isinstance(part, sympy.core.relational.Relational):
            return None
        if part.free_symbols != {symbol}:
            return None
        try:
            solved = _with_timeout(
                lambda: sympy.solveset(part, symbol, sympy.S.Reals),
                FAST_TIMEOUT_SECONDS)
        except Exception:
            return None
        hull = hull.intersect(solved)
    if not isinstance(hull, sympy.Interval):
        return None
    try:
        return (float(hull.inf), float(hull.sup),
                not hull.left_open, not hull.right_open)
    except (TypeError, ValueError):
        return None


def _squashed_link(link) -> tuple:
    """A `(lhs, relation, rhs)` link with the whitespace removed from
    each side, so two spellings of one link compare equal."""
    return tuple("".join(str(part or "").split()) for part in link)


def _overflow_safe_rows(fn, cj) -> "tuple[list, list, str]":
    """Intent:
        The recorded `is_overflow_safe` region of the function a claim
        is about, as `(links, texts, owner)`: its `(lhs, relation, rhs)`
        links, the texts the record quotes, and the name the note
        gives the function. Read from a library key's compendium rows
        and from the project's own `is_overflow_safe` claims adjudicated
        beside this one (`Conjecture.overflow_safe`); empty lists when
        neither records one.
    """
    from .compendium import computation_region, library_key_of
    from .conjecture import claim
    key = library_key_of(fn)
    links: list = []
    texts: list = []
    if key is not None:
        for row in computation_region(key, "is_overflow_safe"):
            for text in row["texts"]:
                try:
                    parsed = claim(text, name="is_overflow_safe")
                except Exception:
                    continue
                links.extend(parsed.links
                             or [(parsed.lhs, parsed.relation, parsed.rhs)])
                texts.append(text)
    # a link the compendium row and a sibling claim both state (the
    # row adjudicated beside this claim) is kept once
    seen = {_squashed_link(link) for link in links}
    for link in getattr(cj, "overflow_safe", ()) or ():
        if _squashed_link(link) in seen:
            continue
        seen.add(_squashed_link(link))
        links.append(link)
        lhs, rel, rhs = link
        texts.append(f"{lhs} {rel} {rhs}")
    owner = key if key is not None else str(getattr(fn, "__name__", "f"))
    return links, texts, owner


def _is_defined_reach(fn, cj, params: list, domain: dict, shapes: dict,
                      links: list, texts: list, owner: str):
    """Intent:
        How far an `is_defined` probe runs each scalar parameter, for any
        function: inside its recorded `is_overflow_safe` region (`links`,
        see `_overflow_safe_rows`) when one is recorded, since where the
        computation overflows is that claim's fact and not this one's;
        else to the claim's pseudo-infinity, else to the number
        representation's maximum; each intersected with the parameter's
        own declared bound. Returns `(reach, note)`: the per-parameter
        `(lo, hi)` the corners are taken from and outside which a draw
        is not a trial, and the text the record carries.
    """
    import math as _math

    import sympy

    from ._sampling import representation_reach
    from .compendium import _relation
    from .records import operational_range
    pinf = operational_range(cj)
    reach_max = representation_reach()
    default_lo, default_hi = (pinf if pinf is not None
                              else (-reach_max, reach_max))
    env = {p: sympy.Symbol(p, real=True) for p in params}
    regions: dict = {}
    for lhs, rel, rhs in links:
        try:
            region = _relation(lhs, rel, rhs, env)
        except Exception:
            continue
        for p in params:
            found = _region_interval(region, env[p])
            if found is None:
                continue
            lo, hi, c_lo, c_hi = regions.get(
                p, (-_math.inf, _math.inf, True, True))
            if found[0] > lo or (found[0] == lo and not found[2]):
                lo, c_lo = found[0], found[2]
            if found[1] < hi or (found[1] == hi and not found[3]):
                hi, c_hi = found[1], found[3]
            regions[p] = (lo, hi, c_lo, c_hi)
    reach: dict = {}
    for p in params:
        if shapes.get(p) is not None:
            continue
        ends = _interval_ends((domain or {}).get(p))
        lo, hi = ends if ends is not None else (-_math.inf, _math.inf)
        r_lo, r_hi, closed_lo, closed_hi = regions.get(
            p, (-_math.inf, _math.inf, True, True))
        lo, hi = max(lo, r_lo), min(hi, r_hi)
        if not closed_lo and lo == r_lo:
            lo = _math.nextafter(lo, _math.inf)
        if not closed_hi and hi == r_hi:
            hi = _math.nextafter(hi, -_math.inf)
        if _math.isinf(lo):
            lo = default_lo
        if _math.isinf(hi):
            hi = default_hi
        if lo <= hi:
            reach[p] = (lo, hi)
    if texts:
        note = (f"sampled inside the overflow-safe region of {owner} "
                f"({' and '.join(texts)})")
    elif pinf is not None:
        from .records import operational_infinity
        note = f"unbounded directions run to {operational_infinity(cj).render()}"
    else:
        note = (f"unbounded directions run to magnitude "
                f"{representation_reach():g}")
    return reach, note


def _compiled_links(links: list, params: list) -> list:
    """Intent:
        `(lhs, relation, rhs)` links compiled for evaluation at a point
        over `params`; [] when a link is not a comparison or reads a
        name outside `params`.
    """
    from .conjecture import _validate
    out: list = []
    for lhs, rel, rhs in links:
        if rel not in _COMPARISONS or not rhs:
            return []
        try:
            out.append((_validate(lhs, set(params), frozenset())[0], rel,
                        _validate(rhs, set(params), frozenset())[0]))
        except Exception:
            return []
    return out


def _region_probe(fn, facts, cj, domain: dict, rng: random.Random,
                  trials: int, kind: str):
    """Intent:
        The empirical half shared by the two region families
        (`_REGION_SAFE`): `is_defined`, where a call inside the region
        must have a value (a finite return) and a call outside must
        not, and `is_overflow_safe`, where a call inside must not
        overflow and a call outside must. The bare claim (`is_defined(f)`,
        `is_overflow_safe(x)`) asks the inside condition at every
        sampled point of the domain. A stated region asks it at every
        sampled point inside and the outside condition at every
        sampled point outside. An indexed row (`is_defined[2]`) states
        one conjunct of the region, so it asks only the outside
        condition: inside, the other conjuncts decide. The first point
        that disagrees is the executed witness.

    Notes:
        Points come from the domain's corners, then points around the
        region's boundary (each link solved for one parameter under the
        fast wall-clock cap, the root offset a little each way), then
        seeded draws from the domain. The bare `is_overflow_safe` also
        tries the representation extremes the domain admits (the float
        corner, the exp threshold, the denormal band, or the claim's
        pseudo-infinity), since overflow lives there. An `is_defined`
        probe takes its corners from `_is_defined_reach` and treats a
        draw outside that reach, or outside the function's recorded
        `is_overflow_safe` region, as no trial. A point with
        a missing argument, or outside the domain, is not a trial.
        Returns the `(verdict, checked, counterexample, established,
        meta)` shape, with the counts inside and outside the region in
        `meta`, or None when a link is not a comparison.
    """
    import math as _math

    from .conjecture import _SAFE_FUNCS, MATH_CONSTANTS, _validate, call_defaults
    from .domain import domain_contains, is_missing
    from .gates import _fmt_point
    from .probing import _fmt_value
    words = _REGION_WORDS[kind]
    safe = _REGION_SAFE[kind]

    # a library function's defaulted parameters the claim leaves alone
    # are not passed (they take their defaults); a pinned one is
    # passed at its pin
    kept, call_pins, _problem = call_defaults(fn, cj)
    params = [p for p in facts.params if p not in kept]
    if not params:
        return None
    bare = cj.relation == kind
    # an indexed row names one conjunct by number (`is_defined[2]`,
    # pinned `is_defined[2]@axis=1`); a row pinned to a call's
    # arguments (`is_defined@axis=1`) states the whole region
    import re as _re
    conjunct = not bare and bool(_re.search(
        r"\[\d+\]$", str(cj.name).split("@", 1)[0]))
    links = [] if bare else (list(cj.links)
                             or [(cj.lhs, cj.relation, cj.rhs)])
    compiled = []
    for lhs, rel, rhs in links:
        if rel not in _COMPARISONS or not rhs:
            return None
        try:
            code_l, _aux = _validate(lhs, set(params), frozenset())
            code_r, _aux = _validate(rhs, set(params), frozenset())
        except Exception:
            return None
        compiled.append((code_l, rel, code_r))
    # the claim's own premise: a point outside it is not a trial. The
    # running claim's premise guard decides when there is one; a claim
    # adjudicated without one (a pinned definedness premise) reads its
    # comparisons here
    from . import _premises
    from .conjecture import _parse_assuming_links, _split_top_and
    guard = _premises.current()
    premise = "" if guard is not None else (cj.assuming or "").strip()
    if premise.startswith("assuming"):
        premise = premise[len("assuming"):].strip()
    assumed = []
    for part in (_split_top_and(premise) if premise else ()):
        premise_links = _parse_assuming_links(part)
        if premise_links is None:
            return None
        for rel_parts in premise_links:
            if rel_parts.relation not in _COMPARISONS:
                return None
            try:
                assumed.append((
                    _validate(rel_parts.lhs, set(params), frozenset())[0],
                    rel_parts.relation,
                    _validate(rel_parts.rhs, set(params), frozenset())[0]))
            except Exception:
                return None
    compare = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
               "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
               ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}

    def satisfies(relations: list, point: dict) -> "bool | None":
        env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **point}
        try:
            return all(bool(compare[rel](eval(cl, {"__builtins__": {}}, env),
                                         eval(cr, {"__builtins__": {}}, env)))
                       for cl, rel, cr in relations)
        except Exception:
            return None

    def inside(point: dict) -> "bool | None":
        return satisfies(compiled, point)

    shapes = _region_shapes(links, params, domain)
    reach, reach_note = ({}, None)
    overflow_safe: list = []
    overflow_texts: list = []
    if kind == "is_defined":
        links_o, overflow_texts, owner = _overflow_safe_rows(fn, cj)
        reach, reach_note = _is_defined_reach(fn, cj, params, domain,
                                              shapes, links_o,
                                              overflow_texts, owner)
        overflow_safe = _compiled_links(links_o, params)

    def admitted(point: dict) -> bool:
        if overflow_safe and satisfies(overflow_safe, point) is False:
            return False
        for p, v in point.items():
            if is_missing(v):
                return False
            if kind == "is_overflow_safe" and isinstance(v, float) \
                    and _math.isinf(v):
                # overflow is an infinity from finite inputs; an
                # infinite input is not a trial
                return False
            bound = (domain or {}).get(p)
            span = reach.get(p)
            if span is not None and isinstance(v, (int, float)) \
                    and not span[0] <= v <= span[1]:
                return False
            if bound is None:
                continue
            dims = getattr(bound, "dims", None)
            if dims:
                # a space binding (`R^n`, `R^(n,n)`): a non-empty array
                # with that many axes
                if not _has_axes(v, len(dims)):
                    return False
                continue
            try:
                if not domain_contains(v, bound):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def draw_one(p: str):
        from .matrices import _rand
        if p in call_pins:
            return call_pins[p]
        if shapes.get(p) == "matrix":
            return _rand(rng.randint(2, 5), rng)
        if shapes.get(p) == "sequence":
            return [rng.uniform(-10.0, 10.0)
                    for _ in range(rng.randint(1, 6))]
        return _synth(facts.param_kinds.get(p, "unknown"), rng,
                      (domain or {}).get(p))

    def draw() -> dict:
        point = {p: draw_one(p) for p in params}
        placed = _placed(point, rng, keep=tuple(call_pins))
        return point if placed is None else placed

    def shape_boundaries():
        # the edge of a shape region: a singular matrix sits on
        # `det(a) != 0`'s boundary, the empty sequence below `dim(a) >= 1`
        from .matrices import _synth_singular
        for p, shape in sorted(shapes.items()):
            for _ in range(3):
                yield {**draw(), p: (_synth_singular(rng.randint(2, 5), rng)
                                     if shape == "matrix" else [])}

    def corners():
        from .probing import _bound_is_complex
        from .representations import PY_COMPLEX128
        for p in params:
            if p in call_pins:
                continue
            if _bound_is_complex((domain or {}).get(p)):
                # the plane's far points on both axes, at the reach
                span = reach.get(p)
                r = (max(abs(span[0]), abs(span[1])) if span is not None
                     else float(PY_COMPLEX128.max_magnitude or 0.0))
                for v in (complex(-r, 0.0), complex(r, 0.0),
                          complex(0.0, -r), complex(0.0, r)):
                    yield {**draw(), p: v}
                continue
            ends = reach.get(p) or _interval_ends((domain or {}).get(p))
            if ends is None:
                continue
            lo, hi = ends
            for v in (lo, hi, (lo + hi) / 2):
                yield {**draw(), p: v}

    def extremes():
        # the bare overflow claim: the representation extremes each
        # scalar parameter's bound admits, where overflow lives
        from .hazards import _extreme_candidates
        from .records import operational_range
        pinf = operational_range(cj)
        for p in params:
            if p in call_pins or shapes.get(p) is not None \
                    or facts.param_kinds.get(p) in (*SEQUENCE_KINDS, "string"):
                continue
            for v in _extreme_candidates((domain or {}).get(p),
                                         pseudo_infinity=pinf):
                yield {**draw(), p: v}

    def near_boundaries():
        import sympy as _sympy

        from ._timeout import FAST_TIMEOUT_SECONDS as _FAST
        from ._timeout import _with_timeout as _capped
        from .grammar import _node_to_sympy
        import ast as _ast
        for lhs, _rel, rhs in links:
            try:
                gap = (_node_to_sympy(_ast.parse(lhs, mode="eval").body)
                       - _node_to_sympy(_ast.parse(rhs, mode="eval").body))
            except Exception:
                continue
            by_name = {str(sym): sym for sym in gap.free_symbols}
            for p in params:
                if p not in by_name:
                    continue
                base = draw()
                held = gap.subs({by_name[q]: base[q] for q in params
                                 if q != p and q in by_name
                                 and isinstance(base[q], (int, float))})
                try:
                    roots = _capped(lambda: _sympy.solve(held, by_name[p]),
                                    _FAST)
                except TimeoutError:
                    return
                except Exception:
                    continue
                for root in roots:
                    if root.free_symbols or not root.is_real:
                        continue
                    for off in _WITNESS_OFFSETS + (1e-6, -1e-6, 10.0, -10.0):
                        yield {**base, p: float(root) + off}

    def candidates():
        yield from corners()
        if bare and kind == "is_overflow_safe":
            yield from extremes()
        if not bare:
            yield from shape_boundaries()
            yield from near_boundaries()
        for _ in range(trials):
            yield draw()

    checked = n_in = n_out = 0
    seen: set = set()
    for point in candidates():
        key = tuple(repr(point[p]) for p in params)
        if key in seen or not admitted(point) \
                or (assumed and not satisfies(assumed, point)) \
                or (guard is not None and not guard.admits_point(point)):
            continue
        seen.add(key)
        where = True if bare else inside(point)
        if where is None:
            continue
        try:
            call_args, call_kwargs = call_arguments(fn, params, point)
            with _pinned_float_env():
                out = fn(*call_args, **call_kwargs)
        except _premises.PremiseRejected:
            continue
        except Exception as exc:
            out, raised = None, exc
            what = f"raised {type(exc).__name__}"
        else:
            raised = None
            what = f"returned {_fmt_value(out)}"
        checked += 1
        n_in, n_out = n_in + bool(where), n_out + (not where)
        if safe(out, raised) == where or (conjunct and where):
            continue
        at = _fmt_point(point, params)
        if bare:
            cx = f"{at}: f {what}, {words['bare']}"
        elif where:
            cx = f"{at}: inside the stated region, f {what}"
        else:
            cx = f"{at}: f {what}, {words['outside']}"
        found = {"mathema.witness_executed": True}
        if kind == "is_defined" and not overflow_texts \
                and not _no_overflow(out, raised):
            # the missing value is an overflow of the computation
            found["mathema.sampled"] = (
                "the computation overflows there; state the region where "
                "it stays in float range as an is_overflow_safe claim "
                "and is_defined is sampled inside it")
        return ("falsified", checked, cx, None, found)
    if checked == 0:
        return "skipped", 0, None
    sampled = (words["sampled_bare"] if bare else
               words["sampled_conjunct"] if conjunct else
               words["sampled"]).format(checked=checked, n_in=n_in,
                                        n_out=n_out)
    if reach_note:
        sampled = f"{sampled}; {reach_note}"
    return "holds", checked, None, None, {"mathema.sampled": sampled}


def _is_defined_probe(fn, facts, cj, domain: dict, rng: random.Random,
                      trials: int):
    """Empirical half of `is_defined`, for any target whose region
    equivalence (the derive half) declines or does not decide: the
    `_region_probe` with "has a value" (a finite return) as the inside
    condition."""
    return _region_probe(fn, facts, cj, domain, rng, trials, "is_defined")


def _has_axes(value, axes: int) -> bool:
    """Whether `value` is a non-empty nested list or tuple (or array)
    `axes` levels deep, with real numbers at the bottom."""
    if axes == 0:
        return (isinstance(value, (int, float))
                and not isinstance(value, bool)) or (
            hasattr(value, "dtype") and getattr(value, "shape", None) == ())
    if hasattr(value, "tolist") and hasattr(value, "shape"):
        value = value.tolist()
    return (isinstance(value, (list, tuple)) and len(value) >= 1
            and all(_has_axes(v, axes - 1) for v in value))


def _region_shapes(links: list, params: list, domain: dict) -> dict:
    """Intent:
        The parameters an `is_defined` region reads as arrays, mapped to
        `"matrix"` or `"sequence"`: a parameter bound over `R^(n,n)` or
        read through `det(...)` is a square matrix, one bound over `R^n`
        or read through `dim(...)` is a sequence.
    """
    import re
    out: dict = {}
    text = " ".join(f"{lhs} {rhs}" for lhs, _rel, rhs in links)
    for p in params:
        dims = getattr((domain or {}).get(p), "dims", None) or ()
        if len(dims) == 2 or re.search(rf"\bdet\s*\(\s*{p}\s*\)", text):
            out[p] = "matrix"
        elif len(dims) == 1 or re.search(rf"\bdim\s*\(\s*{p}\b", text):
            out[p] = "sequence"
    return out


def _matrix_property(name: str):
    from .matrices import PROPERTIES
    return PROPERTIES.get(name)


def _synth_matrix(n: int, rng: random.Random) -> list:
    return [[rng.uniform(-5, 5) for _ in range(n)] for _ in range(n)]


def _non_finite_matrix(n: int, rng: random.Random) -> list:
    """A random n-by-n matrix with one entry a NaN or an infinity."""
    m = _synth_matrix(n, rng)
    m[rng.randrange(n)][rng.randrange(n)] = rng.choice(
        (float("nan"), float("inf"), float("-inf")))
    return m


def _violating_matrix(prop, n: int, rng: random.Random,
                      tries: int = 20) -> "list | None":
    """A random n-by-n matrix that does NOT have `prop`, for the guard
    check; None when none turned up (a property almost every random
    matrix satisfies, so the guard question is not meaningful). A
    finiteness guard is tried against a matrix holding a NaN or an
    infinity."""
    if prop.name == "is_finite":
        return _non_finite_matrix(n, rng)
    for _ in range(tries):
        m = _synth_matrix(n, rng)
        if prop.check(m) is False:
            return m
    return None


def _premise_structures(cj) -> dict:
    """The structure premises of a claim's `assuming` clause,
    `{param: (prop, ...)}` entailment-closed (`assuming A is
    symmetric` gives `{"A": ("is_symmetric",)}`)."""
    import re

    from .conjecture import _split_top_and
    from .grammar import parse_domain_safety
    from .matrices import PROPERTIES, entailed
    text = re.sub(r"^\s*assuming\s+", "", (cj.assuming or "").strip())
    found: dict = {}
    for part in _split_top_and(text) if text else ():
        parsed = parse_domain_safety(part.strip())
        if (parsed is not None and not parsed[0].startswith("not ")
                and parsed[0] in PROPERTIES and parsed[1].isidentifier()):
            found.setdefault(parsed[1], set()).add(parsed[0])
    return {p: tuple(sorted(entailed(props))) for p, props in found.items()}


def _structured_draws(fn, facts, cj, domain: dict):
    """Intent:
        A per-trial drawer of every parameter for a matrix property
        claim: a matrix sized by its `Shape` marker or `R^(m,n)` domain
        (shared dimension names share one size, a fixed size stays
        fixed) and synthesised with its structure markers and
        structure premises; a vector sized the same way; a number
        from its domain. A parameter with no shape and no domain is a
        square matrix of a random size, as before any shape was known.
    """
    from . import dimensions
    from .matrices import synth_for
    from .types import shapes_from_signature, structures_from_signature
    shapes = shapes_from_signature(fn)
    structures = dict(structures_from_signature(fn))
    for p, props in _premise_structures(cj).items():
        structures[p] = tuple(sorted(set(structures.get(p, ())) | set(props)))
    try:
        resolver = dimensions.resolve(facts, shapes, claim_domain=domain)
    except dimensions.DimensionConflict:
        resolver = dimensions.resolve(facts, shapes)

    from .matrices import rank_edge
    drawn = [0]

    def draw(rng: random.Random) -> list:
        drawn[0] += 1
        sizes = resolver.draw_sizes(rng, hi={k: 5 for k in
                                             resolver.distinct_keys()})
        out = []
        for p in facts.params:
            shape = resolver.shapes.get(p)
            declared = p in shapes or getattr((domain or {}).get(p),
                                              "dims", ())
            ndim = shape.ndim if shape is not None and declared else 0
            props = structures.get(p, ())
            kind = facts.param_kinds.get(p, "scalar")
            if ndim == 2 or (ndim == 0 and (props or kind in SEQUENCE_KINDS)):
                if ndim == 2:
                    rows = sizes.get(resolver.key(p, 0)) or 3
                    cols = sizes.get(resolver.key(p, 1)) or 3
                else:
                    rows = cols = rng.randint(1, 5)
                if props and rows == cols:
                    out.append(synth_for(props, rows, rng))
                else:
                    out.append(rank_edge(
                        [[rng.uniform(-5, 5) for _ in range(cols)]
                         for _ in range(rows)], drawn[0] - 1))
            elif ndim == 1:
                n = sizes.get(resolver.key(p, 0)) or 3
                bound = (domain or {}).get(p)
                if getattr(bound, "pieces", None):
                    # a declared element bound (`[a, b]^n`) holds every
                    # element of the draw
                    out.append([_synth("float", rng, bound)
                                for _ in range(n)])
                else:
                    out.append([rng.uniform(-5, 5) for _ in range(n)])
            else:
                out.append(_synth("float", rng, (domain or {}).get(p)))
        return out
    return draw


def _matrix_output_probe(prop):
    """The output/expression check: per trial synthesize every
    parameter (with its shape, structure markers and structure
    premises) and place it on the claim's equality premises, keep
    only points inside every premise, evaluate the predicate's
    argument expression (which calls `f` and may combine matrices) in
    the claim namespace every probe shares, and test the resulting
    value for the property. A raise from `f` at such a point is no
    value and falsifies, the exception named; a raise from the
    expression around it is a broken sample. Holds when every
    evaluable value has the property, falsifies with the witnessing
    arguments when one does not, skips when the property could not be
    decided on any value (a spectral check with no numpy, or no point
    inside the premises)."""
    def probe(fn, facts, cj, domain, rng, trials):
        import ast as _ast

        from .domain import is_missing
        from ._premises import PremiseRejected
        try:
            code = compile(_ast.parse(cj.lhs, mode="eval"), "<claim>", "eval")
        except SyntaxError:
            return None
        draw = _structured_draws(fn, facts, cj, domain)
        checked = 0
        for _ in range(trials):
            point = _placed(dict(zip(facts.params, draw(rng))), rng)
            if point is None or not _admitted(point):
                continue
            filled = [point[p] for p in facts.params]
            raised: list = []
            try:
                value = _eval_matrix_expr(code, point, fn, raised=raised)
            except PremiseRejected:
                continue
            except Exception:
                if raised and not any(is_missing(v) for v in filled):
                    checked += 1
                    return ("falsified", checked,
                            f"{_fmt(tuple(filled))}: f raised "
                            f"{type(raised[0]).__name__}, no value", None)
                continue
            got = prop.check(value)
            if got is None:
                continue
            checked += 1
            if got is not True:
                return ("falsified", checked,
                        f"{_fmt(tuple(filled))}: result is not "
                        f"{prop.name[3:]}", None)
        if checked == 0:
            return ("skipped", 0, None, None)
        return ("holds", checked, None, None)
    return probe


def _matrix_guard_probe(prop):
    """The precondition/guard check for a bare-parameter predicate
    (`is_symmetric(A)`): does the function REJECT an argument that
    lacks the property, the value-analogue of excluded_outside_domain.
    Holds when a synthesized violating input raises or returns None;
    falsifies with that input when the function silently accepts it."""
    def probe(fn, facts, cj, domain, rng, trials):
        from ._premises import PremiseRejected
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
            except PremiseRejected:
                checked -= 1  # outside the claim's premises, not a trial
                continue
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


def _eval_matrix_expr(code, env: dict, fn, raised: "list | None" = None):
    """Evaluate a claim expression (compiled) over drawn values in the
    one namespace every probe of a claim shares
    (`_linalg_eval.FUNCTIONS`): vectors and matrices are numpy arrays,
    `f(...)` calls the real function with its own runtime types, and
    the value comes back as plain lists, the form the matrix property
    checks read. Each exception `f` itself raises is appended to
    `raised` when given."""
    from . import _linalg_eval as lae
    call = lae.law_callable(fn)
    if raised is not None:
        inner = call

        def call(*args, **kwargs):
            try:
                return inner(*args, **kwargs)
            except Exception as exc:
                raised.append(exc)
                raise
    names = {"f": call, **lae.FUNCTIONS,
             **{k: lae.as_array(v) for k, v in env.items()}}
    with _pinned_float_env():
        value = eval(code, {"__builtins__": {}}, names)
    return lae.to_plain(value)


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
    argument by its kind (on the claim's equality premises), call f, and
    test the returned value with `check` (True has the property, False
    does not with a witness, None undecided this round). A raise at a
    point without a missing argument is no output and falsifies."""
    def probe(fn, facts, cj, domain, rng, trials):
        from .domain import is_missing

        def trial(_args):
            point = _placed({p: _synth(facts.param_kinds.get(p, "scalar"),
                                       rng, (domain or {}).get(p))
                             for p in facts.params}, rng)
            if point is None:
                return None
            filled = [point[p] for p in facts.params]
            try:
                with _pinned_float_env():
                    out = fn(*filled)
            except Exception as exc:
                if any(is_missing(v) for v in filled):
                    return None
                return (f"{_fmt(tuple(filled))}: f raised "
                        f"{type(exc).__name__}, no output")
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


def _is_compendium_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                               relation: str, domain: dict | None = None,
                               tolerance: float | None = None):
    """Structural half of is_compendium_safe: decline. Whether a covered
    library call ever reaches its nan region over the declared domain is
    established empirically by the probe (which samples the domain and
    the boundary specials), not proved symbolically here."""
    return None


def _raised_by_library(exc: BaseException, library: str) -> bool:
    """Intent:
        Whether an exception is the library failing rather than the
        caller refusing an input: a floating-point error, or a raise
        whose traceback passes through a file of the library's own
        package.
    """
    import importlib
    import os
    if isinstance(exc, FloatingPointError):
        return True
    try:
        pkg = os.path.dirname(os.path.realpath(
            importlib.import_module(library).__file__ or ""))
    except Exception:
        return False
    if not pkg:
        return False
    tb = exc.__traceback__
    while tb is not None:
        path = os.path.realpath(tb.tb_frame.f_code.co_filename)
        if path.startswith(pkg + os.sep):
            return True
        tb = tb.tb_next
    return False


def _compendium_probe(fn, facts, cj, domain: dict, rng, trials: int):
    """Empirical half of is_compendium_safe(<library>): sample the
    function's inputs (respecting a declared domain, and hitting the
    negative / out-of-unit boundary specials that trigger a covered
    library's nan regions), call f, and check the output is FINITE. A
    silent nan/inf produced through an unguarded call into a covered
    library function (numpy.sqrt on a negative, numpy.arcsin past 1),
    or a raise from inside the library itself (`_raised_by_library`), is
    the counterexample; a finite result on every trial holds, and a
    raise of the caller's own (a guard) is not the library failing.
    Declines when f does not call a covered function of the named
    library."""
    from .compendium import libraries_called
    library = cj.lhs.strip()
    if library not in libraries_called(fn, facts):
        return None

    # empty-sequence trials up front: an empty reduction (numpy.mean of
    # []) returns nan silently, and the random sampler draws 2..8-element
    # sequences, never the empty boundary. One empty trial per sequence
    # parameter catches it.
    empties = [p for p in facts.params
               if facts.param_kinds.get(p) in SEQUENCE_KINDS]

    def _sample(force_empty=None):
        point = {p: ([] if p == force_empty
                     else _synth(facts.param_kinds.get(p, "scalar"), rng,
                                 (domain or {}).get(p)))
                 for p in facts.params}
        placed = _placed(point, rng, keep=(force_empty,))
        return [(placed or point)[p] for p in facts.params]

    def diagnosed(cx: str, filled: list) -> str:
        # the covered call's computation region, when the compendium
        # states one (numpy.exp is overflow-safe only for x <= 709.78)
        from .compendium import computation_diagnosis
        region = computation_diagnosis(fn, facts,
                                       dict(zip(facts.params, filled)))
        return f"{cx}; {region}" if region else cx

    def trial(_args):
        filled = _sample(empties.pop() if empties else None)
        try:
            with _pinned_float_env():
                out = fn(*filled)
        except Exception as e:
            if _raised_by_library(e, library):
                return diagnosed(f"{_fmt(tuple(filled))}: raised "
                                 f"{type(e).__name__} inside {library}",
                                 filled)
            return None
        if _is_nonfinite(out):
            return diagnosed(f"{_fmt(tuple(filled))}: output {out!r} is a "
                             f"silent non-finite value from an unguarded "
                             f"{library} call", filled)
        return True

    target = facts.params[0] if facts.params else ""
    return _probe_trials(fn, facts, target, domain, rng,
                         max(trials, len(facts.params) + 4), trial)


# --- the computation-safety hierarchy (P13): is_computation_safe(f) rolls
# up its children for one implementation; each child is adjudicated by
# execution, and a child's restriction form states the region where the
# computation is safe in that respect. -------------------------------


def _is_overflow_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                             relation: str, domain: dict | None = None,
                             tolerance: float | None = None):
    """Structural half of is_overflow_safe: decline. Whether a
    computation overflows is a fact about one number representation,
    established by executing it (P3, P13); a derive proof over the
    reals says nothing about it."""
    return None


def _overflow_probe(fn, facts, cj, domain: dict, rng: random.Random,
                    trials: int):
    """Empirical half of is_overflow_safe: the `_region_probe` with
    "does not overflow" (no infinity returned, no OverflowError) as
    the inside condition. The bare claim also tries the representation
    extremes the domain admits, where overflow lives."""
    return _region_probe(fn, facts, cj, domain, rng, trials,
                         "is_overflow_safe")


def _is_recursion_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                              relation: str, domain: dict | None = None,
                              tolerance: float | None = None):
    """Structural half of is_recursion_safe: decline. The recursion
    limit is the runtime's, reached or not by executing the call."""
    return None


def _recursion_probe(fn, facts, cj, domain: dict, rng: random.Random,
                     trials: int):
    """Empirical half of is_recursion_safe: call fn at the corners of
    the declared domain (the far end of each numeric parameter first,
    where a recursion driven by it runs deepest) and at sampled points;
    a RecursionError at an admitted point is the counterexample. Any
    other raise is not the recursion limit and passes; so does a
    normal return. `is_recursion_safe(n)` focuses the corners on `n`,
    `is_recursion_safe(f)` takes every numeric parameter's."""
    from .gates import _fmt_point
    target = cj.lhs
    numeric = [p for p in facts.params
               if facts.param_kinds.get(p) not in (*SEQUENCE_KINDS, "string")]
    if target in facts.params:
        focus = [target]
    elif target == "f" and numeric:
        focus = numeric
    else:
        return None
    anchor = focus[0]
    corners: list = []
    for p in focus:
        ends = _interval_ends((domain or {}).get(p))
        if ends is not None:
            lo, hi = ends
            corners.extend((p, v) for v in (hi, lo, (lo + hi) / 2))
    state = {"i": 0}

    def trial(args):
        values = dict(zip(facts.params, args))
        values[anchor] = _synth(facts.param_kinds.get(anchor, "unknown"),
                                rng, (domain or {}).get(anchor))
        corner = None
        if state["i"] < len(corners):
            corner, v = corners[state["i"]]
            state["i"] += 1
            values[corner] = v
        values = _placed(values, rng, keep=(corner,))
        if values is None:
            return None
        try:
            call_args, call_kwargs = call_arguments(fn, facts.params, values)
            with _pinned_float_env():
                fn(*call_args, **call_kwargs)
        except RecursionError:
            return (f"{_fmt_point(values, list(facts.params))}: f raised "
                    f"RecursionError, the recursion limit is reached "
                    f"inside the declared domain")
        except Exception:
            return True
        return True

    verdict, checked, cx = _probe_trials(fn, facts, anchor, domain, rng,
                                         max(trials, len(corners)), trial)
    if verdict != "holds":
        return verdict, checked, cx
    return ("holds", checked, None, None,
            {"mathema.sampled": f"{checked} executed points, none reaching "
                                f"the recursion limit"})


#: computation-safety families named now and adjudicated in a later
#: release, with the question each answers
RESERVED_FAMILIES = {
    "is_precision_safe": "right in a narrower number representation",
    "is_order_invariant": "the same answer whatever the reduction order",
    "is_concurrency_safe": "runs correctly under concurrent calls",
    "is_representation_consistent": "the same answer across the "
                                    "computations the descriptor names",
}


def _reserved_note(name: str) -> str:
    """Why a reserved family reports skipped."""
    return (f"{name} ({RESERVED_FAMILIES[name]}) is reserved for a later "
            f"release and not adjudicated in this one")


def _reserved_derive(fn, facts, lhs_src: str, rhs_src: str,
                     relation: str, domain: dict | None = None,
                     tolerance: float | None = None):
    """Structural half of a reserved family: decline."""
    return None


def _reserved_probe(name: str):
    """The empirical half of a reserved family: skipped, with the
    reason, so a claim naming it is a known claim, not a
    misspelling."""
    def probe(fn, facts, cj, domain: dict, rng: random.Random,
              trials: int):
        return "skipped", 0, _reserved_note(name)
    return probe


#: the children of is_computation_safe, in the order the roll-up runs
#: and reports them: the families that answer "does it run on my
#: domain" and "is the answer right in float64". Each is relevant to a
#: function when its own suggestion gate names a target there, except
#: numerical stability, which always runs. Repeatability is
#: is_repeatable's question.
_COMPUTATION_CHILDREN = (
    "is_overflow_safe", "is_numerically_stable", "is_representation_safe",
    "is_extremity_safe", "is_pole_safe", "is_builtin_safe",
    "is_missing_safe", "is_empty_safe", "is_recursion_safe",
    "is_arbitrary_input_safe", "is_compendium_safe")
_ALWAYS_RELEVANT_CHILDREN = frozenset({"is_numerically_stable"})


def _is_computation_safe_derive(fn, facts, lhs_src: str, rhs_src: str,
                                relation: str, domain: dict | None = None,
                                tolerance: float | None = None):
    """Structural half of is_computation_safe: decline. The roll-up is
    the conjunction of executed facts and holds at best (P3)."""
    return None


def _computation_children(fn, facts, cj, domain: dict) -> list:
    """The child claims is_computation_safe runs for this function:
    numerical stability in its own spelling, and every other child at
    each target its suggestion gate names, all over the roll-up's
    domain and pseudo-infinity."""
    from . import families as _families
    from .conjecture import claim
    registry = _families.families()
    out: list = []
    for name in _COMPUTATION_CHILDREN:
        family = registry.get(name)
        if family is None:
            continue
        if name == "is_numerically_stable":
            out.append(claim(f"g(f, {', '.join(facts.params)}) == 1",
                             name=name, route="best",
                             funcs={"g": "mathema.f.finite_no_error"}))
        else:
            for target in family.suggest_targets(fn, facts):
                out.append(claim(f"{name}({target})",
                                 name=f"{name}[{target}]", route="best"))
    return _over_parent(out, cj, domain)


def _over_parent(children: list, cj, domain: dict) -> list:
    """A roll-up's child claims over the roll-up's own domain, premise
    and pseudo-infinity."""
    from dataclasses import replace as _replace
    return [_replace(c, domain=dict(domain or {}),
                     assuming=getattr(cj, "assuming", "") or "",
                     pseudo_infinity=getattr(cj, "pseudo_infinity", None),
                     resolved_pseudo_infinity=getattr(
                         cj, "resolved_pseudo_infinity", None))
            for c in children]


def _computation_probe(fn, facts, cj, domain: dict, rng: random.Random,
                       trials: int):
    """Empirical half of is_computation_safe(f): the roll-up
    (`_roll_up`) of every relevant child (`_computation_children`)."""
    from ._premises import unguarded
    fn = unguarded(fn)
    return _roll_up(fn, facts, _computation_children(fn, facts, cj, domain),
                    trials)


def _repeatable_children(fn, facts, cj, domain: dict) -> list:
    """The child claims is_repeatable runs for this function, over the
    roll-up's domain: `is_reproducible` (same seed, same answer) when
    the function takes a seed or a generator (`seed_parameter`), else
    `is_deterministic` (same input, same answer), and `is_state_safe`
    always."""
    from .conjecture import claim
    call = f"f({', '.join(facts.params)})"
    first = ("is_reproducible" if seed_parameter(fn, facts) is not None
             else "is_deterministic")
    out = [claim(f"{call} == {call}", name=name, route="best")
           for name in (first, "is_state_safe")]
    return _over_parent(out, cj, domain)


def _is_repeatable_derive(fn, facts, lhs_src: str, rhs_src: str,
                          relation: str, domain: dict | None = None,
                          tolerance: float | None = None):
    """Structural half of is_repeatable: decline. The roll-up is the
    conjunction of its children's verdicts and holds at best."""
    return None


def _repeatable_probe(fn, facts, cj, domain: dict, rng: random.Random,
                      trials: int):
    """Empirical half of is_repeatable(f): the roll-up (`_roll_up`) of
    `_repeatable_children`."""
    from ._premises import unguarded
    fn = unguarded(fn)
    return _roll_up(fn, facts, _repeatable_children(fn, facts, cj, domain),
                    trials)


def _roll_up(fn, facts, children: list, trials: int):
    """Intent:
        Adjudicate a roll-up's child claims in one nested
        `check_conjectures` call and roll the verdicts up. Any child
        falsified falsifies the roll-up with that child's name and
        witness; every child holding or proven makes it hold, never
        proven (P3, a roll-up of executed facts about one
        implementation); anything else is unknown. The note lists each
        child's verdict and `meta["mathema.children"]` carries them as
        a mapping. None when there are no children.
    """
    from ._premises import unguarded
    from .conjecture import check_conjectures
    if not children:
        return None
    probes = check_conjectures(unguarded(fn), children, facts=facts,
                               trials=trials)
    verdicts = {p.name: p.verdict for p in probes}
    checked = sum(p.n or 0 for p in probes)
    meta = {"mathema.children": verdicts,
            "mathema.sampled": ", ".join(f"{n}: {v}"
                                         for n, v in verdicts.items())}
    failed = [p for p in probes if p.verdict == "falsified"]
    if failed:
        first = failed[0]
        cause = (first.stratum or {}).get("cause")
        if cause:
            meta["mathema.cause"] = cause
        return ("falsified", checked,
                f"{first.name}: {first.counterexample}", None, meta)
    if all(v in ("holds", "proven") for v in verdicts.values()):
        return "holds", checked, None, None, meta
    return "unknown", checked, None, None, meta


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
    _defined = _NamedClaimFamily(
        "is_defined", {"derive": _is_defined_derive,
                       "probe:algorithmic": _is_defined_probe})
    # the bare `is_defined(f)` is one question about the whole function
    # (the derive half reads the body's raise regions, the probe half
    # samples every parameter jointly), so it is not expanded into a
    # conjunction over the parameters
    _defined.whole_function = True
    _families.register("is_defined", _defined)
    # the computation-safety members, one SafetyFamily each: the
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
    # is_overflow_safe: no infinity and no OverflowError from finite
    # inputs (P13); its restriction form states the region where the
    # computation stays in float range, the row a
    # compendium carries for numpy.exp. Suggested wherever a parameter
    # is raised to a power or reaches an overflow-prone function.
    from .hazards import _overflow_targets
    _families.register("is_overflow_safe", SafetyFamily(
        "is_overflow_safe", derive=_is_overflow_safe_derive,
        probe=_overflow_probe,
        suggest_targets=_overflow_targets))
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
    # is_recursion_safe: no RecursionError over the domain, suggested
    # when the body calls itself; `(f)` is one claim over the whole
    # function, not a conjunction over its parameters
    from .hazards import _recursion_targets
    _families.register("is_recursion_safe", SafetyFamily(
        "is_recursion_safe", derive=_is_recursion_safe_derive,
        probe=_recursion_probe,
        suggest_targets=_recursion_targets, whole_function=True))
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
    # predicate relations). is_deterministic is the STRONG one: its
    # empirical half is paired calls compared by kind. is_reproducible is
    # weaker (up to an RNG seed): its probe runs paired calls with
    # the recognized RNG states captured and restored.
    _families.register("is_deterministic", SafetyFamily(
        "is_deterministic", derive=_is_deterministic_derive,
        probe=_deterministic_probe))
    _families.register("is_reproducible", SafetyFamily(
        "is_reproducible", derive=_is_reproducible_derive,
        probe=_reproducible_probe))
    _families.register("is_state_safe", SafetyFamily(
        "is_state_safe", derive=_is_state_safe_derive,
        probe=_state_probe))
    # reserved: named now, adjudicated later, never suggested; a
    # platform (GPU, JIT, distributed) is named in the bracketed
    # computation descriptor, never in a family name
    for _rname in RESERVED_FAMILIES:
        _families.register(_rname, SafetyFamily(
            _rname, derive=_reserved_derive,
            probe=_reserved_probe(_rname), whole_function=True,
            reserved=_reserved_note(_rname)))
    _families.register("is_computation_safe", SafetyFamily(
        "is_computation_safe", derive=_is_computation_safe_derive,
        probe=_computation_probe, whole_function=True))
    # is_repeatable is the roll-up for "is it repeatable": the seed
    # decides whether its first child is is_reproducible or
    # is_deterministic, and is_state_safe always joins; declared by the
    # author, never battery-suggested
    _families.register("is_repeatable", SafetyFamily(
        "is_repeatable", derive=_is_repeatable_derive,
        probe=_repeatable_probe, whole_function=True))
