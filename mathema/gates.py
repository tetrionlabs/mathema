# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The soundness gates at the derive->Probe seam, beside the
corroboration engine they drive: `_corroboration_gate` (no derive
disproof survives unless an executed in-domain point reproduces it
against the real function; an unreproduced one downgrades to unknown
with the engine-bug flag), `_float_companion` (the `<name>[float]`
claim a derive proof spawns: the same relation executed against the
real code in float, at the domain's corners and sampled interior
points), and `_point_evaluator`, the injected-dependency builder both
(and the corroboration engine) run on.

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

# how far a float companion reaches along an unbounded direction when the
# claim declares no `|inf|`: the largest power of ten a float64 holds
_FLOAT_REACH = 1e308

# the name suffix, and the family, of a derive claim's implementation
# companion
FLOAT_SUFFIX = "[float]"
FLOAT_FAMILY = "is_numerically_stable"

# the authored route that states the mathematics alone: adjudicated as
# a derive claim, spawning no float companion
MATH_ONLY_ROUTE = "derive:math_only"


def _integer_bound(bound) -> bool:
    """Intent:
        Whether a declared bound admits integers only: a `Z`/`N` domain
        (a subset of one included) or a finite set of whole numbers.
        What a parameter's values ARE is read off its domain, whatever
        its annotation says.
    """
    from .domain import bound_assumptions
    if isinstance(bound, (frozenset, set)):
        return bool(bound) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            and v == v and abs(v) != float("inf") and v == int(v)
            for v in bound)
    try:
        return bool((bound_assumptions(bound) or {}).get("integer"))
    except Exception:
        return False


