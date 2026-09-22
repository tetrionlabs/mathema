# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The soundness gates at the derive->Probe seam, beside the
corroboration engine they drive: `_corroboration_gate` (no derive
disproof survives unless an executed in-domain point reproduces it
against the real function; an unreproduced one downgrades to unknown
with the engine-bug flag), `_stability_gate` (a proven-exact claim
swept for float instability where the sweep is scoped to reach), and
`_point_evaluator`, the injected-dependency builder both gates (and
the corroboration engine) run on. Lived inside `conjecture.py` while
the gates were being built; a module of its own now, with
`conjecture` re-exporting the public knob
(`set_numerical_stability_check`) unchanged.

The gates consume `conjecture`'s claim plumbing (`_validate`,
`_SAFE_FUNCS`) through call-time imports: `conjecture` imports this
module at load, this module reaches back only when a gate actually
runs, so the import graph stays acyclic."""
from __future__ import annotations

from ._math_vocab import MATH_CONSTANTS
from .probing import _close
from .records import Probe


def _conjecture_bits():
    """The claim-plumbing names the evaluator needs from conjecture,
    resolved at call time (see the module docstring's cycle note)."""
    from .conjecture import InvalidConjecture, _SAFE_FUNCS, _validate
    return InvalidConjecture, _SAFE_FUNCS, _validate


_EXTREME = 1e10

# whether a proven derive claim is also swept for implementation
# numerical stability. Default OFF for now: sweeping the extreme
# corners of an unbounded domain falsifies proofs whose implementation
# is perfectly sound within any range a caller would actually use, so
# the sweep is opt-in until the extreme-value handling is refined (it
# is slated to become the default, see the roadmap). Turn it on to
# have derive attest the implementation reflects the maths, not only
# that the maths is correct.
_STABILITY_CHECK = [False]


def set_numerical_stability_check(enabled: bool) -> None:
    """Turn the proven-claim numerical-stability sweep on or off
    process-wide (default off for now, slated to default on). On =
    derive verdicts also attest the float implementation is stable
    across the declared domain, not only that the mathematics is
    correct."""
    _STABILITY_CHECK[0] = bool(enabled)


def _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum=(),
                     cap=None, scoped_extremes=False):
    """Intent:
        Build the injected dependencies the corroboration engine needs
        for THIS claim: `evaluate(point)` decides the original claim's
        relation at a concrete point by calling the real `fn` (True =
        holds, False = a genuine counterexample, None = can't tell);
        `probe_finite(point)` returns a numerical-instability detail (a
        raise, a NaN, or a deviation past a magnitude-scaled tolerance)
        or None; `admits(point)` is in-domain-and-assumption
        membership; `sample(name, rng)` draws a value respecting the
        parameter's declared bound (the probe route's own `_synth`);
        `corners` are the domain endpoints (infinity taken at `cap`'s
        resolved pseudo-infinity range, else +-`_EXTREME`); plus the
        free-variable `names`.

    Notes:
        `None` when the claim can't be numerically evaluated at all (a
        calculus form d/lim/integrate, or an uncompilable law), the
        caller then marks a disproof uncorroborated and skips a proof's
        sweep.
    """
    from .domain import bound_to_sympy_set, domain_contains
    from .probing import _synth
    InvalidConjecture, _SAFE_FUNCS, _validate = _conjecture_bits()
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    # the gates verify scalar-real VALUE claims by calling fn at a
    # point; a sequence parameter, a non-value relation, or a bundled
    # (dataclass/dict) parameter isn't reproducible this way; return
    # None so the caller leaves the derive verdict untouched
    if any(k == "sequence" for k in kinds.values()):
        return None
    if cj.relation not in ("==", "~=", "!=", "<=", ">=", "<", ">"):
        return None
    extra = frozenset(bound_funcs)
    try:
        code_l, aux_l = _validate(cj.lhs, set(kinds), extra)
        code_r, aux_r = _validate(cj.rhs, set(kinds), extra) if cj.rhs else (None, set())
    except InvalidConjecture:
        return None
    names = list(kinds) + sorted((aux_l | aux_r) - MATH_CONSTANTS.keys())
    slack = cj.tolerance if cj.tolerance is not None else 1e-9
    # raises from the function under test (or a bound function) are
    # tagged so the evaluators below can tell a genuine in-domain raise,
    # which IS a failure of a value claim, per the pedantic raise
    # rule, from a raise in the law's own plumbing, which proves
    # nothing about the claim
    calls_raised = [False]

    def _tag(callee):
        def _wrapped(*a, **kw):
            try:
                return callee(*a, **kw)
            except Exception:
                calls_raised[0] = True
                raise
        return _wrapped

    base_env = {"f": _tag(fn), **_SAFE_FUNCS, **MATH_CONSTANTS,
                **{name: _tag(v) for name, v in bound_funcs.items()}}
    from .records import pseudo_infinity_range
    if cap is not None:
        cap_lo, cap_hi = pseudo_infinity_range(cap)
    elif scoped_extremes:
        # scoped mode with no operational infinity declared: the
        # unbounded direction contributes NO extreme point at all,
        # an unbounded coordinate draws like an ordinary sample
        # instead, and testing the extremes is is_extremity_safe's
        # own job (or `let |inf| be ...`'s, when bound)
        cap_lo = cap_hi = None
    else:
        cap_lo, cap_hi = -_EXTREME, _EXTREME

    def _values(point):
        env = {**base_env, **point}
        lv = eval(code_l, {"__builtins__": {}}, env)
        rv = eval(code_r, {"__builtins__": {}}, env) if code_r is not None else 0
        return lv, rv

    def _relation_holds(lv, rv, tol):
        # inf-aware: two sides that overflow to the SAME infinity are
        # equal (an identity like sinh(-x) == -sinh(x) still holds at
        # overflow, both -inf), not a spurious inequality from
        # abs(inf - inf) = NaN. Native comparison handles inf/-inf;
        # abs-difference is only for the finite case.
        rel = cj.relation
        both_finite = all(abs(v) != float("inf") for v in (lv, rv))
        if rel in ("==", "~="):
            return lv == rv or (both_finite and abs(lv - rv) <= tol)
        if rel == "!=":
            return not (lv == rv or (both_finite and abs(lv - rv) <= tol))
        if both_finite:
            # strict relations compare natively: equality within
            # tolerance must not count as strictly greater/less (the
            # probe loop applies the same rule)
            return (lv <= rv + tol if rel == "<=" else
                    lv >= rv - tol if rel == ">=" else
                    lv < rv if rel == "<" else
                    lv > rv if rel == ">" else None)
        # an infinity on one side: native comparison is exact
        return (lv <= rv if rel == "<=" else lv >= rv if rel == ">=" else
                lv < rv if rel == "<" else lv > rv if rel == ">" else None)

    def _real(v):
        # a plain real number the relation can compare, not a bool,
        # string, None, complex, list, tuple, or NaN (inf is allowed:
        # _relation_holds compares it natively)
        return (isinstance(v, (int, float)) and not isinstance(v, bool)
                and v == v)

    def evaluate(point):
        calls_raised[0] = False
        try:
            lv, rv = _values(point)
        except Exception:
            # a raise FROM THE FUNCTION at an in-domain point is a
            # genuine failure of a value claim (the pedantic raise
            # rule), so it reproduces a disproof; a plumbing raise
            # stays inconclusive
            return False if calls_raised[0] else None
        if _real(lv) and _real(rv):
            # a counterexample must be a FINITE genuine failure, not an
            # overflow artifact; an inf point stays inconclusive
            if abs(lv) == float("inf") or abs(rv) == float("inf"):
                return None
            return _relation_holds(lv, rv, slack)
        # non-numeric result: an EQUALITY relation still compares
        # exactly (None vs a real number is a genuine mismatch, so an
        # opaque disproof reproduces); a NaN stays inconclusive (the
        # missing-policy axis owns it), and ordering over non-orderable
        # values proves nothing
        if any(isinstance(v, float) and v != v for v in (lv, rv)):
            return None
        if cj.relation in ("==", "~="):
            try:
                return bool(lv == rv)
            except Exception:
                return None
        if cj.relation == "!=":
            try:
                return not (lv == rv)
            except Exception:
                return None
        return None

    def probe_finite(point):
        # genuine implementation instability only: a raise, a NaN, or a
        # deviation past a MAGNITUDE-SCALED tolerance (so a correct
        # large-magnitude identity is not flagged, only catastrophic
        # cancellation / a real break is). An inf that still satisfies
        # the relation is fine (float's finite range, not instability);
        # a non-numeric result is inconclusive, never a flag.
        calls_raised[0] = False
        try:
            lv, rv = _values(point)
        except Exception:
            # only a raise from the function under test is
            # implementation instability; the law's own plumbing
            # failing says nothing about the code
            return "the implementation raises here" if calls_raised[0] else None
        for v in (lv, rv):
            if isinstance(v, complex):
                return None
            if isinstance(v, float) and v != v:
                return "the implementation returns NaN here"
        if not (_real(lv) and _real(rv)):
            return None
        scaled = slack + 1e-7 * max(abs(lv), abs(rv), 1.0)
        holds = _relation_holds(lv, rv, scaled)
        return None if holds else "a catastrophic deviation past a scaled tolerance"

    def sample(name, rng):
        # an unbounded parameter samples within the pseudo-infinity
        # range (or the full-extreme default), so a declared range
        # bounds the sweep's own draws, not only the corners
        b = cj_domain.get(name)
        if b is None:
            b = (cap_lo, cap_hi)
        return _synth(kinds.get(name, "float"), rng, b)

    def admits(point):
        for n in names:
            bound = cj_domain.get(n)
            v = point.get(n)
            if bound is None or v is None:
                continue
            try:
                fv = float(v)
                fv = int(fv) if fv.is_integer() else fv
            except (TypeError, ValueError):
                continue
            if not domain_contains(fv, bound):
                return False
        for a_l, a_rel, a_r in assum:
            try:
                env = {**base_env, **point}
                al = eval(compile(a_l, "<a>", "eval"), {"__builtins__": {}}, env)
                ar = eval(compile(a_r, "<a>", "eval"), {"__builtins__": {}}, env)
            except Exception:
                return False
            ops = {"<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y,
                   "<": lambda x, y: x < y, ">": lambda x, y: x > y,
                   "==": lambda x, y: _close(x, y),
                   "!=": lambda x, y: not _close(x, y)}
            if not ops.get(a_rel, lambda x, y: True)(al, ar):
                return False
        return True

    def _extreme_fallback(which):
        # None in scoped mode with no operational infinity: the
        # caller substitutes an ordinary draw for the coordinate
        return cap_lo if which == "lo" else cap_hi

    def _endpoint(bound, which):
        if isinstance(bound, tuple):
            val = float(bound[0] if which == "lo" else bound[1])
            if abs(val) == float("inf"):
                return _extreme_fallback(which)
            return val
        try:
            sset = bound_to_sympy_set(bound)
            edge = sset.inf if which == "lo" else sset.sup
            val = float(edge)
            if val != val or abs(val) == float("inf"):
                return _extreme_fallback(which)
            return val
        except Exception:
            return _extreme_fallback(which)

    def _kindly(name, value):
        # an integer-kind parameter (an `int` annotation, a loop count)
        # must reach `fn` as an int; a corner endpoint is a float by
        # construction, and passing a float where the code does
        # `range(t)`/`x[i]` raises a TypeError that is a type mismatch,
        # not the numerical instability this sweep is looking for. The
        # interior `sample` already coerces via `_synth(kind, ...)`; the
        # corners are coerced here to match.
        if kinds.get(name) in ("int", "bool"):
            try:
                return int(round(value))
            except (TypeError, ValueError):
                return value
        return value

    if cap_lo is None:
        # scoped mode with no operational infinity: the sweep only
        # runs where every coordinate has a real extreme to visit (a
        # finite declared endpoint); an unbounded, uncapped direction
        # is is_extremity_safe's own job; there is no principled
        # "modest" stand-in for infinity, so the sweep declines
        # rather than inventing one
        for n in names:
            bound = cj_domain.get(n)
            if bound is None or _endpoint(bound, "lo") is None \
                    or _endpoint(bound, "hi") is None:
                return None

    lows = {n: _kindly(n, _endpoint(cj_domain.get(n), "lo"))
            if cj_domain.get(n) is not None else _kindly(n, cap_lo)
            for n in names}
    highs = {n: _kindly(n, _endpoint(cj_domain.get(n), "hi"))
             if cj_domain.get(n) is not None else _kindly(n, cap_hi)
             for n in names}
    corners = [lows, highs]

    # this dict is the point-runtime kit; `interfaces.runtime` states
    # its contract (and the narrower obligation of a foreign runner
    # whose callable stands in for fn) so the seam is testable
    return dict(evaluate=evaluate, probe_finite=probe_finite, admits=admits,
                sample=sample, corners=corners, names=names)


