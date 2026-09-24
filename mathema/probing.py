# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Probing: empirical evidence for mathematical properties.

Probes call the real function on synthesized inputs and check algebraic laws
numerically. Verdicts are honest about their strength: `holds (probed n=…)`
is evidence, not proof; `falsified` comes with the counterexample. Only pure
functions are probed.

This module owns the sampling engine and its policy: risk/budget
heuristics, domain-aware value synthesis, critical-point-informed
hints, pole/domain safety analysis, and `probe()` itself. The claim
suggestion battery lives in `suggest.py`; the built-in claim families
(probe:algorithmic techniques and the derive-route safety checks) live
in `claim_families.py`.
"""
from __future__ import annotations

import cmath
import math
import random
from dataclasses import dataclass

import sympy

from ._sampling import (
    _RNG_SEED as _RNG_SEED, _SPECIALS as _SPECIALS,
    _SpecialCycle as _SpecialCycle, _finite_bounds as _finite_bounds,
    _synth_scalar as _synth_scalar,
)
from .grammar import MISSING, Domain, domain_contains
# Probe's real home is records.py (the stdlib-only leaf every layer can
# import); re-exported here because probing is where consumers
# historically found it.
from .records import Probe as Probe


# Adaptive trial budget. A flat n for every law spends the same effort on a
# two-line affine function as on a five-branch one, neither serves the
# reader well, so n is instead decided once, statically, per probe() call
# (see _starting_budget()), from the function's own structure alone:
#
# - up, from _N_BASE toward _N_MAX: a structurally complex function (more
#   branches, more loops, a wide or unbounded declared domain; see
#   _structural_risk()) gets a higher budget, since a fixed sample density
#   covers less of a bigger behavioral space.
# - down, to a single reduced tier: a function the derive route can *prove*
#   is affine (see _affine_hint()) is trivially well-behaved in shape, so it
#   gets fewer trials, but only when the declared domain doesn't need the
#   extra density anyway (a wide or float-precision-risky domain still gets
#   real coverage regardless of shape).
#
# This budget is the same for every law in the battery and does not change
# while they run; there is no cross-law memory, and a later probe() call
# on the same function starts fresh from the same static decision, not from
# anything an earlier call observed. Override per call with
# explain(..., trials=N); an explicit trials= is respected exactly,
# everywhere in this call, with no adaptivity at all.
#
# Sampling is deliberately not uniform. Functions break at special points, so
# ~30% of draws come from a boundary/special pool (0, ±1, ±tiny, ±huge, and
# the declared domain's edges and midpoint when a domain is given); the rest
# are uniform. Everything is seeded, so verdicts are reproducible.
_N_BASE = 128
_N_MAX = 256


@dataclass(frozen=True)
class _RiskPolicy:
    """Every tunable number behind _structural_risk()/_starting_budget()/
    _probe_density(), grouped into one inspectable object instead of
    scattered as bare literals or a pile of separate module-level names.
    `max_*` fields cap a risk factor, past that many branches/loops/
    wide-or-extreme domains, one more doesn't change the picture much,
    the same way a sixth branch isn't meaningfully riskier than the
    fourth already was. `*_penalty` fields are how many confidence-score
    points one unit of the corresponding factor costs; `wide_span`/
    `tiny_magnitude`/`huge_magnitude` are what counts as a domain a
    fixed sample density thins out fast, or where float precision itself
    becomes a risk."""
    max_branch_risk: int = 3
    max_loop_risk: int = 2
    free_params: int = 2             # first two params add no combinatorial risk
    max_wide_domain_risk: int = 2
    max_float_extreme_risk: int = 2
    wide_span: float = 1e4
    tiny_magnitude: float = 1e-6
    huge_magnitude: float = 1e9
    branch_penalty: float = 1.0
    loop_penalty: float = 1.5
    param_penalty: float = 0.5
    wide_domain_penalty: float = 1.0
    float_extreme_penalty: float = 1.0
    score_min: float = 1.0
    score_max: float = 10.0
    budget_step_per_unit: int = 32    # extra trials per unit of starting complexity
    affine_budget: int = 32           # a provably affine function, well-behaved domain
    min_trials_floor_when_scaled: int = 16   # trials_scale never shrinks a budget below this
    max_critical_hints_per_param: int = 1000   # see _hints_from_points's own truncation note


_RISK = _RiskPolicy()


def _affine_hint(fn, facts) -> bool:
    """True only if the derive route can *prove* fn is affine (a constant
    slope) in every one of its scalar parameters, never a guess. An
    affine function is trivially monotone (or constant) everywhere by
    construction, no domain assumptions needed, so this is a narrow but
    airtight structural signal: checking `d(f, p)` (real, not empirical)
    has no free symbols left after simplifying, for every scalar `p`.
    `False` for anything not liftable at all (a loop, a branch, a non-
    scalar parameter, see symbolic.lift()), or liftable but genuinely
    nonlinear (`x**2`, `sin(x)`, ...). Broader, non-affine monotonicity
    (a provably sign-constant derivative that isn't itself constant) and
    critical-point-aware sampling are natural next steps built on the
    same lifted form, not attempted here yet."""
    try:
        from .symbolic import lift
        import sympy
        lifted = lift(fn, facts)
    except Exception:
        return False
    if lifted is None or not lifted.params:
        return False
    if not isinstance(lifted.expr, sympy.Basic):
        # a tuple-valued (multi-value) or _SymbolicArray-valued (an
        # np.linspace/np.arange-shaped lift) return isn't a single
        # differentiable expression; both fail this check, not just
        # the tuple case.
        return False
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        return _with_timeout(
            lambda: all(sympy.simplify(
                sympy.diff(lifted.expr, sym)).free_symbols == set()
                for sym in lifted.params.values()),
            FAST_TIMEOUT_SECONDS)
    except Exception:
        return False


def _points_for_probe(fn, facts, domain: dict, extensive: bool) -> list[dict]:
    """Intent:
        The critical-point list _critical_hint()/is_pole_safe's own
        derive route both need, computed at most once per probe() call
        (and, for is_pole_safe/is_numerically_stable, at claim-adjudication
        time too).

    Notes:
        Fast mode (default): direct lift()-only, matching
        _affine_hint()'s own restriction. 1-second cap, uncached.

        Extensive mode is not just the same analysis run slower.
        audit._try_derive_lift's own chain includes lift_conditioned(),
        which can resolve part of a branchy function symbolically
        (pruning branches via the declared domain) even when the
        function as a whole does not lift. So a partially-liftable
        function's own sampling can become genuinely hybrid under
        extensive mode: some candidates come from a real partial
        symbolic resolution, not pure empirical trial. Uses
        diagnostics._cached_critical_points (memoized by facts.form)
        and a 15-second cap.

        Degrades to [] on any failure in either mode.
    """
    try:
        from . import diagnostics
        from ._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                               FAST_TIMEOUT_SECONDS, _with_timeout)
        if extensive:
            return _with_timeout(
                lambda: diagnostics._cached_critical_points(fn, facts),
                EXTENSIVE_TIMEOUT_SECONDS)
        from .symbolic import lift
        lifted = lift(fn, facts)
        if lifted is None or isinstance(lifted.expr, tuple):
            return []
        return _with_timeout(
            lambda: diagnostics._critical_points_over_expr(
                lifted.expr, diagnostics._source_file(fn)),
            FAST_TIMEOUT_SECONDS)
    except Exception:
        return []


def _hints_from_points(points: list[dict],
                       policy: _RiskPolicy = _RISK) -> tuple[dict[str, list[float]], set[str]]:
    """Intent:
        Per-parameter real-valued sampling candidates extracted from a
        critical-point list (see _synth_scalar's extra/extra_cycle).

    Notes:
        Drops any point whose "at" doesn't evaluate to a finite real
        (a complex or symbolic root), not every discovered point is
        usable as a concrete sample value. A parameter whose own
        discovered-point count exceeds `policy.max_critical_hints_per_param`
        (a high-degree polynomial's many real roots, say) is truncated to
        that many rather than handed to `_SpecialCycle` uncapped; its
        own guaranteed-coverage lap would otherwise spend the entire
        trial budget cycling through hints alone, crowding out ordinary
        sampling. Returns `(hints, truncated)`, `truncated` naming which
        parameters actually hit the cap, so a caller can say so in the
        reported evidence rather than truncating silently.
    """
    hints: dict[str, list[float]] = {}
    for pt in points:
        try:
            v = float(sympy.sympify(pt["at"]).evalf())
        except Exception:
            continue
        if v != v or abs(v) == float("inf"):
            continue
        hints.setdefault(pt["variable"], []).append(v)
    truncated = {p for p, vs in hints.items() if len(vs) > policy.max_critical_hints_per_param}
    for p in truncated:
        hints[p] = hints[p][:policy.max_critical_hints_per_param]
    return hints, truncated


def _critical_hint(fn, facts, domain: dict, extensive: bool = False) -> dict[str, list[float]]:
    """Intent:
        Per-parameter real critical points, for extra sampling
        candidates. Thin wrapper over _points_for_probe/_hints_from_points,
        kept as its own function for direct unit testing.
    """
    hints, _truncated = _hints_from_points(_points_for_probe(fn, facts, domain, extensive))
    return hints


#: The hazard kinds every probe folds into its sampling candidates by
#: default: knowledge about THIS function (a compendium-covered callee's guard
#: boundary). Generic stress kinds (the magnitude decade sweep) are
#: request-side, a family that wants them asks by kind, because a
#: universal sweep measurably crowds ordinary in-domain sampling out
#: of the trial budget and costs real falsifications.
_SAMPLING_HAZARD_KINDS = ("compendium",)


def _hazard_hint_values(fn, facts, domain: dict,
                        kinds: tuple = _SAMPLING_HAZARD_KINDS) -> dict[str, list[float]]:
    """Intent:
        The hazard registry's finite values for `kinds`, per
        parameter: sampling candidates in the same shape
        `_critical_hint` returns, merged beside it in
        `_prepare_sampling`.

    Notes:
        Non-finite injections (nan, inf, None) stay with the safety
        batteries, which observe behaviour rather than sample values.
        Degrades to {} on any failure: hazard discovery is context,
        never a precondition of sampling.
    """
    out: dict[str, list[float]] = {}
    try:
        from .hazards import hazard_points
        for pt in hazard_points(fn, facts, domain, kinds=list(kinds)):
            v = pt.value
            if v is None or v != v or abs(v) == float("inf"):
                continue
            if pt.param in getattr(facts, "params", ()):
                out.setdefault(pt.param, []).append(float(v))
    except Exception:
        return {}
    return out


def _structural_risk(facts, domain: dict, policy: _RiskPolicy = _RISK) -> dict:
    """How much of a function's real behavior a fixed sample size can
    realistically cover, as named, capped factors, not a statistical
    calculation, a legible heuristic in the same honest spirit as
    `holds (n=...)` itself: each factor is named so a low score is
    diagnosable, not just a number. `branches`/`loops` widen the space of
    *paths* a fixed n must split its attention across; `params` widens
    the space of *combinations*; `wide_domain`/`float_extremes` flag a
    declared domain a fixed sample density thins out fast (unbounded or
    very wide) or where float precision itself becomes a risk (very
    large or very near-zero magnitudes)."""
    wide_domain, float_extremes = 0, 0
    for p in facts.params:
        bounds = domain.get(p)
        if not isinstance(bounds, tuple):
            continue
        lo, hi = bounds
        if math.isinf(lo) or math.isinf(hi) or (hi - lo) > policy.wide_span:
            wide_domain += 1
        if (0 < abs(lo) < policy.tiny_magnitude) or (0 < abs(hi) < policy.tiny_magnitude) \
                or abs(lo) > policy.huge_magnitude or abs(hi) > policy.huge_magnitude:
            float_extremes += 1
    return {
        "branches": min(facts.branch_count, policy.max_branch_risk),
        "loops": min(len(facts.loops), policy.max_loop_risk),
        "params": max(0, len(facts.params) - policy.free_params),
        "wide_domain": min(wide_domain, policy.max_wide_domain_risk),
        "float_extremes": min(float_extremes, policy.max_float_extreme_risk),
    }


def _starting_budget(risk: dict, affine: bool, policy: _RiskPolicy = _RISK) -> int:
    """A single, static trial count for the whole probe() battery,
    decided once from the function's own structure, never adjusted
    reactively while laws run (there is no cross-law memory in this
    module; every probe() call is independent). `affine` only ever
    lowers the budget, and only when the declared domain doesn't need
    the extra density anyway: a provably affine function is trivially
    well-behaved in *shape*, but a wide or float-precision-risky domain
    (`risk["wide_domain"]`/`risk["float_extremes"]`) still needs real
    coverage regardless of shape, so affine-ness is ignored rather than
    overriding that."""
    if affine and risk["wide_domain"] == 0 and risk["float_extremes"] == 0:
        return policy.affine_budget
    complexity = risk["branches"] + risk["loops"] + risk["wide_domain"]
    return min(_N_MAX, _N_BASE + complexity * policy.budget_step_per_unit)


_PROBE_MAX_STARS = 4   # sampling evidence, however extensive, is never proof;
                       # 5 stars is reserved for an actual derive-route `proven`
                       # verdict, which doesn't go through this heuristic at all


def _probe_density(risk: dict, n_trials: int, policy: _RiskPolicy = _RISK) -> dict:
    """A 1-10 confidence heuristic for one probe's verdict, how much a
    reader should lean on `n_trials` samples given this function's own
    structural risk factors. Not a calibrated probability (mathema
    doesn't have the statistics to back that claim): a relative,
    explainable signal, same honesty standard as everything else this
    module reports. `stars` is the same score compressed to a 1-4 scale
    for a compact display, capped below the derive route's own 5, so
    "look how many trials" can never visually read as strong as an
    actual proof. `factors` is `_structural_risk()`'s own breakdown, so
    a low score is always traceable to a specific cause."""
    score = policy.score_max
    score -= risk["branches"] * policy.branch_penalty
    score -= risk["loops"] * policy.loop_penalty
    score -= risk["params"] * policy.param_penalty
    score -= risk["wide_domain"] * policy.wide_domain_penalty
    score -= risk["float_extremes"] * policy.float_extreme_penalty
    # centered on _N_BASE, not linear: doubling n from there is worth a
    # flat +1, same as halving it costs a flat -1, extra trials past a
    # point buy steadily less legibility, not steadily less risk.
    score += math.log2(max(n_trials, 1) / _N_BASE)
    score = max(policy.score_min, min(policy.score_max, score))
    stars = max(1, min(_PROBE_MAX_STARS, round(score / 2.5)))
    return {"score": round(score, 1), "stars": stars, "max_stars": 5,
           "n": n_trials, "factors": dict(risk)}


def _close(u, v, tolerance: float | None = None) -> bool:
    """`tolerance` overrides the default abs_tol, a claim's own declared
    tolerance (declared-schema.md) governs its own comparison outright;
    the 1e-9 default is only a floating-point-representation fudge factor
    for claims that never declared one."""
    if isinstance(u, bool) or isinstance(v, bool):
        return u == v
    if isinstance(u, (int, float)) and isinstance(v, (int, float)):
        if math.isnan(u) and math.isnan(v):
            return True
        return math.isclose(u, v, rel_tol=1e-6,
                            abs_tol=tolerance if tolerance is not None else 1e-9)
    if isinstance(u, (int, float, complex)) and isinstance(v, (int, float, complex)):
        return cmath.isclose(u, v, rel_tol=1e-6,
                             abs_tol=tolerance if tolerance is not None else 1e-9)
    if isinstance(u, (list, tuple)) and isinstance(v, (list, tuple)):
        return len(u) == len(v) and all(_close(a, b, tolerance) for a, b in zip(u, v))
    return u == v


def _synth_dict(key_tree, rng: random.Random, specials=None) -> dict:
    """A dict matching the (possibly NESTED) key structure the body
    reads (`_dict_key_tree`): a key with children becomes a nested dict,
    a leaf key a synthesized scalar, so `cfg["a"]["b"]` finds `cfg["a"]`
    a dict rather than a scalar. An empty structure (the body only
    iterates, `d.values()`) gets a few generic scalar keys, plus
    sometimes an extra key the body never asks for."""
    if not key_tree:
        key_tree = {f"k{i}": {} for i in range(rng.randint(1, 4))}
    out = {k: (_synth_dict(sub, rng, specials) if sub
               else _synth_scalar(rng, specials=specials))
           for k, sub in key_tree.items()}
    if rng.random() < 0.3:
        out[f"extra{rng.randint(0, 9)}"] = _synth_scalar(rng, specials=specials)
    return out


def _scalar_relation(a, b, relation: str, slack: float,
                     exact_inequality: bool = False):
    """One scalar comparison for the elementwise walk. A strict `<`/`>`
    gets no tolerance credit; a closed `<=`/`>=` gets the slack; `==`/
    `~=` go through `_close`, and so does `!=` when the claim declared a
    tolerance. With `exact_inequality`, `!=` fails only where the two
    values are equal, so a representation tolerance never makes two
    different values a counterexample. Raises TypeError for values that
    do not order (a complex vs a real), which the caller reads as
    'unanswerable', not 'false'."""
    if relation in ("==", "~="):
        return _close(a, b, tolerance=slack)
    if relation == "!=":
        if exact_inequality:
            return not (a == b or (a != a and b != b))
        return not _close(a, b, tolerance=slack)
    if relation == "<=":
        return a <= b + slack
    if relation == ">=":
        return a >= b - slack
    if relation == "<":
        return a < b
    return a > b


def _is_matrix_value(v) -> bool:
    """Whether a value is matrix/array-valued (a nested sequence or a
    numpy array), so a relation over it is compared elementwise."""
    if isinstance(v, (list, tuple)):
        return True
    return hasattr(v, "shape") and hasattr(v, "__array__")


def relation_holds_elementwise(lv, rv, relation: str, slack: float,
                               exact_inequality: bool = False):
    """Whether `lv <relation> rv` holds: a scalar comparison, or, when a
    side is matrix/array-valued, the relation at EVERY element (a scalar
    broadcasts against a matrix). numpy fast path when either side is an
    array, a recursive walk over nested lists otherwise. Returns
    `True`/`False`, or `None` when the comparison is structurally
    meaningless (an ordering over non-orderable values, or mismatched
    shapes), which the caller reads as skip, never falsify.
    `exact_inequality` makes `!=` compare exactly (see
    `_scalar_relation`)."""
    if not _is_matrix_value(lv) and not _is_matrix_value(rv):
        try:
            return bool(_scalar_relation(lv, rv, relation, slack,
                                         exact_inequality))
        except TypeError:
            return None
    from .matrices import _numpy
    np = _numpy()
    if np is not None and (hasattr(lv, "__array__") or hasattr(rv, "__array__")
                           or isinstance(lv, (list, tuple))
                           or isinstance(rv, (list, tuple))):
        try:
            a = np.asarray(lv, dtype=float)
            b = np.asarray(rv, dtype=float)
        except Exception:
            return None
        try:
            if relation in ("==", "~="):
                return bool(np.allclose(a, b, rtol=1e-6, atol=slack))
            if relation == "!=":
                if exact_inequality:
                    return not bool(np.array_equal(a, b, equal_nan=True))
                return not bool(np.allclose(a, b, rtol=1e-6, atol=slack))
            if relation == "<=":
                return bool((a <= b + slack).all())
            if relation == ">=":
                return bool((a >= b - slack).all())
            if relation == "<":
                return bool((a < b).all())
            return bool((a > b).all())
        except (ValueError, TypeError):
            return None       # incompatible shapes: unanswerable

    def _walk(x, y):
        xs, ys = isinstance(x, (list, tuple)), isinstance(y, (list, tuple))
        if xs and ys:
            if len(x) != len(y):
                return None
            parts = [_walk(u, v) for u, v in zip(x, y)]
        elif xs:
            parts = [_walk(u, y) for u in x]   # broadcast scalar y
        elif ys:
            parts = [_walk(x, v) for v in y]   # broadcast scalar x
        else:
            try:
                return bool(_scalar_relation(x, y, relation, slack,
                                             exact_inequality))
            except TypeError:
                return None
        return None if any(pt is None for pt in parts) else all(parts)

    return _walk(lv, rv)


# _finite_bounds/_SpecialCycle/_synth_scalar live in ._sampling now,
# shared with symbolic/_proof_support.py's disproof corroboration,
# imported above, re-exported under their own names for existing
# importers of mathema.probing.


def _sample_bare_named_set(rng: random.Random, name: str):
    if name == "Z":
        return (rng.choice([0, 1, -1, 2, -2]) if rng.random() < 0.3
               else rng.randint(-1000, 1000))
    if name == "N":
        return rng.choice([0, 1, 2]) if rng.random() < 0.3 else rng.randint(0, 1000)
    if name == "C":
        # a square patch of the plane, with the plane's own landmark
        # values favored the way the real specials pool favors 0/1/-1.
        if rng.random() < 0.3:
            return rng.choice([0j, 1 + 0j, -1 + 0j, 1j, -1j,
                               1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j])
        return complex(rng.uniform(-10, 10), rng.uniform(-10, 10))
    return rng.uniform(-10, 10)   # "R"


def _sample_domain(rng: random.Random, dom: Domain,
                   specials: "_SpecialCycle | None" = None):
    """Sample one value from a `Domain` (grammar.py's exclusion/union/
    type-refinement shape), a union picks one piece first, weighted
    by span for an interval piece so a wide piece isn't sampled as
    rarely as a single point would be, then samples within it,
    respecting `base_type` (`Z`/`N` rounds to an int) and retrying
    (bounded, not exact; this is probe sampling, not a precise
    excluded-measure-zero guarantee) to avoid landing exactly on an
    excluded value."""
    def _rectangle(p):
        return (isinstance(p, tuple) and not isinstance(p, frozenset)
                and any(isinstance(v, complex) for v in p))

    pieces = dom.pieces or (dom.base_type,)
    weights = []
    for p in pieces:
        if _rectangle(p):
            weights.append(1.0)
        elif isinstance(p, tuple):
            lo, hi = _finite_bounds(*p)
            weights.append(max(hi - lo, 1e-9))
        else:
            weights.append(1.0)
    for _ in range(20):
        piece = rng.choices(pieces, weights=weights, k=1)[0]
        if isinstance(piece, frozenset):
            value = rng.choice(list(piece))
        elif _rectangle(piece):
            c1, c2 = complex(piece[0]), complex(piece[1])
            value = complex(
                rng.uniform(min(c1.real, c2.real), max(c1.real, c2.real)),
                rng.uniform(min(c1.imag, c2.imag), max(c1.imag, c2.imag)))
        elif isinstance(piece, tuple):
            value = _synth_scalar(rng, piece, specials=specials)
            if dom.base_type in ("Z", "N"):
                value = int(round(value))
                if dom.base_type == "N":
                    value = abs(value)
        else:
            value = _sample_bare_named_set(rng, piece)
        if value not in dom.excluded:
            return value
    return value


def _classify_bound(bounds) -> str:
    """The domain-bound shape, independent of a parameter's own
    inferred kind, "domain" (a grammar.Domain: union/exclusion/an
    explicit type refinement), "frozenset" (a discrete set), "Z"/"N"
    (a named integer set), "interval" (a plain (lo, hi) tuple), or
    "none". Shared by every consumer that needs to dispatch on a
    bound's own shape (_synth's own sampling, _sampling_shorthand's
    rendering, ...) so a new bound shape only needs teaching to one
    place; the real gap that let _sampling_shorthand crash on a
    Domain object _synth already knew how to handle, the first time a
    claim's own richer domain bound reached it."""
    if isinstance(bounds, Domain):
        return "domain"
    if isinstance(bounds, frozenset):
        return "frozenset"
    if bounds == "Z":
        return "Z"
    if bounds == "N":
        return "N"
    if bounds == "C":
        return "C"
    if isinstance(bounds, tuple) and len(bounds) == 2:
        return "interval"
    if bounds is None:
        return "none"
    return "other"


def _synth(kind: str, rng: random.Random, bounds=None,
          specials: "_SpecialCycle | None" = None,
          extra: list[float] | None = None,
          extra_cycle: "_SpecialCycle | None" = None,
          length: "int | None" = None):
    # `kind == "sequence"` is checked first, unconditionally, before any
    # bounds-shape dispatch below, a Domain/frozenset/"Z"/"N" bound
    # means something different for a sequence (a per-element domain)
    # than it does for a scalar (the parameter's own domain), so a
    # sequence-typed parameter must never fall into the scalar
    # dispatch below and come back a bare number instead of a list.
    if kind == "dict":
        # a mapping parameter with no key list to hand (the automatic
        # type-probes): a generic dict, enough not to crash a function
        # that only iterates its values. The claim path uses
        # `_synth_dict(keys, ...)` with the body's real keys instead.
        return _synth_dict([], rng, specials=specials)
    if kind == "sequence":
        # `length`, when a dimension premise fixed it for this trial,
        # overrides the free 2..8 draw so the premise holds by
        # construction rather than by rejection
        n = length if length is not None else rng.randint(2, 8)
        if bounds is not None:
            # a declared element domain, generate elements that
            # respect it (recursing through _synth's own scalar
            # dispatch below, so a Domain/frozenset/"Z"/"N"/plain
            # Interval bound is handled exactly the same way it already
            # is for a scalar parameter with the same bounds) rather
            # than the unconstrained variety below, which would
            # routinely generate an out-of-domain element and fail the
            # very first smoke-test call against a function that
            # correctly validates its own declared domain.
            return [_synth("float", rng, bounds, specials=specials) for _ in range(n)]
        if rng.random() < 0.3:
            shape = rng.choice(["constant", "sorted", "reversed", "with-zero", "extreme"])
            if shape == "constant":
                v = _synth_scalar(rng, specials=specials)
                return [v] * n
            if shape == "sorted":
                return sorted(rng.uniform(-10, 10) for _ in range(n))
            if shape == "reversed":
                return sorted((rng.uniform(-10, 10) for _ in range(n)), reverse=True)
            if shape == "with-zero":
                xs = [rng.uniform(-10, 10) for _ in range(n)]
                xs[rng.randrange(n)] = 0.0
                return xs
            return [rng.choice([1e6, -1e6, 1e-9, 0.0])] + \
                   [rng.uniform(-10, 10) for _ in range(n - 1)]
        return [rng.uniform(-10, 10) for _ in range(n)]
    # set-membership domain values (grammar.py's split_quantifier): a
    # frozenset samples one of its own elements regardless of kind; "Z"/
    # "N" override the sampling strategy to signed/unsigned integers,
    # regardless of the parameter's own inferred kind; a Domain (union/
    # exclusion/explicit type refinement) is handled the same way, by
    # its own dedicated sampler, also regardless of kind.
    bound_shape = _classify_bound(bounds)
    if bound_shape == "domain":
        return _sample_domain(rng, bounds, specials=specials)
    if bound_shape == "frozenset":
        return rng.choice(list(bounds))
    if bound_shape in ("Z", "N", "C"):
        return _sample_bare_named_set(rng, bound_shape)
    if kind == "bool":
        return rng.random() < 0.5
    if kind == "int":
        if bounds is not None:
            lo, hi = _finite_bounds(*bounds)
            return rng.randint(int(lo), int(hi))
        return rng.choice([0, 1, 2]) if rng.random() < 0.3 else rng.randint(0, 10)
    return _synth_scalar(rng, bounds, specials=specials, extra=extra, extra_cycle=extra_cycle)


def _fmt_value(v) -> str:
    """One computed or sampled value, legibly, shared by _fmt() (an
    argument tuple) and every check closure's own failure `detail`
    string (the actual result(s) being compared, not just the inputs
    that produced them)."""
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, complex):
        # the claim grammar's own coordinate spelling (a+bj), never
        # Python's parenthesized repr
        return f"{v.real:.6g}{v.imag:+.6g}j"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_value(x) for x in v) + "]"
    if isinstance(v, tuple):
        return "(" + ", ".join(_fmt_value(x) for x in v) + ")"
    return repr(v)


def _fmt(args: tuple, names: tuple[str, ...] | None = None) -> str:
    """A counterexample's argument tuple, legible on its own: labeled
    `name=value` pairs when the caller's own parameter names are known,
    a bare positional tuple otherwise. Unlabeled, a two-element
    counterexample like `([...], -5.54)` reads as (input, output);
    it's actually (x, alpha), both inputs."""
    if names is not None and len(names) == len(args):
        return ", ".join(f"{n}={_fmt_value(a)}" for n, a in zip(names, args))
    return "(" + ", ".join(_fmt_value(a) for a in args) + ")"


def _sampling_shorthand(kinds: dict, domain: dict, n: int,
                        critical_hints: dict[str, list[float]] | None = None,
                        truncated_hints: "set[str] | None" = None) -> str:
    """How a probe actually sampled, in compact mathematical notation: the
    distribution per parameter, the seed, the trial count. Meant to make a
    `holds (n=...)` verdict legible and reproducible from the record alone,
    not just from reading probing.py's source.

    `critical_hints`, when a parameter has any, appends a `⊕crit{...}`
    marker naming the analytically-discovered points folded into that
    parameter's own sampling (see `_points_for_probe`). Never changes
    the verdict itself, still `holds`/`falsified`; this only makes the
    evidence behind it more understandable. `truncated_hints` names any
    parameter whose own discovered-point count was capped (see
    `_hints_from_points`'s own `max_critical_hints_per_param`), appending
    `[truncated@N]` so a reader knows `n` covers a capped hint pool plus
    ordinary sampling, not every point that was actually found."""
    critical_hints = critical_hints or {}
    truncated_hints = truncated_hints or set()

    def crit_suffix(p: str) -> str:
        hints = critical_hints.get(p)
        if not hints:
            return ""
        trunc = f"[truncated@{len(hints)}]" if p in truncated_hints else ""
        return "⊕crit{" + ", ".join(f"{v:g}" for v in hints) + "}" + trunc

    parts = []
    for p, k in kinds.items():
        bounds = domain.get(p) if k != "sequence" else None
        bound_shape = _classify_bound(bounds)
        if bound_shape == "frozenset":
            parts.append(f"{p}~U{{{', '.join(str(v) for v in sorted(bounds))}}}")
        elif bound_shape == "Z":
            parts.append(f"{p}~{{0,±1,±2}}[p=.3]⊔U{{-1000..1000}}")
        elif bound_shape == "N":
            parts.append(f"{p}~{{0,1,2}}[p=.3]⊔U{{0..1000}}")
        elif k == "sequence":
            parts.append(f"{p}~Seq(len∈[2,8]; shape∈{{U,const,sorted,rev,+0,extreme}}[p=.3])")
        elif k == "int" and (bounds is None or isinstance(bounds, tuple)):
            # only a plain (lo, hi) tuple/Interval is subscriptable; a
            # Domain-typed bound (a `⊂ Z` refinement) falls through to
            # the set-notation rendering below, subscripting it blind
            # was a real crash on the empirical-fallback path
            parts.append(f"{p}~U{{{int(bounds[0])}..{int(bounds[1])}}}" if bounds
                         else f"{p}~{{0,1,2}}[p=.3]⊔U{{0..10}}")
        elif bound_shape == "interval":
            lo, hi = bounds
            parts.append(f"{p}~U({lo:g},{hi:g})⊔{{lo,hi,mid,±ε}}[p=.3]{crit_suffix(p)}")
        elif bound_shape != "none":
            # "domain" (grammar.Domain: union/exclusion/an explicit
            # type refinement) or "other", a richer shape this
            # function's own compact notation has no bespoke rendering
            # for. Fall back to the same canonical set-notation text a
            # person would type for it, rather than assuming every
            # non-plain-tuple bound is a (lo, hi) pair, the real gap
            # that used to crash here on a Domain object _synth already
            # knew how to handle.
            from .grammar import render_domain_bound
            parts.append(f"{p}~{render_domain_bound(bounds)}{crit_suffix(p)}")
        else:
            parts.append(f"{p}~U(-10,10)⊔{{0,±1,±.5,2,±1e-9,±1e6}}[p=.3]{crit_suffix(p)}")
    return ", ".join(parts) + f", seed={_RNG_SEED}, n={n}"


def _out_of_domain_candidates(bounds) -> list:
    """Concrete values provably *not* in `bounds`, worth injecting as
    one sequence element to test whether the real function rejects
    them, the `domain_enforced[...]` prober's own generalization of
    "just past each boundary" to every domain shape this module now
    supports (a plain `Interval`, or a `Domain` with exclusion/union/an
    explicit type refinement), not only a bare interval. A `Domain`
    that explicitly excludes `MISSING` also contributes a NaN
    candidate; that's a real, declared fact worth testing the real
    function against now, not just a numeric range."""
    if isinstance(bounds, tuple):
        lo, hi = bounds
        span = (hi - lo) or 1.0
        return [lo - 0.5 * span, hi + 0.5 * span]
    if isinstance(bounds, Domain):
        candidates = []
        for piece in bounds.pieces:
            if isinstance(piece, tuple):
                lo, hi = piece
                span = (hi - lo) or 1.0
                candidates += [lo - 0.5 * span, hi + 0.5 * span]
        if MISSING in bounds.excluded:
            candidates.append(float("nan"))
        return [c for c in candidates if not domain_contains(c, bounds)]
    return []


def _pole_safety(bounds, poles: list[dict]) -> tuple[str, list[str]]:
    """Intent:
        Does bounds (a plain (lo, hi) interval) provably exclude every
        pole in poles; "falsified" (at least one pole is provably
        inside), "undecided" (a pole's location couldn't be fully
        evaluated), or "proven" (every pole provably falls outside).

    Notes:
        Shared by is_pole_safe's own derive route and
        suggest_claims()'s is_numerically_stable derive route, the same
        pole-vs-declared-domain containment reasoning, computed once.
        contained is the list of pole locations (as their own text,
        e.g. "-1") found inside bounds, empty when the verdict isn't
        "falsified". A `diagnostics._integer_pole_hazards()`-produced
        hazard (`"at": "non-positive integers"`, gamma/loggamma's own
        infinite pole class) is decided via `_nonpositive_integer_in`
        instead of sympy root evaluation; there's no single root to
        sympify at all.
    """
    from .grammar import domain_contains
    contained, undecided = [], False
    for h in poles:
        if h["at"] == "non-positive integers":
            k = _nonpositive_integer_in(bounds)
            if k is None:
                undecided = True
            elif k is not False:
                contained.append(str(k))
            continue
        try:
            root = sympy.sympify(h["at"])
        except Exception:
            undecided = True
            continue
        if root.free_symbols:
            undecided = True   # coupled to another variable, out of scope
            continue
        if root.is_real is False:
            continue           # a non-real pole is never reachable by a real domain
        try:
            root_f = float(root)
        except Exception:
            undecided = True
            continue
        if domain_contains(root_f, bounds):
            contained.append(h["at"])
    if contained:
        return "falsified", contained
    if undecided:
        return "undecided", contained
    return "proven", contained


def _nonpositive_integer_in(bounds):
    """A concrete non-positive integer bounds provably contains (as a
    real `int`), `False` when bounds provably contains none, or `None`
    when this can't be decided for bounds' own shape, a full `Domain`
    object (pieces/exclusions/base_type together) isn't attempted here,
    conservatively undecided rather than guessed at."""
    if bounds in ("N", "Z"):
        return 0   # both include 0, itself a real pole
    if isinstance(bounds, frozenset):
        for v in bounds:
            try:
                v_f = float(v)
            except (TypeError, ValueError):
                return None
            if v_f <= 0 and v_f.is_integer():
                return int(v_f)
        return False
    if isinstance(bounds, tuple):
        try:
            lo, hi = float(bounds[0]), float(bounds[1])
        except (TypeError, ValueError):
            return None
        k = min(math.floor(hi), 0)
        return int(k) if k >= math.ceil(lo) else False
    return None


def _poles_by_var(points: list[dict]) -> dict[str, list[dict]]:
    poles_by_var: dict[str, list[dict]] = {}
    for pt in points:
        if pt["kind"] == "pole":
            poles_by_var.setdefault(pt["variable"], []).append(pt)
    return poles_by_var




@dataclass
class SamplingSetup:
    """Everything one sampling pass needs, prepared once and passed
    whole, the named replacement for a 9-tuple that used to be
    destructured positionally (three different ways) at every call
    site. See `_prepare_sampling` for how each field is decided."""
    rng: random.Random
    specials: _SpecialCycle
    risk: dict
    budget: int
    points: list
    critical_hints: dict
    truncated_hints: set
    extra_cycles: dict
    route: str
    # "probe" or "probe:semi_analytical", the route value the evidence
    # honestly earns, per record-schema.md's open route field.


def _prepare_sampling(fn, facts, domain: dict, trials: int | None,
                      trials_scale: float, extensive: bool) -> "SamplingSetup":
    """One shared sampling setup: seeded RNG, adaptive trial budget,
    and critical-point hints, in the same three-way shape everywhere
    a real callable gets sampled, not reimplemented per caller:

    - `extensive=True`: the full derive chain (fold/dot/sum-lifted,
      branch-pruned) informs sampling, whether or not fn lifts directly.
    - `extensive=False` but fn lifts directly ("lifts easily"):
      critical points come from that direct lift, cheaply.
    - Not liftable at all (even under the extensive attempt):
      `_points_for_probe` degrades to `[]`, so sampling falls back to
      the plain special-value/uniform pool with no hints, the route
      this produces is correctly plain "probe", not "probe:semi_analytical".

    Both `probe()`'s own structural checks (domain_enforced) and
    `check_conjectures()`'s claim adjudication call this, so a claim
    gets the exact same pole/stationary-point-aware sampling and the
    exact same structural-risk-based budget a built-in law always had,
    not a separately (and more weakly) sampled one.

    Returns `(rng, specials, risk, budget, points, critical_hints,
    truncated_hints, extra_cycles, route_value)`. `truncated_hints`
    names any parameter whose own discovered-point count exceeded
    `_RiskPolicy.max_critical_hints_per_param` (see `_hints_from_points`),
    so a caller can say so in the reported evidence rather than
    truncating silently, empty in practice today, since a search slow
    enough to discover that many points times out under
    `_points_for_probe`'s own wall-clock cap well before returning."""
    rng = random.Random(_RNG_SEED)
    specials = _SpecialCycle(rng)
    risk = _structural_risk(facts, domain)
    budget = trials if trials is not None else _starting_budget(risk, _affine_hint(fn, facts))
    points = _points_for_probe(fn, facts, domain, extensive)
    critical_hints, truncated_hints = _hints_from_points(points)
    # the route subroute below keys on ANALYTICAL discoveries about
    # this function; hazard-channel values (the decade sweep, stub
    # boundaries) widen the sampling but never relabel its mechanism
    analytical = bool(critical_hints)
    for param, values in _hazard_hint_values(fn, facts, domain).items():
        critical_hints.setdefault(param, []).extend(values)
    # kept per-parameter, not merged into the shared `specials` pool, so
    # one parameter's own pole never gets attributed to another's
    # sampling. Built regardless of whether a domain is declared for
    # this parameter, _synth_scalar's own guaranteed-lap check skips
    # an out-of-bounds hint rather than needing this to pre-filter.
    extra_cycles = {p: _SpecialCycle(rng, values=critical_hints[p])
                    for p in facts.params if p in critical_hints}
    scale = min(1.0, trials_scale)
    if scale < 1.0:
        budget = max(_RISK.min_trials_floor_when_scaled, len(_SPECIALS),
                     round(budget * scale))
    # record-schema.md's own `route` field: "probe:semi_analytical"
    # states plainly that at least one parameter's own sampling was
    # informed by an analytically discovered critical point this run,
    # not blind trial-and-error.
    route_value = "probe:semi_analytical" if analytical else "probe"
    return SamplingSetup(rng=rng, specials=specials, risk=risk, budget=budget,
                         points=points, critical_hints=critical_hints,
                         truncated_hints=truncated_hints,
                         extra_cycles=extra_cycles, route=route_value)


def probe(fn, facts, domain: dict | None = None,
          trials: int | None = None, trials_scale: float = 1.0,
          extensive: bool = False) -> list[Probe]:
    """Empirical evidence. `domain` maps parameter names to (lo, hi) limits:
    algebraic probes sample *inside* the declared domain (claims are
    adjudicated where they are claimed). Whether the code REJECTS
    out-of-domain input is the declared excluded_outside_domain claim's
    question, not a synthesized probe here.

    `trials_scale` shrinks the trial budget, `trials` included, not
    just the adaptive default, by a flat factor: a dev-loop knob
    (`mathema check --trials-scale 0.25`, say) for faster iteration,
    not a per-function tuning tool. Only ever shrinks (clamped to
    (0, 1]); a structurally riskier function already gets more trials
    on its own (see _starting_budget), so scaling upward here would
    just be working against that signal rather than adding a new one.
    Floored at `max(_RiskPolicy.min_trials_floor_when_scaled,
    len(_SPECIALS))` regardless of how small the scale is: below
    `len(_SPECIALS)`, _SpecialCycle's own guaranteed sweep couldn't
    finish even once, and below roughly a dozen trials a `holds`
    verdict stops being real evidence of anything, a dev-speed
    convenience is not worth reporting that as if it still were.

    `extensive=True` widens the critical-point analysis behind the
    sampling hints to also consider a fold/dot/sum-lifted function
    (`domain_safe[...]`'s own pole-avoidance reasoning moved to
    `is_pole_safe[param]`, suggested via `suggest_claims()` rather than
    run unconditionally here). This can make a partially-liftable
    function's own sampling genuinely hybrid: part symbolic, part
    empirical, not just the same analysis run slower. See
    `_points_for_probe`'s own docstring for the full explanation. Real,
    opt-in cost; default `False` keeps today's cheap, direct-lift-only
    behavior."""
    if facts.is_pure is False:
        # False is established impurity; None means purity could not
        # be analysed at all (no source), which is not a statement
        # that effects exist, so probing proceeds against the live
        # callable as it always did for doc-only records
        return [Probe("purity", "", "skipped",
                      note="function has effects; algebraic probing not "
                           "meaningful"
                           + (": " + "; ".join(facts.effects)
                              if facts.effects else ""))]
    kinds = [facts.param_kinds.get(p, "unknown") for p in facts.params]
    if not kinds:
        return []
    # the call the battery attempts, stated as the `callable` row's
    # statement; why it could not be made rides in the row's note
    callable_statement = f"f({', '.join(facts.params)}) can be called"
    domain = dict(domain or {})
    # a Literal[...]/Enum annotation already states the parameter's
    # entire value set, seed it as that parameter's domain (a stated
    # domain always wins over the inference)
    for p, vals in getattr(facts, "finite_domains", {}).items():
        domain.setdefault(p, frozenset(vals))
    # a string parameter with no finite domain has no honest sampling
    # story: synthesizing a float and watching the function raise would
    # manufacture a gap that is an artefact of the battery, not a fact
    # about the code, decline, naming the parameter and the spelling
    # that fixes it
    for p, k in zip(facts.params, kinds):
        if k == "string" and _classify_bound(domain.get(p)) not in (
                "frozenset", "domain"):
            return [Probe(
                "callable", callable_statement, "skipped",
                note=f"parameter {p!r} is a string with no declared "
                     f"domain; declare its values, e.g. 'for {p} in "
                     f'{{"a", "b"}}, ...\' in a claim, or annotate it '
                     f"Literal[...]",
                meta={"mathema.probe_gap": "string-domain-missing"})]
    # budget/risk/route_value aren't needed here, domain_enforced below
    # is the only law left in this function (everything else migrated to
    # claims, see suggest_claims()), and it reports its own fixed route
    # rather than a sampling-informed one.
    setup = _prepare_sampling(fn, facts, domain, trials, trials_scale, extensive)
    rng, specials = setup.rng, setup.specials
    critical_hints, extra_cycles = setup.critical_hints, setup.extra_cycles

    def args_for() -> tuple:
        out = []
        for p, k in zip(facts.params, kinds):
            out.append(_synth(k, rng, domain.get(p), specials=specials,
                              extra=critical_hints.get(p), extra_cycle=extra_cycles.get(p)))
        return tuple(out)

    # A parameter's own critical-point hint is drawn deterministically
    # exactly once (extra_cycle's own guaranteed lap), which may be
    # this very first call; retrying a few times tells a genuine
    # signature mismatch (fails identically every time) apart from a
    # one-off arithmetic exception from landing exactly on a pole.
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            fn(*args_for())
            break
        except Exception as e:
            last_exc = e
    else:
        return [Probe("callable", callable_statement, "skipped",
                      note="could not synthesize valid inputs from the "
                           f"signature ({type(last_exc).__name__}: {last_exc})",
                      meta={"mathema.probe_gap": "input-synthesis"})]

    probes: list[Probe] = []

    # deterministic/is_numerically_stable/commutative/associative/even/odd/
    # idempotent/monotone/bounded/permutation_invariant/scale_equivariant/
    # translation_equivariant used to live here as their own hardcoded,
    # probe-only checks. They're now claims suggest_claims() proposes
    # (see its own docstring), adjudicated through check_conjectures()
    # so a liftable function gets a symbolic proof instead of only
    # probing, wherever a proof is possible. "monotone" specifically was
    # dropped rather than migrated: suggest_claims()'s own
    # monotonic_increasing[p]/monotonic_decreasing[p] (derivative sign,
    # not two random points) already covers the same question more
    # precisely. domain_enforced itself is retired too: out-of-domain
    # rejection is now the DECLARED excluded_outside_domain claim (the
    # SafetyFamily member in claim_families), opted into explicitly or
    # auto-declared by @enforce_domain, never synthesized behind a
    # mode flag. _out_of_domain_candidates below is its trial source.

    return probes