def _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum=(),
                     cap=None, reach=None, sequences=False):
    """Intent:
        Build the injected dependencies the corroboration engine needs
        for THIS claim: `evaluate(point)` decides the original claim's
        relation at a concrete point by calling the real `fn` (True =
        holds, False = a genuine counterexample, None = can't tell);
        `probe_finite(point)` returns an implementation-failure detail
        (a raise, a NaN, an inf or a deviation past a magnitude-scaled
        tolerance where the relation fails) or None; `admits(point)` is
        in-domain-and-assumption membership; `sample(name, rng)` draws
        a value respecting the parameter's declared bound; `corners`
        are the domain's corner points; `reach` is the magnitude an
        unbounded direction runs to; plus the free-variable `names`.

    Notes:
        `None` when the claim can't be numerically evaluated at all (a
        calculus form d/lim/integrate, or an uncompilable law): the
        caller then marks a disproof uncorroborated and spawns no float
        companion. An unbounded direction runs to `cap`'s resolved
        pseudo-infinity range when one is declared, else to `reach`
        when given (the float companion's large magnitude, sampled
        log-uniformly so moderate magnitudes are visited too), else to
        +-`_EXTREME`. A sequence parameter is evaluable only with
        `sequences=True`: `sample` then draws a list (respecting a
        declared per-element bound) and `admits` requires a list whose
        every element the bound admits. A coordinate whose domain is
        integer-only reaches `fn` as an int, corners included.
    """
    import math
    from .domain import (_as_int_if_whole, bound_to_sympy_set,
                         domain_contains, is_missing)
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
    slack = cj.tolerance if cj.tolerance is not None else 1e-9
    # `ε`/`eps`/`epsilon` in a law is the claim's tolerance, a fixed
    # value, never a free variable to sample
    eps_names = (aux_l | aux_r) & {"eps", "epsilon", "ε"}
    names = list(kinds) + sorted((aux_l | aux_r) - MATH_CONSTANTS.keys()
                                 - eps_names)
    # raises from the function under test (or a bound function) are
    # tagged so the evaluators below can tell a genuine in-domain raise,
    # which IS a failure of a value claim, per the pedantic raise
    # rule, from a raise in the law's own plumbing, which proves
    # nothing about the claim; a non-finite RESULT from the function is
    # tagged the same way, since an inf or NaN the law's own arithmetic
    # produced says nothing about the code either
    calls_raised = [None]
    calls_nonfinite = [False]

    def _tag(callee):
        def _wrapped(*a, **kw):
            try:
                out = callee(*a, **kw)
            except Exception as exc:
                calls_raised[0] = type(exc).__name__
                raise
            if isinstance(out, float) and (out != out
                                           or abs(out) == float("inf")):
                calls_nonfinite[0] = True
            return out
        return _wrapped

    def _reset():
        calls_raised[0] = None
        calls_nonfinite[0] = False

    base_env = {"f": _tag(fn), **_SAFE_FUNCS, **MATH_CONSTANTS,
                **{name: _tag(v) for name, v in bound_funcs.items()},
                **{name: slack for name in eps_names}}
    from .records import pseudo_infinity_range
    if cap is not None:
        cap_lo, cap_hi = pseudo_infinity_range(cap)
    elif reach is not None:
        cap_lo, cap_hi = -float(reach), float(reach)
    else:
        cap_lo, cap_hi = -_EXTREME, _EXTREME

    int_names = {name for name in names
                 if _integer_bound(cj_domain.get(name))
                 or kinds.get(name) in ("int", "bool")}

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
        _reset()
        try:
            lv, rv = _values(point)
        except Exception:
            # a raise FROM THE FUNCTION at an in-domain point is a
            # genuine failure of a value claim (the pedantic raise
            # rule), so it reproduces a disproof; a plumbing raise
            # stays inconclusive
            return False if calls_raised[0] else None
        if _real(lv) and _real(rv):
            if (abs(lv) == float("inf") or abs(rv) == float("inf")) \
                    and not calls_nonfinite[0]:
                # an infinity only the law's own arithmetic produced
                # (the function returned finite values) says nothing
                # about the code
                return None
            # an overflow the function itself returned is an executed
            # value like any other: if the relation fails on it, that
            # is a counterexample (the overflow rule)
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
        # an implementation failure only: a raise from the code, a NaN
        # or an inf the code returned where the relation then fails, or
        # a deviation past a MAGNITUDE-SCALED tolerance (so a correct
        # large-magnitude identity is not flagged, only catastrophic
        # cancellation or a real break is). An inf that still satisfies
        # the relation is fine; a non-numeric result is inconclusive,
        # never a flag.
        _reset()
        try:
            lv, rv = _values(point)
        except Exception:
            # only a raise from the function under test is an
            # implementation failure; the law's own plumbing failing
            # says nothing about the code
            if calls_raised[0]:
                return f"the implementation raises {calls_raised[0]} here"
            return None
        for v in (lv, rv):
            if isinstance(v, complex):
                return None
        if any(isinstance(v, float) and v != v for v in (lv, rv)):
            return ("the implementation returns NaN here"
                    if calls_nonfinite[0] else None)
        if not (_real(lv) and _real(rv)):
            return None
        overflowed = any(abs(v) == float("inf") for v in (lv, rv))
        if overflowed and not calls_nonfinite[0]:
            return None
        scaled = slack + 1e-7 * max(abs(lv) if not overflowed else 0.0,
                                    abs(rv) if not overflowed else 0.0, 1.0)
        if _relation_holds(lv, rv, scaled):
            return None
        if overflowed:
            return (f"the implementation overflows to inf here, and the "
                    f"relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r})")
        return (f"the relation fails on the executed values ({lv!r} "
                f"{cj.relation} {rv!r}), past the magnitude-scaled "
                f"tolerance: precision loss")

    def _ends(bound):
        # the bound's (lo, hi) as floats, +-inf for an unbounded end
        if isinstance(bound, tuple):
            return float(bound[0]), float(bound[1])
        try:
            sset = bound_to_sympy_set(bound)
            return float(sset.inf), float(sset.sup)
        except Exception:
            return None

    def _wide_draw(name, rng, lo, hi):
        # a log-uniform magnitude out to the reach, so an unbounded
        # direction is visited at moderate AND at large magnitudes
        top = max(math.log10(max(abs(cap_lo), abs(cap_hi), 1.0)), 0.0)
        magnitude = 10.0 ** rng.uniform(-3.0, top)
        if math.isinf(lo) and math.isinf(hi):
            value = magnitude if rng.random() < 0.5 else -magnitude
        elif math.isinf(hi):
            value = lo + magnitude
        else:
            value = hi - magnitude
        value = min(max(value, cap_lo if math.isinf(lo) else lo),
                    cap_hi if math.isinf(hi) else hi)
        return int(round(value)) if name in int_names else value

    def sample(name, rng):
        # an unbounded parameter samples within the pseudo-infinity
        # range (or the reach), so a declared range bounds the draws
        # too, not only the corners
        b = cj_domain.get(name)
        if name in seq_names:
            # a sequence's declared bound is per element
            return _synth("sequence", rng, b)
        if reach is not None and cap is None:
            ends = (-math.inf, math.inf) if b is None else _ends(b)
            if ends is not None and (math.isinf(ends[0]) or math.isinf(ends[1])):
                return _wide_draw(name, rng, *ends)
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
            except (TypeError, ValueError, OverflowError):
                continue
            if not domain_contains(fv, bound):
                return False
        for a_l, a_rel, a_r in assum:
            try:
                env = {**base_env, **_typed(point)}
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

    def _endpoint(name, which):
        # the domain's edge in one direction, at the cap/reach when that
        # direction is unbounded, stepped just inside an open end (an
        # integer domain's open end steps to the next integer)
        bound = cj_domain.get(name)
        if bound is None:
            return cap_lo if which == "lo" else cap_hi
        ends = _ends(bound)
        if ends is None:
            return cap_lo if which == "lo" else cap_hi
        val = ends[0] if which == "lo" else ends[1]
        if val != val or math.isinf(val):
            return cap_lo if which == "lo" else cap_hi
        if name in int_names:
            val = math.ceil(val) if which == "lo" else math.floor(val)
            if not domain_contains(val, bound):
                val = val + 1 if which == "lo" else val - 1
            return int(val)
        if not domain_contains(val, bound):
            val = math.nextafter(val, math.inf if which == "lo" else -math.inf)
        return val

    def _corner_value(name, value):
        # a sequence's corner is a short list at the per-element edge
        return [value] * 3 if name in seq_names else value

    edges = {n: (_endpoint(n, "lo"), _endpoint(n, "hi")) for n in names}
    if len(names) <= 6:
        # every corner of the box: 2^k points for k coordinates
        import itertools
        corners = [{n: _corner_value(n, e[i]) for n, e, i in
                    zip(names, (edges[n] for n in names), choice)}
                   for choice in itertools.product((0, 1), repeat=len(names))]
    else:
        corners = [{n: _corner_value(n, edges[n][i]) for n in names}
                   for i in (0, 1)]

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


