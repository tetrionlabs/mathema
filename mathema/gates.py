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
                     cap=None, scoped_extremes=False, sequences=False,
                     exact=False):
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
        `exact` drops the default allowance, so a claim with no
        declared tolerance is compared with none;
        `corners` are the domain endpoints (infinity taken at `cap`'s
        resolved pseudo-infinity range, else +-`_EXTREME`); plus the
        free-variable `names`.

    Notes:
        `None` when the claim can't be numerically evaluated at all (a
        calculus form d/lim/integrate, or an uncompilable law), the
        caller then marks a disproof uncorroborated and skips a proof's
        sweep. A sequence parameter is evaluable only with
        `sequences=True`: `sample` then draws a list (respecting a
        declared per-element bound) and `admits` requires a list whose
        every element the bound admits.
    """
    from .domain import (_as_int_if_whole, bound_assumptions,
                         bound_to_sympy_set, domain_contains, is_missing)
    from .probing import _synth
    InvalidConjecture, _SAFE_FUNCS, _validate = _conjecture_bits()
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    # the gates verify VALUE claims by calling fn at a point; a
    # non-value relation or a bundled (dataclass/dict) parameter isn't
    # reproducible this way, and a sequence parameter only when the
    # caller asked for list-valued points
    seq_names = {p for p, k in kinds.items() if k == "sequence"}
    if seq_names and not sequences:
        return None
    if cj.relation not in ("==", "~=", "!=", "<=", ">=", "<", ">"):
        return None
    extra = frozenset(bound_funcs)
    try:
        code_l, aux_l = _validate(cj.lhs, set(kinds), extra)
        code_r, aux_r = _validate(cj.rhs, set(kinds), extra) if cj.rhs else (None, set())
    except InvalidConjecture:
        return None
    slack = (cj.tolerance if cj.tolerance is not None
             else 0.0 if exact else 1e-9)
    # `ε`/`eps`/`epsilon` in a law is the claim's tolerance, a fixed
    # value, never a free variable to sample
    eps_names = (aux_l | aux_r) & {"eps", "epsilon", "ε"}
    names = list(kinds) + sorted((aux_l | aux_r) - MATH_CONSTANTS.keys()
                                 - eps_names)
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
                **{name: _tag(v) for name, v in bound_funcs.items()},
                **{name: (cj.tolerance if cj.tolerance is not None else 1e-9)
                   for name in eps_names}}
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

    int_names = set()
    for name in names:
        try:
            if (bound_assumptions(cj_domain.get(name)) or {}).get("integer"):
                int_names.add(name)
        except Exception:
            continue

    def _typed(point):
        # a whole-number coordinate of an integer domain is passed as an
        # int, the value the probe route draws there; a float would make
        # `range(n)` raise where the claim is about integers
        return {n: (_as_int_if_whole(v) if n in int_names else v)
                for n, v in point.items()}

    def _values(point):
        env = {**base_env, **_typed(point)}
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
            # with no declared tolerance an inequality fails only at an
            # actual equality
            if cj.tolerance is None:
                return not (lv == rv)
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
        # opaque disproof reproduces), and ordering over non-orderable
        # values proves nothing. A NaN that propagates a missing input
        # is the missing-policy axis's business, inconclusive here; a
        # NaN computed from non-missing inputs is read as IEEE reads
        # it: no ordering holds, it equals no number, and two NaN
        # sides agree, as the probe route's comparison has it
        nan_sides = [isinstance(v, float) and v != v for v in (lv, rv)]
        if any(nan_sides):
            if any(is_missing(v) for v in point.values()):
                return None
            if cj.relation in ("==", "~="):
                return all(nan_sides)
            if cj.relation == "!=":
                return not all(nan_sides)
            return False
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
        if name in seq_names:
            # a sequence's declared bound is per element
            return _synth("sequence", rng, b)
        if b is None:
            b = (cap_lo, cap_hi)
        return _synth(kinds.get(name, "float"), rng, b)

    def admits(point):
        for n in seq_names:
            # a sequence coordinate is a list, each element inside the
            # declared per-element bound
            v = point.get(n)
            if not isinstance(v, (list, tuple)):
                return False
            bound = cj_domain.get(n)
            if bound is not None and not all(
                    isinstance(e, (int, float)) and domain_contains(e, bound)
                    for e in v):
                return False
        for n in names:
            bound = cj_domain.get(n)
            v = point.get(n)
            if bound is None or v is None or n in seq_names:
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


def _sequence_witness(witness, seq_names):
    """Intent:
        A symbolic witness with each sequence parameter's element
        coordinates reassembled into a list the real function can be
        called with. A fold's disproof names its witness per element
        (`x[0]`, `x[L - 1]`, `x[k]`) beside an integer length symbol
        (`L`); the list has that length, the concretely indexed
        elements at their positions and a symbolically indexed
        element's value everywhere else.

    Notes:
        A sequence whose length can't be read off the witness is left
        out, so the corroboration search samples that parameter
        instead. Every other coordinate passes through unchanged, and
        an empty or absent witness comes back as given.
    """
    import re as _re
    if not witness or not seq_names:
        return witness
    out = dict(witness)
    for p in seq_names:
        entries = {}
        for key, value in witness.items():
            m = _re.fullmatch(rf"{_re.escape(p)}\[(.+)\]", str(key))
            if m is not None and isinstance(value, (int, float)):
                entries[m.group(1).strip()] = float(value)
        for key in [k for k in out if str(k).startswith(f"{p}[")]:
            del out[key]
        # the bare parameter name, when the witness carries one, is a
        # scalar stand-in the list replaces
        out.pop(p, None)
        if not entries:
            continue
        index_names = {n for text in entries
                       for n in _re.findall(r"[A-Za-z_]\w*", text)}
        lengths = [witness[n] for n in sorted(index_names)
                   if isinstance(witness.get(n), (int, float))
                   and float(witness[n]).is_integer() and witness[n] >= 1]
        env = {n: int(witness[n]) for n in index_names
               if isinstance(witness.get(n), (int, float))
               and float(witness[n]).is_integer()}
        concrete, filler = {}, None
        for text, value in entries.items():
            try:
                idx = eval(compile(text, "<index>", "eval"),
                           {"__builtins__": {}}, dict(env))
            except Exception:
                filler = value if filler is None else filler
                continue
            if isinstance(idx, int):
                concrete[idx] = value
        if lengths:
            n = int(lengths[0])
        elif concrete and all(i >= 0 for i in concrete):
            n = max(concrete) + 1
        else:
            continue
        seq = [filler if filler is not None else 0.0] * n
        for idx, value in concrete.items():
            if -n <= idx < n:
                seq[idx] = value
        out[p] = seq
    return out


_DEFAULT_ORDERING_SLACK = 1e-9


def _exact_witness_violation(cj, fn, facts, cj_domain, bound_funcs, assum,
                             proof, seq_names):
    """Intent:
        The point derive named as its witness, when the real code
        executed there violates a closed ordering (`<=`/`>=`) compared
        exactly, with none of the default allowance. None when the
        claim is not such an ordering, declares its own tolerance
        (which is then part of the claim), names no complete in-domain
        witness, or the code satisfies the relation there exactly.
    """
    from . import corroboration as C
    if cj.relation not in ("<=", ">=") or cj.tolerance is not None:
        return None
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            sequences=True, exact=True)
    if deps is None:
        return None
    seeds = C._seed_points(_sequence_witness(proof.witness, seq_names),
                           deps["names"])
    if not seeds:
        return None
    point = seeds[0]
    if set(point) != set(deps["names"]) or not deps["admits"](point):
        return None
    return point if deps["evaluate"](point) is False else None


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
        was claimed. A disproof whose witness is already an executed
        call to the real function (a raise-region disproof ran the call
        and saw it raise) stands as it is.
    """
    from . import corroboration as C
    if proof.meta.get("mathema.witness_executed") and falsified.counterexample:
        # no stratum: a raise at the witness is the contract or the
        # mathematics talking, which the probe route leaves unclassified
        # too (conjecture._machine_failure_stratum)
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        return falsified
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            sequences=True)
    if deps is None:
        # a claim with no point evaluation against the function (a
        # calculus form d/lim/integrate, a law that won't compile, a
        # bundled parameter) can't produce an executed witness, and a
        # falsification needs one: the verdict is unknown, flagged
        # uncorroborated like any other disproof nothing reproduced
        falsified.verdict = "unknown"
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "uncorroborated",
                          "mathema.corroboration_unexecutable": True}
        falsified.counterexample = None
        falsified.note = (
            f"{falsified.note}; uncorroborated disproof: the derive route "
            f"reported this false, but the claim form has no point "
            f"evaluation against the function, so the symbolic disproof "
            f"has no executed witness, and a falsification needs one; the "
            f"verdict stays unknown").lstrip("; ")
        return falsified
    seq_names = [n for n in deps["names"]
                 if facts.param_kinds.get(n) == "sequence"]
    result = C.corroborate_disproof(deps["evaluate"], deps["names"],
                                    sample=deps["sample"], admits=deps["admits"],
                                    witness=_sequence_witness(proof.witness,
                                                              seq_names))
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
    exact_point = _exact_witness_violation(cj, fn, facts, cj_domain,
                                           bound_funcs, assum, proof,
                                           seq_names)
    if exact_point is not None:
        pt = _fmt_point(exact_point, deps["names"])
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        falsified.counterexample = pt or falsified.counterexample
        if falsified.stratum is None:
            falsified.stratum = {"mathematics": "unsound",
                                 "blame": "claim", "witness": pt}
        falsified.note = (
            f"{falsified.note}; reproduced exactly at derive's witness: "
            f"the executed code violates the relation there by less than "
            f"the default tolerance ({_DEFAULT_ORDERING_SLACK:g}) the probe "
            f"route allows, and compared exactly it fails").lstrip("; ")
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