def _fmt_point(point, names):
    """A point rendered for a counterexample string, numeric coords
    as :.6g, discrete/string coords (a string domain member) as-is."""
    parts = []
    for n in names:
        if n not in point:
            continue
        v = point[n]
        parts.append(f"{n}={v:.6g}" if isinstance(v, (int, float))
                     and not isinstance(v, bool) else f"{n}={v!r}")
    return ", ".join(parts)


def _corroboration_gate(falsified, proof, cj, fn, facts, cj_domain,
                        bound_funcs, assum=()):
    """Intent:
        Only trust a derive `disproven` once a concrete in-domain
        counterexample reproduces the failure against the REAL
        function, seeded by the proof's own witness. Reproduced ->
        `falsified` (meta corroboration=reproduced; route
        probe:semi_analytical when the analytical seed guided it). Not
        reproduced -> verdict `unknown` with the uncorroborated flag:
        a symbolic disproof nothing reproduces means an engine bug
        somewhere (a corrupted residual, an off-surface search), so the
        record must neither assert the falsification nor hide that it
        was claimed.
    """
    from . import corroboration as C
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum)
    if deps is None:
        # not scalar-real-evaluable (a calculus form, a sequence, an
        # opaque return): the disproof can't be reproduced this way, so
        # leave the derive verdict untouched; this gate only ever
        # REDUCES confidence in a scalar sign disproof it could check
        # and couldn't reproduce
        return falsified
    result = C.corroborate_disproof(deps["evaluate"], deps["names"],
                                    sample=deps["sample"], admits=deps["admits"],
                                    witness=proof.witness)
    if result.point is not None:
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        pt = _fmt_point(result.point, deps["names"])
        falsified.counterexample = pt or falsified.counterexample
        if falsified.stratum is None:
            # a symbolic disproof plus a reproduced executed witness is
            # the evidence bar for indicting the mathematics itself
            falsified.stratum = {"mathematics": "unsound",
                                 "blame": "claim", "witness": pt}
        if result.seeded and \
                proof.meta.get("mathema.derive_route") != "brute_force":
            # a seeded reproduction means the analytical witness guided
            # an empirical search, so the route names that. The one
            # mechanism this is wrong for is the exhaustive sweep: its
            # witness is not a seed, it is an executed call to the real
            # function at a point the domain admits, so the gate has
            # nothing to add and relabelling it would report weaker
            # evidence than was actually obtained.
            falsified.route = "probe:semi_analytical"
        return falsified
    falsified.verdict = "unknown"
    falsified.meta = {**(falsified.meta or {}),
                      "mathema.corroboration": "uncorroborated"}
    falsified.counterexample = None
    falsified.note = (
        f"{falsified.note}; uncorroborated disproof: the derive route "
        f"reported this false but no in-domain counterexample reproduced "
        f"against the function ({result.checked} points checked), a "
        f"symbolic disproof nothing reproduces indicates an engine bug "
        f"worth reporting, so the verdict stays unknown")
    return falsified