def companion_name(parent_name: str) -> str:
    """The name of a claim's float companion: `<parent name>[float]`."""
    return f"{parent_name}{FLOAT_SUFFIX}"


def _reach_text(names, cj_domain, cap, reach) -> str:
    """Intent:
        How far the float companion ran along the claim's unbounded
        directions, in words, or an empty string when every coordinate
        is bounded.
    """
    import math
    from .domain import bound_to_sympy_set
    unbounded = []
    for n in names:
        b = cj_domain.get(n)
        if b is None:
            unbounded.append(n)
            continue
        try:
            lo, hi = ((float(b[0]), float(b[1])) if isinstance(b, tuple) else
                      (float(bound_to_sympy_set(b).inf),
                       float(bound_to_sympy_set(b).sup)))
        except Exception:
            continue
        if math.isinf(lo) or math.isinf(hi):
            unbounded.append(n)
    if not unbounded:
        return ""
    who = ", ".join(unbounded)
    if cap is not None:
        return f"unbounded directions ({who}) run to the declared |inf|"
    return (f"unbounded directions ({who}) run to magnitude "
            f"{reach[1]:.0e}, sampled log-uniformly (no |inf| declared)")


def _float_companion(parent, cj, fn, facts, cj_domain, bound_funcs,
                     assum=(), budget=None) -> "Probe | None":
    """Intent:
        The implementation claim a derive proof spawns. `parent` is
        proven in exact arithmetic, which is all a derive `proven`
        says; the companion `<name>[float]` is the same relation
        executed against the REAL code in float: at every corner of
        the declared domain and at sampled interior points, unbounded
        directions running to the claim's `pseudo_infinity` when one is
        declared and to a large magnitude (1e308, sampled log-uniformly)
        otherwise. A raise, a NaN, or an inf or a precision loss where
        the relation fails on the executed values falsifies it with
        that point as the witness; otherwise it holds, over the points
        it executed.

    Notes:
        `None` when the claim has no point evaluation against the code
        (a calculus form, a law that won't compile): a limit or an
        integral is a claim about the mathematics only. The companion
        carries the parent's surface, so it gates exactly when the
        parent does. A sweep the wall-clock cap cuts short is
        `unknown`, naming the point that was executing. `budget`, when
        given, is the total number of points drawn, corners included
        (the caller's trials); otherwise every corner plus the
        corroboration budget of interior points.
    """
    from . import corroboration as C
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    cap = getattr(cj, "pseudo_infinity", None)
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            cap=cap, reach=_FLOAT_REACH, sequences=True)
    if deps is None:
        return None
    from .records import pseudo_infinity_range
    name = companion_name(parent.name)
    reach = (pseudo_infinity_range(cap) if cap is not None
             else (-_FLOAT_REACH, _FLOAT_REACH))
    reach_text = _reach_text(deps["names"], cj_domain, cap, reach)
    interior = (C._CORROBORATION_BUDGET if budget is None
                else max(0, int(budget) - len(deps["corners"])))
    progress = C.StabilitySweep()
    try:
        sweep = _with_timeout(
            lambda: C.sweep_stability(deps["probe_finite"], deps["names"],
                                      sample=deps["sample"],
                                      corners=deps["corners"],
                                      admits=deps["admits"],
                                      budget=interior, progress=progress),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        at = (_fmt_point(progress.in_flight, deps["names"])
              if progress.in_flight else "")
        return Probe(
            name, parent.statement, "unknown", route="probe",
            n=progress.checked,
            note=f"the implementation of {parent.name}, executed in float; "
                 f"the sweep hit the {FAST_TIMEOUT_SECONDS}s wall-clock cap"
                 + (f" executing {at}" if at else "")
                 + (f"; {reach_text}" if reach_text else ""),
            meta={"mathema.timeout": "fast"})
    what = (f"the implementation of {parent.name}, executed in float at "
            f"{sweep.checked} points (every domain corner, then sampled "
            f"interior points)"
            + (f"; {reach_text}" if reach_text else ""))
    if sweep.fragile_point is not None:
        pt = _fmt_point(sweep.fragile_point, deps["names"])
        remedy = ("narrow the domain, "
                  + ("" if not reach_text else
                     "lower the |inf| binding, " if cap is not None else
                     "declare an |inf| for the unbounded directions, ")
                  + "fix the implementation, or state the claim with "
                    "route derive:math_only")
        return Probe(
            name, parent.statement, "falsified", route="probe",
            n=sweep.checked, counterexample=pt, note=what,
            sketch=f"{parent.name} is proven in exact arithmetic, but the "
                   f"implementation fails it at {pt}: {sweep.detail}; "
                   f"{remedy}",
            # the proof that coexists with the executed break is the
            # evidence that the mathematics is sound and the code is not
            stratum={"mathematics": "sound", "blame": "implementation",
                     "cause": "implementation:numerical-instability",
                     "representation": "f64", "witness": pt})
    if sweep.checked == 0:
        return Probe(name, parent.statement, "skipped", route="probe",
                     note=f"{what}; no in-domain point satisfied the "
                          f"claim's premises, so nothing was executed")
    return Probe(name, parent.statement, "holds", route="probe",
                 n=sweep.checked, note=what)