def _stability_gate(proven, cj, fn, facts, cj_domain, bound_funcs, assum=()):
    """Intent:
        A derive proof is exact in real arithmetic; derive also attests
        the IMPLEMENTATION reflects it, so when the sweep is enabled
        (opt-in for now, see set_numerical_stability_check) the code is
        swept for numerical instability across the declared domain.
        The sweep is SCOPED: it visits declared endpoints and interior
        draws, and reaches an extreme only where the claim binds an
        operational infinity (`let |inf| be ...`), an unbounded
        direction with no such binding is is_extremity_safe's own job,
        never this sweep's. A genuine break (raise / NaN /
        catastrophic deviation) falsifies the proven-exact claim,
        naming the fragile point and the narrow-the-domain /
        cap-infinity / accept-the-risk remedy. No break, or the check
        turned off -> `proven` unchanged.
    """
    if not _STABILITY_CHECK[0]:
        return proven
    from . import corroboration as C
    cap = getattr(cj, "pseudo_infinity", None)
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            cap=cap, scoped_extremes=True)
    if deps is None:
        # a calculus form with no numeric sweep, or an unbounded
        # uncapped direction the scoped sweep declines to invent an
        # extreme for, either way the exact proof stands untouched
        return proven
    sweep = C.sweep_stability(deps["probe_finite"], deps["names"],
                              sample=deps["sample"], corners=deps["corners"],
                              admits=deps["admits"])
    if sweep.fragile_point is None:
        return proven
    pt = _fmt_point(sweep.fragile_point, deps["names"])
    return Probe(
        cj.name, proven.statement, "falsified", route="derive",
        counterexample=pt,
        note=f"{proven.note}; proven exactly in real arithmetic, but "
             f"numerically unstable in the declared domain",
        sketch=f"proven exactly in real arithmetic, but the implementation "
               f"is numerically unstable at {pt} ({sweep.detail}); "
               f"narrow the domain"
               + (" or lower the |inf| binding" if cap is not None else "")
               + ", widen the tolerance to accept the risk, or clamp "
               "the operation",
        meta={**(proven.meta or {}), "mathema.numerically_unstable": pt},
        # the two strata, machine-readable: this falsification is the
        # one whose whole meaning is "mathematics sound, implementation
        # unstable", and the proof that coexists with the executed
        # break is the evidence for saying so
        stratum={"mathematics": "sound", "blame": "implementation",
                 "cause": "implementation:numerical-instability",
                 "representation": "f64", "witness": pt})
