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
import collections
import dataclasses
import math
import random
from dataclasses import dataclass

import sympy

from ._sampling import (
    _RNG_SEED as _RNG_SEED, _SPECIALS as _SPECIALS,
    _SpecialCycle as _SpecialCycle, _finite_bounds as _finite_bounds,
    _synth_scalar as _synth_scalar,
)
from ._sampling import _moderate_bounds, _reach_ends
from .grammar import MISSING, Domain, domain_contains
from .domain import _sentinel_piece, numeric_excluded
from .runtime_types import SEQUENCE_KINDS
# Probe's real home is records.py (the stdlib-only leaf every layer can
# import); re-exported here because probing is where consumers
# historically found it.
from .records import Probe as Probe
from ._signatures import callable_signature


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
    max_language_risk: int = 3
    language_hazards_per_unit: int = 32   # hazards one unit of language risk stands for
    wide_span: float = 1e4
    tiny_magnitude: float = 1e-6
    huge_magnitude: float = 1e9
    branch_penalty: float = 1.0
    loop_penalty: float = 1.5
    param_penalty: float = 0.5
    wide_domain_penalty: float = 1.0
    float_extreme_penalty: float = 1.0
    language_penalty: float = 1.0
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
    large or very near-zero magnitudes). `language` counts the hazards
    a language-bound parameter's language brings, one unit per
    `language_hazards_per_unit`, and is present only when some
    parameter is bound to a language."""
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
    risk = {
        "branches": min(facts.branch_count, policy.max_branch_risk),
        "loops": min(len(facts.loops), policy.max_loop_risk),
        "params": max(0, len(facts.params) - policy.free_params),
        "wide_domain": min(wide_domain, policy.max_wide_domain_risk),
        "float_extremes": min(float_extremes, policy.max_float_extreme_risk),
    }
    language = _language_risk(facts.params, domain, policy)
    if language is not None:
        risk["language"] = language
    return risk


def _language_risk(params, domain: dict, policy: _RiskPolicy = _RISK) -> "int | None":
    """Intent:
        The `language` risk factor: for each parameter bound to a
        language, one unit per `language_hazards_per_unit` hazards its
        lap visits, summed and capped at `max_language_risk`. `None`
        when no parameter is bound to a language.
    """
    units, bound = 0, False
    for p in params:
        dom = domain.get(p)
        if _classify_bound(dom) != "language":
            continue
        bound = True
        units += math.ceil(len(_language_hazards(dom)) / policy.language_hazards_per_unit)
    return min(units, policy.max_language_risk) if bound else None


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
    overriding that, and the same holds for a language domain's hazards
    (`risk["language"]`)."""
    if affine and risk["wide_domain"] == 0 and risk["float_extremes"] == 0 \
            and not risk.get("language"):
        return policy.affine_budget
    complexity = (risk["branches"] + risk["loops"] + risk["wide_domain"]
                  + risk.get("language", 0))
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
    score -= risk.get("language", 0) * policy.language_penalty
    # centered on _N_BASE, not linear: doubling n from there is worth a
    # flat +1, same as halving it costs a flat -1, extra trials past a
    # point buy steadily less legibility, not steadily less risk.
    score += math.log2(max(n_trials, 1) / _N_BASE)
    score = max(policy.score_min, min(policy.score_max, score))
    stars = max(1, min(_PROBE_MAX_STARS, round(score / 2.5)))
    return {"score": round(score, 1), "stars": stars, "max_stars": 5,
           "n": n_trials, "factors": dict(risk)}


# the relative half of the default closeness allowance: with no declared
# tolerance, two values are equal when they agree within this relative
# tolerance or the absolute 1e-9, whichever is larger
DEFAULT_RELATIVE_TOLERANCE = 1e-6


def plain_value(v):
    """Intent:
        An executed value in the plain Python form the comparisons
        read: a numpy scalar or a 0-d array becomes its Python number,
        an array becomes nested lists, anything else is returned as it
        is.
    """
    if type(v) in (bool, int, float, complex, str, type(None)):
        return v
    if hasattr(v, "shape") and hasattr(v, "tolist"):
        try:
            return v.tolist()
        except Exception:
            return v
    if hasattr(v, "dtype") and hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _is_number(v) -> bool:
    return isinstance(v, (int, float, complex)) and not isinstance(v, bool)


def _numbers_agree(u, v, abs_tol: float, rel_tol: float) -> bool:
    # a NaN agrees with nothing; the same infinity is one point; a
    # finite value is close within the tolerances, complex values by
    # abs(u - v)
    if holds_nan(u) or holds_nan(v):
        return False
    if holds_inf(u) or holds_inf(v):
        return u == v
    if isinstance(u, complex) or isinstance(v, complex):
        return cmath.isclose(u, v, rel_tol=rel_tol, abs_tol=abs_tol)
    return math.isclose(u, v, rel_tol=rel_tol, abs_tol=abs_tol)


def values_agree(u, v, tolerance: float | None = None,
                 rel_tol: float = DEFAULT_RELATIVE_TOLERANCE,
                 broadcast: bool = False) -> "bool | None":
    """Intent:
        Whether two executed values are equal, the one reading every
        comparison shares: Python numbers, numpy scalars, 0-d arrays,
        arrays and nested lists alike, arrays and lists compared
        element by element. A NaN agrees with nothing, another NaN
        included; two sides at the same infinity agree; complex values
        compare by `abs(u - v)`; finite values agree within `tolerance`
        (absolute, 1e-9 when None) or `rel_tol` (relative), whichever
        is larger.

    Notes:
        `None` when the two sides have different shapes. With
        `broadcast`, a number against an array or list is compared
        with every element. A bool, and a value that is not a number,
        agrees only by exact equality.
    """
    abs_tol = tolerance if tolerance is not None else 1e-9
    u, v = plain_value(u), plain_value(v)

    def walk(x, y):
        xs, ys = isinstance(x, (list, tuple)), isinstance(y, (list, tuple))
        if xs and ys:
            if len(x) != len(y):
                return None
            parts = [walk(a, b) for a, b in zip(x, y)]
        elif xs or ys:
            if not broadcast:
                return None
            parts = ([walk(a, y) for a in x] if xs
                     else [walk(x, b) for b in y])
        elif _is_number(x) and _is_number(y):
            return _numbers_agree(x, y, abs_tol, rel_tol)
        else:
            try:
                return bool(x == y)
            except Exception:
                return False
        if any(pt is None for pt in parts):
            return None
        return all(parts)

    return walk(u, v)


def _close(u, v, tolerance: float | None = None,
           rel_tol: float = DEFAULT_RELATIVE_TOLERANCE) -> bool:
    """`tolerance` overrides the default abs_tol, a claim's own declared
    tolerance (declared-schema.md) governs its own comparison outright;
    the 1e-9 default is only a floating-point-representation fudge factor
    for claims that never declared one. `rel_tol` is the relative
    allowance on top of it, 0 for a claim that declared its tolerance.
    The reading is `values_agree`'s: a NaN is close to nothing, and two
    values of different shapes are not close."""
    return bool(values_agree(u, v, tolerance, rel_tol))


def values_differ(u, v, tolerance: float | None = None,
                  rel_tol: float = DEFAULT_RELATIVE_TOLERANCE) -> bool:
    """Intent:
        Whether `u != v` holds between two executed values: they do not
        agree (`values_agree`), and neither holds a NaN, since a NaN is
        no value and fails every relation, `!=` included.
    """
    if holds_nan(plain_value(u)) or holds_nan(plain_value(v)):
        return False
    return not values_agree(u, v, tolerance, rel_tol)


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
                     exact_inequality: bool = False,
                     rel_tol: float = DEFAULT_RELATIVE_TOLERANCE):
    """One scalar comparison for the elementwise walk. A strict `<`/`>`
    gets no tolerance credit; a closed `<=`/`>=` gets the slack; `==`/
    `~=` go through `_close`, and so does `!=` when the claim declared a
    tolerance. With `exact_inequality`, `!=` fails only where the two
    values are equal, so a representation tolerance never makes two
    different values a counterexample. Raises TypeError for values that
    do not order (a complex vs a real), which the caller reads as
    'unanswerable', not 'false'. `rel_tol` is `_close`'s relative
    allowance."""
    if holds_nan(a) or holds_nan(b):
        return False
    if relation in ("==", "~="):
        return _close(a, b, tolerance=slack, rel_tol=rel_tol)
    if relation == "!=":
        if exact_inequality:
            return not (a == b)
        return not _close(a, b, tolerance=slack, rel_tol=rel_tol)
    if relation == "<=":
        return a <= b + slack
    if relation == ">=":
        return a >= b - slack
    if relation == "<":
        return a < b
    return a > b


class ExecutedMissing:
    """What the code did at each missing input a route executed: `table`,
    `{param: {member: outcome}}` with the first outcome per member kept;
    `policy`, the behaviour per (parameter, kind, member) over every
    call (`_missing_policy.PolicyTable`); and how many points were
    classified rather than judged."""

    def __init__(self) -> None:
        from ._missing_policy import PolicyTable
        self.table: dict = {}
        self.said: dict = {}
        # `{param: default}` of the function called, set by the route
        self.defaults: dict = {}
        # the first call per (parameter, member): (value, output, raised,
        # behaviour)
        self.first: dict = {}
        # the first point where a declared `Optional` return gave None
        # from present inputs: `{"at": "x = 0.75", "declared": text}`
        self.introduced: dict = {}
        self.policy = PolicyTable()
        self.classified = 0
        self.last_classified = False

    def add_call(self, point: dict, output=None, raised: "str | None" = None) -> None:
        """File one call at `point` (its arguments by name) that returned
        `output` or raised `raised`."""
        from ._missing_policy import (classify_call, keys_of, member_changes,
                                      no_value_slots)
        from ._missing_words import outcome_entry, said, value_shown
        # a parameter left at its own default (numpy's `axis=None`) is no
        # missing input
        point = {p: v for p, v in point.items()
                 if not (p in self.defaults and v is self.defaults[p])}
        keys = keys_of(point)
        if not keys:
            return
        behaviour = classify_call(point, output, raised)
        # a hole returned in its slot spelled as another member is said
        # slot by slot: `values[1]=None returned as nan`
        respelled: dict = {}
        if raised is None:
            for p, position, drawn, back in member_changes(point, output):
                where = "".join(f"[{i}]" for i in position)
                word = next(sl.member for sl in no_value_slots(point[p]).slots
                            if sl.position == position)
                shown = "None" if drawn is None else value_shown(drawn)
                respelled.setdefault((p, word),
                                     f"{p}{where}={shown} returned as {back}")
        from .policy import record_call
        record_call(point, output, raised)
        for p, _kind, member in keys:
            in_slot = no_value_slots(point[p]).shape != ()
            entry = (outcome_entry(member, raised=raised) if raised is not None
                     else outcome_entry(member, output, behaviour=behaviour,
                                        respelled=respelled.get((p, member)),
                                        in_slot=in_slot))
            self.table.setdefault(p, {}).setdefault(member, entry)
            self.said.setdefault(p, {}).setdefault(
                member, said(p, member, {p: point[p]}, output, raised, behaviour))
            self.first.setdefault((p, member), (point[p], output, raised, behaviour))
        self.policy.add(point, output, raised)

    def returned_absent(self, point: dict, declared: str) -> None:
        """File a None the function returned from present inputs, which
        its return type declares."""
        from ._missing_words import point_shown
        self.introduced = self.introduced or {"at": point_shown(point),
                                              "declared": declared}
        self.classified += 1
        self.last_classified = True

    def meta(self) -> dict:
        out: dict = {}
        if self.introduced:
            out["returned"] = {"absent": "introduces", "source": "annotation",
                               **self.introduced}
        if self.table:
            out["executed"] = {p: dict(v) for p, v in self.table.items()}
            out["behaviour"] = self.policy.summary()
            out["said"] = {p: dict(v) for p, v in self.said.items()}
            mixed = self.policy.mixed()
            if mixed:
                out["mixed"] = mixed
        return out


class LastCall:
    """The calls a wrapped function made since the last `record`, for the
    executed missing inputs: `wrap(fn)` returns fn recording each
    outcome."""

    def __init__(self) -> None:
        self.calls: list = []

    def wrap(self, fn):
        def recorded(*a, **k):
            try:
                out = fn(*a, **k)
            except Exception as exc:
                self.calls.append(("raised", type(exc).__name__))
                raise
            self.calls.append(("returned", out))
            return out
        return recorded

    def reset(self) -> None:
        self.calls = []

    def raised(self) -> bool:
        return any(kind == "raised" for kind, _ in self.calls)

    def outputs(self) -> list:
        return [v for kind, v in self.calls if kind == "returned"]

    def record(self, executed: "ExecutedMissing", point: dict) -> None:
        """File every call since the last record at `point`, then forget
        them."""
        if inputs_missing(point.values()):
            for kind, value in self.calls:
                if kind == "raised":
                    executed.add_call(point, raised=value)
                else:
                    executed.add_call(point, output=value)
        self.calls = []


def signature_defaults(fn) -> dict:
    """`{param: default}` for every parameter of `fn` that has one."""
    import inspect

    from ._signatures import callable_signature
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return {}
    return {p: q.default for p, q in sig.parameters.items()
            if q.default is not inspect.Parameter.empty}


def executed_missing(kit: dict) -> "ExecutedMissing | None":
    """The executed missing inputs a point-runtime kit's `evaluate`
    records, when it has them (a foreign runner's evaluator need not)."""
    return getattr(kit.get("evaluate"), "executed", None)


def with_executed(meta: "dict | None", executed: "ExecutedMissing | None") -> "dict | None":
    """`meta` with the outcomes and behaviours at the executed missing
    inputs merged under `mathema.missing`; `meta` unchanged when there
    are none."""
    extra = executed.meta() if executed is not None else {}
    if not extra:
        return meta
    out = dict(meta or {})
    missing = dict(out.get("mathema.missing") or {})
    if extra.get("returned") and "returned" not in missing:
        missing["returned"] = extra["returned"]
    for key in ("executed", "behaviour", "said", "mixed"):
        merged = {p: dict(v) for p, v in (missing.get(key) or {}).items()}
        for p, members in extra.get(key, {}).items():
            for word, said in members.items():
                merged.setdefault(p, {}).setdefault(word, said)
        if merged:
            missing[key] = merged
    out["mathema.missing"] = missing
    return out


def missing_class(value) -> "str | None":
    """Intent:
        The kind of missing value `value` is: `"absent"` for `None`,
        `"hole"` for a value with no computable content (NaN, `pd.NA`,
        `NaT`, a hole a runtime type's adapter reads back), None for a
        value that is not missing. A container is not itself a missing
        value, whatever it holds.
    """
    from .domain import absence_word, is_missing
    if absence_word(value) is not None:
        return "absent"
    if isinstance(value, (list, tuple, dict, str)) or _is_matrix_value(value):
        return None
    try:
        return "hole" if is_missing(value) else None
    except Exception:
        return None


def inputs_missing(args) -> bool:
    """Intent:
        Whether any argument is missing or holds a missing value: `None`,
        a hole, or a vector, matrix, table or record holding one (read
        through the runtime type adapters' `observe`).
    """
    from .runtime_types import observed_plain

    def holds(v) -> bool:
        if missing_class(v) is not None:
            return True
        if isinstance(v, dict):
            return any(holds(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return any(holds(x) for x in v)
        if _is_matrix_value(v) or type(v).__module__.split(".")[0] in ("pandas",
                                                                       "polars"):
            try:
                seen = observed_plain(v)
            except Exception:
                return False
            return seen is not v and holds(seen)
        return False

    return any(holds(a) for a in args)


def classified(args, outputs, raised: bool = False) -> bool:
    """Intent:
        Whether a point is classified rather than judged: an argument is
        missing, and the call raised or returned a missing value (a
        hole or `None`, or a container holding one). A value claim is
        judged only where the function returns a value; the behaviour
        at a missing output is recorded, never compared.
    """
    return inputs_missing(args) and (
        raised or any(inputs_missing([o]) for o in outputs))


def _is_matrix_value(v) -> bool:
    """Whether a value is matrix/array-valued (a nested sequence or a
    numpy array), so a relation over it is compared elementwise."""
    if isinstance(v, (list, tuple)):
        return True
    return hasattr(v, "shape") and hasattr(v, "__array__")


def _pinned_float_env():
    """The floating-point error regime every probe evaluation runs
    under: numpy's own defaults, pinned explicitly so a verdict never
    depends on whatever ambient `numpy.seterr` state the calling
    process happens to carry (an invalid operation is a NaN, never a
    FloatingPointError), with the RuntimeWarning numpy emits for it
    silenced (`quiet_callee_warnings`). Without numpy, only the
    silencing."""
    import contextlib
    stack = contextlib.ExitStack()
    stack.enter_context(quiet_callee_warnings())
    try:
        import numpy
    except Exception:
        return stack
    stack.enter_context(numpy.errstate(divide="warn", over="warn",
                                       under="ignore", invalid="warn"))
    return stack


def quiet_callee_warnings():
    """Intent:
        A context in which a RuntimeWarning is not shown: what the code
        under test emits while it is probed (numpy's "invalid value
        encountered", "overflow", "Mean of empty slice") is the value
        being measured, a nan or an inf, and never a message for the
        person running mathema. mathema's own warnings are other
        categories and still show.
    """
    import warnings
    ctx = warnings.catch_warnings()

    class _Quiet:
        def __enter__(self):
            ctx.__enter__()
            warnings.simplefilter("ignore", RuntimeWarning)
            return self

        def __exit__(self, *exc):
            return ctx.__exit__(*exc)
    return _Quiet()


def quiet_while_probing(func):
    """Run `func` inside `quiet_callee_warnings`."""
    import functools

    @functools.wraps(func)
    def run(*args, **kwargs):
        with quiet_callee_warnings():
            return func(*args, **kwargs)
    return run


def _keeps_default(fn, parameter) -> bool:
    """Intent:
        Whether a parameter that has a default, and that no claim
        binds, is passed at its default when the built-in battery
        builds a call, rather than sampled like any other parameter:
        True for a library function (a key of a registered
        `compendium:` file), False for any other function, whose
        defaulted parameters are sampled.

    Notes:
        A claim's own calls follow the same rule
        (`conjecture.call_defaults`). A record built without Python
        source lists only the parameters without defaults
        (`_doc_only_facts`), so its defaulted parameters are never
        passed at all.
    """
    from .compendium import library_key_of
    return (parameter.default is not parameter.empty
            and library_key_of(fn) is not None)


def call_arguments(fn, params, values: dict) -> "tuple[list, dict]":
    """Intent:
        The positional and keyword arguments that call `fn` with
        `values[p]` for every parameter `p` in `params` that `values`
        holds: a keyword-only parameter by keyword, every other one
        positionally, in order, until a parameter is left out (it then
        takes its default), after which each goes by keyword. A
        callable whose signature cannot be read takes every value
        positionally.
    """
    try:
        spec = callable_signature(fn).parameters
    except (TypeError, ValueError):
        spec = {}
    args: list = []
    kwargs: dict = {}
    order = [p for p, param in spec.items()
             if param.kind in (param.POSITIONAL_ONLY,
                               param.POSITIONAL_OR_KEYWORD)]
    gap = False
    for p in params:
        if p not in values:
            continue
        param = spec.get(p)
        if p in order:
            # a positional parameter before this one that no value
            # fills leaves a gap only a keyword can step over
            gap = gap or any(q not in values for q in
                             order[:order.index(p)])
        if param is not None and (param.kind is param.KEYWORD_ONLY
                                  or (gap and param.kind is
                                      param.POSITIONAL_OR_KEYWORD)):
            kwargs[p] = values[p]
        else:
            args.append(values[p])
    return args, kwargs


def holds_nan(value) -> bool:
    """True when a value is a NaN or contains one: a Python or numpy
    float NaN, a complex value with a NaN component, or a NaN element
    of a numpy array or a nested list or tuple. A value that is not numeric at all holds no NaN."""
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return value != value
    if isinstance(value, complex):
        # no value when either component is a NaN
        return value.real != value.real or value.imag != value.imag
    if isinstance(value, (list, tuple)):
        return any(holds_nan(v) for v in value)
    if hasattr(value, "dtype") and hasattr(value, "shape"):
        try:
            import numpy
            arr = numpy.asarray(value)
            if arr.dtype.kind != "c":
                arr = arr.astype(float)
            return bool(numpy.isnan(arr).any())
        except (TypeError, ValueError, ImportError):
            return False
    return False


def holds_inf(value) -> int:
    """Intent:
        The sign of an infinity a value is or contains: 1 for `inf`, -1
        for `-inf` (when both occur, the first found), 0 for none. Reads
        Python and numpy floats, complex values (the real part, then
        the imaginary part), numpy arrays, and nested lists and
        tuples; a value that is not numeric holds no infinity.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, float):
        return (1 if value > 0 else -1) if value in (_INF, -_INF) else 0
    if isinstance(value, complex):
        return holds_inf(value.real) or holds_inf(value.imag)
    if isinstance(value, (list, tuple)):
        for v in value:
            sign = holds_inf(v)
            if sign:
                return sign
        return 0
    if hasattr(value, "dtype") and hasattr(value, "shape"):
        try:
            import numpy
            arr = numpy.asarray(value)
            if arr.dtype.kind == "c":
                arr = numpy.concatenate([arr.real.ravel(), arr.imag.ravel()])
            else:
                arr = arr.astype(float)
            found = arr[numpy.isinf(arr)]
        except (TypeError, ValueError, ImportError):
            return 0
        return (1 if found.flat[0] > 0 else -1) if found.size else 0
    return 0


_INF = float("inf")


def same_infinity(lv, rv) -> bool:
    """Intent:
        Whether two values are the same infinity, inf and inf or -inf
        and -inf: two overflows toward one infinity are the same
        extended-real point, so the computation is consistent there.
        Two complex values are the same point only when both
        components agree, one of them infinite.
        A NaN is the absence of a value and never the same as anything,
        another NaN included; a finite value is not an infinity.
    """
    def sign(v):
        if isinstance(v, bool) or not isinstance(v, float):
            return 0
        return 1 if v == _INF else -1 if v == -_INF else 0
    if isinstance(lv, complex) or isinstance(rv, complex):
        # one point of the plane only when both components agree, an
        # infinite one among them and no NaN in either
        if not all(isinstance(v, (int, float, complex))
                   and not isinstance(v, bool) for v in (lv, rv)):
            return False
        a, b = complex(lv), complex(rv)
        if holds_nan(a) or holds_nan(b) or not holds_inf(a):
            return False
        return a.real == b.real and a.imag == b.imag
    return sign(lv) != 0 and sign(lv) == sign(rv)


def relation_holds_elementwise(lv, rv, relation: str, slack: float,
                               exact_inequality: bool = False,
                               rel_tol: float = DEFAULT_RELATIVE_TOLERANCE):
    """Whether `lv <relation> rv` holds: a scalar comparison, or, when a
    side is matrix/array-valued, the relation at EVERY element (a scalar
    broadcasts against a matrix), numpy values read as the plain values
    they hold (`plain_value`). `==`, `~=` and `!=` over arrays are one
    fact about the whole value (`values_agree`), so `!=` holds when some
    element differs; an ordering holds when it holds at every element. A
    NaN anywhere fails every relation. Returns
    `True`/`False`, or `None` when the comparison is structurally
    meaningless (an ordering over non-orderable values, or mismatched
    shapes), which the caller reads as skip, never falsify.
    `exact_inequality` makes `!=` compare exactly (see
    `_scalar_relation`), and `rel_tol` is the relative allowance `==`
    and a toleranced `!=` get on top of `slack`. A 0-d numpy value (a
    numpy scalar) is a scalar. Over complex values `==`, `~=` and `!=`
    compare by `abs(a - b)`, with the tolerance rules of reals; an
    ordering over a complex value is unanswerable. Two values of
    different lengths or shapes are unequal outright under `==`, `~=`
    and `!=`; an ordering over them is unanswerable. Leaves that are
    not numbers (a record, a string, `None`) are equal only by their
    own equality."""
    lv, rv = plain_value(lv), plain_value(rv)
    if not _is_matrix_value(lv) and not _is_matrix_value(rv):
        try:
            return bool(_scalar_relation(lv, rv, relation, slack,
                                         exact_inequality, rel_tol))
        except TypeError:
            return None
    if relation in ("==", "~=", "!="):
        # equality of two arrays is one fact about every element; a
        # NaN anywhere is no value and fails the relation, `!=` too
        if holds_nan(lv) or holds_nan(rv):
            return False
        exact = relation == "!=" and exact_inequality
        agree = values_agree(lv, rv, 0.0 if exact else slack,
                             0.0 if exact else rel_tol, broadcast=True)
        if agree is None:
            # two values of different shapes are unequal outright
            return relation == "!="
        return agree if relation != "!=" else not agree

    def _walk(x, y):
        # an ordering, at every element: over sequences of different
        # length, or leaves that do not order, it is unanswerable
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
                                             exact_inequality, rel_tol))
            except TypeError:
                return None
        return None if any(pt is None for pt in parts) else all(parts)

    return _walk(lv, rv)


class ComplexResult(ArithmeticError):
    """A complex value returned by a function that a real claim reads as
    real-valued. The claim treats it as a raise: the call has no real
    value at that point. `callee` names the function, `value` is what
    it returned."""

    def __init__(self, callee: str, value):
        super().__init__(f"{callee} returned the complex value "
                         f"{_complex_text(value)}")
        self.callee = callee
        self.value = value


def _complex_text(value) -> str:
    try:
        return _fmt_value(complex(value))
    except (TypeError, ValueError):
        return repr(value)


def is_complex_value(v) -> bool:
    """Whether `v` is a complex number, or a numpy value or array of
    complex dtype."""
    if isinstance(v, complex):
        return True
    return getattr(getattr(v, "dtype", None), "kind", None) == "c"


def _bound_is_complex(bound) -> bool:
    if isinstance(bound, str):
        return bound == "C"
    if getattr(bound, "base_type", None) == "C":
        return True
    if isinstance(bound, tuple):
        return any(isinstance(v, complex) for v in bound)
    pieces = getattr(bound, "pieces", None) or ()
    return any(_bound_is_complex(p) for p in pieces if isinstance(p, tuple))


def complex_is_a_raise(callee, cj_domain: dict | None) -> bool:
    """Intent:
        Whether a complex result from `callee` counts as a raise under a
        claim with domain `cj_domain`: yes, unless the callee is
        annotated `complex` (its return or any parameter) or the claim
        quantifies some variable over the complex plane (`C`, or a
        rectangle with complex corners).
    """
    import inspect
    if any(_bound_is_complex(b) for b in (cj_domain or {}).values()):
        return False
    try:
        sig = callable_signature(callee)
    except (TypeError, ValueError):
        return True
    annotations = [sig.return_annotation,
                   *(prm.annotation for prm in sig.parameters.values())]
    return not any(a is not inspect.Signature.empty and "complex" in str(a)
                   for a in annotations)


def ordering_shortfall(lv, rv, relation: str) -> float:
    """Intent:
        By how much `lv <relation> rv` fails when compared exactly, for
        a closed ordering (`<=`/`>=`): the largest amount by which the
        left side exceeds (for `<=`) or falls short of (for `>=`) the
        right, taken elementwise over a matrix or array value. 0.0
        when the relation holds exactly, when the relation is not a
        closed ordering, or when the values are not finite reals.
    """
    if relation not in ("<=", ">="):
        return 0.0
    sign = 1.0 if relation == "<=" else -1.0
    if not _is_matrix_value(lv) and not _is_matrix_value(rv):
        if isinstance(lv, bool) or isinstance(rv, bool) \
                or not isinstance(lv, (int, float)) \
                or not isinstance(rv, (int, float)):
            return 0.0
        # the difference is taken exactly, so an integer too large for
        # a float never has to be converted unless it is the answer
        exact = (lv - rv) if relation == "<=" else (rv - lv)
        if exact <= 0:
            return 0.0
        try:
            gap = float(exact)
        except OverflowError:
            return 0.0
        return gap if math.isfinite(gap) else 0.0
    from .matrices import _numpy
    np = _numpy()
    if np is None:
        return 0.0
    try:
        gaps = sign * (np.asarray(lv, dtype=float) - np.asarray(rv, dtype=float))
        finite = gaps[np.isfinite(gaps)]
    except (ValueError, TypeError):
        return 0.0
    if finite.size == 0:
        return 0.0
    gap = float(finite.max())
    return gap if gap > 0 else 0.0


# _finite_bounds/_SpecialCycle/_synth_scalar live in ._sampling now,
# shared with symbolic/_proof_support.py's disproof corroboration,
# imported above, re-exported under their own names for existing
# importers of mathema.probing.


def _complex_component(rng: random.Random) -> float:
    """One part of a complex draw: uniform on [-10, 10], or with the
    far share a draw along the whole line out to complex128's
    per-component maximum (`_sampling._far_draw`)."""
    from ._sampling import _FAR_SHARE, _far_draw
    from .representations import PY_COMPLEX128
    if rng.random() < _FAR_SHARE:
        reach = float(PY_COMPLEX128.max_magnitude or 0.0)
        return _far_draw(rng, -reach, reach, True, True)
    return rng.uniform(-10, 10)


def _sample_bare_named_set(rng: random.Random, name: str):
    if name == "Z":
        return (rng.choice([0, 1, -1, 2, -2]) if rng.random() < 0.3
               else rng.randint(-1000, 1000))
    if name == "N":
        return rng.choice([0, 1, 2]) if rng.random() < 0.3 else rng.randint(0, 1000)
    if name == "C":
        # the plane's own landmark values favored the way the real
        # specials pool favors 0/1/-1; otherwise the real and the
        # imaginary part are each drawn from the everyday/far split: a
        # square patch around the origin, or (the far share) a
        # magnitude log-uniform over the decades out to complex128's
        # per-component maximum
        if rng.random() < 0.3:
            return rng.choice([0j, 1 + 0j, -1 + 0j, 1j, -1j,
                               1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j])
        return complex(_complex_component(rng), _complex_component(rng))
    return rng.uniform(-10, 10)   # "R"


def _integer_range(piece, base_type: str) -> "tuple[int, int]":
    """Intent:
        The first and last integers an interval piece admits, an open
        end excluding its endpoint and a fractional end rounding inward
        (`(0, 5]` gives 1..5, `[0.5, 5]` gives 1..5), with an unbounded
        side (an infinite end, or the reach a `ReachInterval` marks)
        capped the way `_finite_bounds` caps a real one. `first > last`
        when no integer lies inside.
    """
    from .domain import _integer_span
    first, last = _integer_span(piece, base_type)
    if getattr(piece, "reach_lo", False):
        first = -math.inf
    if getattr(piece, "reach_hi", False):
        last = math.inf
    flo, fhi = _moderate_bounds(*_reach_ends(piece))
    if math.isinf(first):
        first = math.ceil(flo)
    if math.isinf(last):
        last = math.floor(fhi)
    return int(first), int(last)


def _synth_int_in(rng: random.Random, piece, base_type: str) -> int:
    """Intent:
        One uniformly drawn integer inside an interval piece (see
        `_integer_range`). A piece holding no integer gives its first
        candidate, which the probe's own domain check then rejects.
    """
    first, last = _integer_range(piece, base_type)
    if first > last:
        return first
    return rng.randint(first, last)


def _draw_member(rng: random.Random, values: list, lap=None):
    """Intent:
        One member of a finite set, a sentinel among them drawn as a
        real value it stands for (`None` for absence, a member's value
        for a hole), never the sentinel itself; with a lap given, a
        sentinel draw takes the lap's next value, so the members the
        claim resolved are the ones used.
    """
    from .domain import is_sentinel, realise_sentinel
    choice = rng.choice(values)
    if not is_sentinel(choice):
        return choice
    if lap is not None:
        return lap.next()
    realised = realise_sentinel(choice)
    if realised:
        return rng.choice(realised)
    concrete = [v for v in values if not is_sentinel(v)]
    return rng.choice(concrete) if concrete else None


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

    from .domain import _is_enumerated, is_sentinel
    # a sentinel piece beside an interval or a named type is not drawn
    # at random; a finite set's own sentinels are its members
    enumerated = _is_enumerated(dom)
    pieces = tuple(p for p in dom.pieces
                   if enumerated or not (isinstance(p, frozenset) and p
                                         and all(is_sentinel(v) for v in p))) \
        or (dom.base_type,)
    weights = []
    for p in pieces:
        if _rectangle(p):
            weights.append(1.0)
        elif isinstance(p, tuple):
            lo, hi = _moderate_bounds(*_reach_ends(p))
            weights.append(max(hi - lo, 1e-9))
        else:
            weights.append(1.0)
    for _ in range(20):
        piece = rng.choices(pieces, weights=weights, k=1)[0]
        if isinstance(piece, frozenset):
            value = _draw_member(rng, list(piece))
        elif _rectangle(piece):
            c1, c2 = complex(piece[0]), complex(piece[1])
            value = complex(
                rng.uniform(min(c1.real, c2.real), max(c1.real, c2.real)),
                rng.uniform(min(c1.imag, c2.imag), max(c1.imag, c2.imag)))
        elif isinstance(piece, tuple):
            value = _synth_scalar(rng, piece, specials=specials)
            if dom.base_type in ("Z", "N"):
                # rounded, then held inside the piece's own integers,
                # so a draw just inside an open or fractional end never
                # rounds onto a point outside the domain; an infinite
                # draw is no integer, and stands for the capped end
                first, last = _integer_range(piece, dom.base_type)
                if not math.isfinite(value):
                    value = last if value > 0 else first
                value = min(max(int(round(value)), first), max(first, last))
        else:
            value = _sample_bare_named_set(rng, piece)
        try:
            kept = value not in dom.excluded
        except TypeError:
            kept = True
        if kept:
            return value
    return value


#: the hazard kinds the lap visits first: a length and a shape, which
#: is where a refinement's members at its bounds sit
_BOUND_KINDS = ("length", "shape")


def _language_lap(rng: random.Random, dom) -> "_SpecialCycle | None":
    """Intent:
        One lap over every hazard of a language domain, for the first
        draws of a parameter bound to it: the length and shape hazards
        (a refinement's members at its bounds among them) first, in the
        language's order, then the rest once each in a seeded order. `None` when
        the bound is not a language domain or has no hazard to visit.
    """
    if _classify_bound(dom) != "language":
        return None
    values = _language_hazards(dom)
    if not values:
        return None
    pairs = _language_hazards(dom, kinds=True)
    lengths = [v for v, kind in pairs if kind in _BOUND_KINDS]
    rest = [v for v, kind in pairs if kind not in _BOUND_KINDS]
    return _SpecialCycle(rng, values=rest, first=lengths)


class _Resolved:
    """One language piece of a domain, resolved once, its hazards built
    on first use and kept."""

    def __init__(self, piece) -> None:
        from .languages import resolve_language
        self.language = resolve_language(piece)
        self._hazards: "tuple | None" = None

    def hazards(self) -> tuple:
        if self._hazards is None:
            self._hazards = tuple(self.language.hazards())
        return self._hazards


#: recently sampled domains, each with its resolved pieces and the
#: registry generation they were resolved under
_RESOLVED: "collections.OrderedDict[int, tuple]" = collections.OrderedDict()
_RESOLVED_KEEP = 32


def _resolved(dom, piece) -> _Resolved:
    """Intent:
        `piece` of `dom` resolved, reused across a claim's draws until a
        language or refinement is registered or removed.

    Raises:
        UnknownLanguage, UnknownRefinement: as resolution does.
    """
    from .languages import generation
    now = generation()
    entry = _RESOLVED.get(id(dom))
    if entry is None or entry[0] is not dom or entry[1] != now:
        entry = (dom, now, {})
        _RESOLVED[id(dom)] = entry
        while len(_RESOLVED) > _RESOLVED_KEEP:
            _RESOLVED.popitem(last=False)
    else:
        _RESOLVED.move_to_end(id(dom))
    pieces = entry[2]
    if piece not in pieces:
        pieces[piece] = _Resolved(piece)
    return pieces[piece]


def _language_hazards(dom, kinds: bool = False) -> list:
    """Intent:
        Every hazard of a language domain's pieces, the members of the
        domain's excluded set left out, in the languages' own order;
        with `kinds`, `(value, kind)` pairs.
    """
    from .domain import LanguageRef
    values: list = []
    for piece in dom.pieces or ():
        if not isinstance(piece, LanguageRef):
            continue
        try:
            hazards = _resolved(dom, piece).hazards()
        except Exception:
            continue
        for h in hazards:
            try:
                excluded = h.value in dom.excluded
            except TypeError:
                excluded = False
            if not excluded:
                values.append((h.value, h.kind) if kinds else h.value)
    return values


class LanguageDrawFailed(Exception):
    """A language could not produce a member to sample (a schema whose
    checks reject every record drawn): the claim over it cannot be
    evaluated at all, on any route."""

    def __init__(self, piece, error: Exception) -> None:
        super().__init__(f"L[{getattr(piece, 'text', piece)}] produced no member to "
                         f"sample ({type(error).__name__}: {error})")


def _sample_language(rng: random.Random, dom: Domain):
    """Intent:
        One member of a language domain: a piece chosen uniformly (a
        language or a finite set of members), then a hazard value of
        that language three draws in ten and a random member
        otherwise, retried a bounded number of times to avoid an
        excluded member.

    Notes:
        The hazard corpus is the language's own (`Language.hazards`,
        every value of which is a member), so a draw never leaves the
        declared language; the guaranteed lap over every hazard is
        `_language_lap`, the per-parameter cycle the claim loop threads
        in through `_synth`'s `lap`.
    """
    from .domain import LanguageRef, is_sentinel
    pieces = dom.pieces or ()
    value = None
    for _ in range(20):
        piece = rng.choice(pieces)
        if isinstance(piece, frozenset):
            members = [v for v in piece if not is_sentinel(v)]
            if not members:
                continue
            value = rng.choice(members)
        elif isinstance(piece, LanguageRef):
            resolved = _resolved(dom, piece)
            hazards = resolved.hazards()
            if hazards and rng.random() < 0.3:
                value = rng.choice(hazards).value
            else:
                try:
                    value = resolved.language.sample(rng)
                except TimeoutError:
                    raise
                except Exception as e:
                    raise LanguageDrawFailed(piece, e) from e
        else:
            continue
        try:
            excluded = value in dom.excluded
        except TypeError:
            excluded = False
        if not excluded:
            return value
    return value


def _classify_bound(bounds) -> str:
    """The domain-bound shape, independent of a parameter's own
    inferred kind, "language" (a Domain over `L[...]` pieces),
    "domain" (a grammar.Domain: union/exclusion/an
    explicit type refinement), "frozenset" (a discrete set), "Z"/"N"
    (a named integer set), "interval" (a plain (lo, hi) tuple), or
    "none". Shared by every consumer that needs to dispatch on a
    bound's own shape (_synth's own sampling, _sampling_shorthand's
    rendering, ...) so a new bound shape only needs teaching to one
    place; the real gap that let _sampling_shorthand crash on a
    Domain object _synth already knew how to handle, the first time a
    claim's own richer domain bound reached it."""
    if isinstance(bounds, Domain):
        return "language" if bounds.base_type == "L" else "domain"
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
          length: "int | None" = None,
          lap: "_SpecialCycle | None" = None):
    # `kind == "sequence"` is checked first, unconditionally, before any
    # bounds-shape dispatch below, a Domain/frozenset/"Z"/"N" bound
    # means something different for a sequence (a per-element domain)
    # than it does for a scalar (the parameter's own domain), so a
    # sequence-typed parameter must never fall into the scalar
    # dispatch below and come back a bare number instead of a list.
    if _classify_bound(bounds) == "language":
        # a language bound is the parameter's own domain whatever kind
        # the body suggested (a mapping read, an iteration): the author
        # said the value IS a member, so it is drawn as one, the
        # language's hazards first when a lap is threaded in
        if lap is not None and lap.guaranteed_remaining():
            return lap.next()
        return _sample_language(rng, bounds)
    if lap is not None and lap.guaranteed_remaining() \
            and kind not in (*SEQUENCE_KINDS, "dict", "table"):
        # the sentinels a scalar's domain admits, each drawn once
        # before any random draw
        return lap.next()
    if kind == "dict":
        # a mapping parameter with no key list to hand (the automatic
        # type-probes): a generic dict, enough not to crash a function
        # that only iterates its values. The claim path uses
        # `_synth_dict(keys, ...)` with the body's real keys instead.
        return _synth_dict([], rng, specials=specials)
    if kind in SEQUENCE_KINDS:
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
    if bound_shape in ("domain", "frozenset") and lap is not None \
            and lap.guaranteed_remaining():
        # a finite set's listed sentinels, each realised member drawn
        # once before any random draw
        return lap.next()
    if bound_shape == "domain":
        return _sample_domain(rng, bounds, specials=specials)
    if bound_shape == "frozenset":
        return _draw_member(rng, list(bounds), lap)
    if bound_shape in ("Z", "N", "C"):
        return _sample_bare_named_set(rng, bound_shape)
    if kind == "bool":
        return rng.random() < 0.5
    if kind == "int":
        if bounds is not None:
            return _synth_int_in(rng, bounds, "Z")
        return rng.choice([0, 1, 2]) if rng.random() < 0.3 else rng.randint(0, 10)
    return _synth_scalar(rng, bounds, specials=specials, extra=extra, extra_cycle=extra_cycle)


def _annotation_text(param) -> str:
    """A signature parameter's annotation as source text, or ''."""
    import inspect
    ann = getattr(param, "annotation", inspect.Parameter.empty)
    if ann is inspect.Parameter.empty:
        return ""
    if isinstance(ann, str):
        return ann
    if isinstance(ann, type):
        return ann.__name__
    return repr(ann).replace("typing.", "")


def _hides_characters(s: str) -> bool:
    """Whether printing `s` would hide some of its characters from a
    reader: a combining mark, a format character, or a space other than
    the ordinary one. Controls need no help; `repr` escapes them."""
    import unicodedata
    for c in s:
        cat = unicodedata.category(c)
        if cat in ("Mn", "Mc", "Me", "Cf", "Zl", "Zp") or (cat == "Zs" and c != " "):
            return True
    return False


def spell_text(s: str, *, force: bool = False) -> str:
    """A string for a witness: its repr, followed by its escaped form in
    parentheses when printing it would hide characters (or `force`, for
    two sides that differ yet read the same)."""
    shown = repr(s)
    if force or _hides_characters(s):
        escaped = ascii(s)
        if escaped != shown:
            return f"{shown} ({escaped})"
    return shown


def sample_bound(bound, rng: random.Random, kind: str = "scalar"):
    """Intent:
        One value drawn from a declared bound, the draw the probe route
        makes for a parameter of `kind` with that bound: a language
        member for a language bound, an element of a finite set, an
        integer or a real inside an interval, a list for `"sequence"`.
        The extension surface's sampling seam, so a registered family
        or a language package draws members the way the probe does.
    """
    return _synth(kind, rng, bound)


def _nesting(v) -> tuple:
    """`(levels, records)`: how many container levels a value nests,
    counted with an explicit stack over lists, tuples, sets, dicts and
    the fields of objects with a `__dict__`, and the most values of the
    value's own type along any one path (0 unless it is such an
    object)."""
    root_type = type(v) if hasattr(v, "__dict__") and not isinstance(v, type) else None
    deepest = most = 0
    stack = [(v, 0, 0)]
    seen: set = set()
    while stack:
        node, level, records = stack.pop()
        if isinstance(node, (str, bytes, int, float, complex, bool)) or node is None:
            deepest = max(deepest, level)
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        if root_type is not None and type(node) is root_type:
            records += 1
            most = max(most, records)
        if isinstance(node, dict):
            kids = list(node.values())
        elif isinstance(node, (list, tuple, set, frozenset)):
            kids = list(node)
        elif hasattr(node, "__dict__"):
            kids = list(vars(node).values())
        else:
            deepest = max(deepest, level)
            continue
        deepest = max(deepest, level + 1)
        stack.extend((k, level + 1, records) for k in kids)
    return deepest, most


def _deep_summary(v) -> str:
    """A value too deep to print, by its type and how deep it nests: a
    tree of records by the records along its deepest path, the depth a
    record tree is measured in, anything else by its container levels."""
    levels, records = _nesting(v)
    name = type(v).__name__
    if records:
        return f"<{name} tree {records} records deep>"
    return f"<{name} nested {levels} levels deep>"


def _fmt_value(v) -> str:
    """One computed or sampled value, legibly, shared by _fmt() (an
    argument tuple) and every check closure's own failure `detail`
    string (the actual result(s) being compared, not just the inputs
    that produced them). A value nested too deep for Python to print
    is named by its type and its depth instead."""
    try:
        return _fmt_value_of(v)
    except RecursionError:
        return _deep_summary(v)


def _fmt_value_of(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, complex):
        # the claim grammar's own coordinate spelling (a+bj), never
        # Python's parenthesized repr
        return f"{v.real:.6g}{v.imag:+.6g}j"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_value_of(x) for x in v) + "]"
    if isinstance(v, tuple):
        return "(" + ", ".join(_fmt_value_of(x) for x in v) + ")"
    if isinstance(v, str):
        return spell_text(v)
    shown = repr(v)
    if shown.startswith("<") and " object" in shown and hasattr(v, "__dict__"):
        # a record whose repr is only its class (an ORM row): its public
        # fields say which record it is
        fields = {k: x for k, x in vars(v).items() if not k.startswith("_")}
        if fields:
            return (f"{type(v).__name__}("
                    + ", ".join(f"{k}={_fmt_value_of(x)}" for k, x in fields.items()) + ")")
    return shown


def _fmt(args: tuple, names: tuple[str, ...] | None = None,
         shown: "set[str] | None" = None) -> str:
    """A counterexample's argument tuple, legible on its own: labeled
    `name=value` pairs when the caller's own parameter names are known,
    a bare positional tuple otherwise. Unlabeled, a two-element
    counterexample like `([...], -5.54)` reads as (input, output);
    it's actually (x, alpha), both inputs. With `shown`, only the named
    arguments in it appear (all of them when none is)."""
    if names is not None and len(names) == len(args):
        pairs = list(zip(names, args))
        if shown is not None and any(n in shown for n, _ in pairs):
            pairs = [(n, a) for n, a in pairs if n in shown]
        return ", ".join(f"{n}={_fmt_value(a)}" for n, a in pairs)
    return "(" + ", ".join(_fmt_value(a) for a in args) + ")"


def _sampling_shorthand(kinds: dict, domain: dict, n: int,
                        critical_hints: dict[str, list[float]] | None = None,
                        truncated_hints: "set[str] | None" = None,
                        observed_lengths: "dict[str, set] | None" = None,
                        premise_drawn: "set[str] | None" = None,
                        runtime_names: "dict[str, str] | None" = None,
                        nested: "set[str] | None" = None,
                        lap_floor: "tuple[int, int] | None" = None,
                        holes: "dict[str, list] | None" = None) -> str:
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
    ordinary sampling, not every point that was actually found.

    A sequence parameter states the lengths its checked samples had
    (`observed_lengths`: one length as `len=20`, several as their
    range, none recorded as the free draw's `len∈[2,8]`) and how its
    elements were drawn: the declared element domain (`elem~...`, the
    special shapes are not used under one), the free draw with its
    shapes, or `drawn on the premise` for a parameter in
    `premise_drawn`, which an equality premise draws directly. A
    parameter in `runtime_names` states the runtime type each draw was
    realised as (`as pandas.Series`); one in `nested`, drawn as nested
    lists, states the size cap per axis those are drawn up to.
    `lap_floor`, `(lap, budget)`, says the trial count was raised from
    the budget to a language's lap so every hazard is visited."""
    critical_hints = critical_hints or {}
    truncated_hints = truncated_hints or set()

    def crit_suffix(p: str) -> str:
        hints = critical_hints.get(p)
        if not hints:
            return ""
        trunc = f"[truncated@{len(hints)}]" if p in truncated_hints else ""
        return "⊕crit{" + ", ".join(f"{v:g}" for v in hints) + "}" + trunc

    def far_suffix(bounds) -> str:
        # an unbounded direction's far draws, out to its reach
        lo, hi, un_lo, un_hi = _reach_ends(bounds)
        reach = max(abs(lo) if un_lo else 0.0, abs(hi) if un_hi else 0.0)
        return f"⊔far(≤{reach:g})"

    lengths_seen = observed_lengths or {}
    premise_drawn = premise_drawn or set()

    def sequence_text(p: str) -> str:
        lengths = sorted(lengths_seen.get(p) or ())
        if not lengths:
            size = "len∈[2,8]"
        elif len(lengths) == 1:
            size = f"len={lengths[0]}"
        else:
            size = f"len∈[{lengths[0]},{lengths[-1]}]"
        element_bound = domain.get(p)
        if p in premise_drawn:
            draw = "drawn on the premise"
        elif element_bound is not None:
            draw = "elem~" + element_text(p, element_bound)
        else:
            draw = "shape∈{U,const,sorted,rev,+0,extreme}[p=.3]"
        admitted = (holes or {}).get(p)
        if admitted:
            from ._missing_words import value_shown
            words = ", ".join(dict.fromkeys(value_shown(h, in_slot=True)
                                            for h in admitted))
            draw += f"; holes {{{words}}} at p=.15, degenerate lap first"
        realised = (runtime_names or {}).get(p)
        if realised:
            draw += f"; as {realised}"
        elif p in (nested or ()):
            from .runtime_types import ListAdapter
            draw += (f"; as nested lists, at most {ListAdapter.SIZE_CAP} "
                     f"per axis")
        return f"Seq({size}; {draw})"

    def element_text(p: str, bound) -> str:
        # a space binding (`[0, 1]^n`, `R^n`) is a Domain with `dims`,
        # each element drawn from the Domain without them
        if isinstance(bound, Domain) and bound.dims:
            element = dataclasses.replace(bound, dims=())
            values = [pc for pc in element.pieces if not _sentinel_piece(pc)]
            if not numeric_excluded(element) and element.base_type == "R":
                if not values:
                    return "U(-10,10)"
                if len(values) == 1 and isinstance(values[0], (tuple, list)):
                    lo, hi = values[0]
                    return f"U({lo:g},{hi:g})⊔{{lo,hi,mid,±ε}}[p=.3]"
            return one(p, "float", element)
        return one(p, "float", bound)

    def one(p: str, k: str, bounds) -> str:
        if k == "table":
            return ("Table(equal-length columns, len∈[2,8], each drawn "
                    "as a free Seq)")
        if (isinstance(bounds, Domain) and len(bounds.pieces) == 1
                and getattr(bounds.pieces[0], "bare", False)
                and not numeric_excluded(bounds)):
            # a bare real line given the reach samples as a bare parameter
            bounds = bounds.pieces[0]
        if getattr(bounds, "bare", False):
            return (f"U(-10,10)⊔{{0,±1,±.5,2,±1e-9,±1e6}}[p=.3]"
                    f"{far_suffix(bounds)}[p=.1]{crit_suffix(p)}")
        if isinstance(bounds, tuple) and k != "int" and (
                getattr(bounds, "reach_lo", False)
                or getattr(bounds, "reach_hi", False)):
            mlo, mhi = _moderate_bounds(*_reach_ends(bounds))
            return (f"U({mlo:g},{mhi:g})⊔{{lo,hi,mid,±ε}}[p=.3]"
                    f"{far_suffix(bounds)}{crit_suffix(p)}")
        bound_shape = _classify_bound(bounds)
        if bound_shape == "frozenset":
            from .domain import _member_sort_key
            members = sorted(bounds, key=_member_sort_key)
            return f"U{{{', '.join(str(v) for v in members)}}}"
        if bound_shape == "Z":
            return "{0,±1,±2}[p=.3]⊔U{-1000..1000}"
        if bound_shape == "N":
            return "{0,1,2}[p=.3]⊔U{0..1000}"
        if k in SEQUENCE_KINDS:
            return sequence_text(p)
        if k == "int" and (bounds is None or isinstance(bounds, tuple)):
            # only a plain (lo, hi) tuple/Interval is subscriptable; a
            # Domain-typed bound (a `⊂ Z` refinement) falls through to
            # the set-notation rendering below. The integers actually
            # drawn: an open or fractional end rounds inward and an
            # unbounded end is capped, as `_synth_int_in` samples them
            if bounds:
                first, last = _integer_range(bounds, "Z")
                return f"U{{{first}..{last}}}"
            return "{0,1,2}[p=.3]⊔U{0..10}"
        if bound_shape == "interval":
            lo, hi = bounds
            return f"U({lo:g},{hi:g})⊔{{lo,hi,mid,±ε}}[p=.3]{crit_suffix(p)}"
        if bound_shape != "none":
            # "domain" (grammar.Domain: union/exclusion/an explicit
            # type refinement) or "other": the canonical set-notation
            # text a person would type for it
            from .grammar import render_domain_bound
            return f"{render_domain_bound(bounds)}{crit_suffix(p)}"
        return f"U(-10,10)⊔{{0,±1,±.5,2,±1e-9,±1e6}}[p=.3]{crit_suffix(p)}"

    def bound_of(p: str, k: str):
        # a sequence's declared bound is its element domain, read by
        # `sequence_text`; a language bound is the parameter's own
        # domain whatever its kind
        bound = domain.get(p)
        if k in SEQUENCE_KINDS and _classify_bound(bound) != "language":
            return None
        return bound

    parts = [f"{p}~{one(p, k, bound_of(p, k))}" for p, k in kinds.items()]
    floor = (f", n raised to {lap_floor[0]} to visit every hazard (budget {lap_floor[1]})"
             if lap_floor else "")
    return ", ".join(parts) + f", seed={_RNG_SEED}, n={n}" + floor


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
        if bounds.base_type == "L":
            # a language's own near non-members are its `outside`
            # draws, which the safety families read directly
            return []
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
    affine: bool = False
    explicit_trials: bool = False
    scale: float = 1.0
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
    affine = trials is None and _affine_hint(fn, facts)
    budget = trials if trials is not None else _starting_budget(risk, affine)
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
    budget = _scaled_budget(budget, scale)
    # record-schema.md's own `route` field: "probe:semi_analytical"
    # states plainly that at least one parameter's own sampling was
    # informed by an analytically discovered critical point this run,
    # not blind trial-and-error.
    route_value = "probe:semi_analytical" if analytical else "probe"
    return SamplingSetup(rng=rng, specials=specials, risk=risk, budget=budget,
                         points=points, critical_hints=critical_hints,
                         truncated_hints=truncated_hints,
                         extra_cycles=extra_cycles, route=route_value,
                         affine=affine, explicit_trials=trials is not None,
                         scale=scale)


def _scaled_budget(budget: int, scale: float) -> int:
    """Intent:
        `budget` shrunk by `trials_scale` when it is below one, never
        under `min_trials_floor_when_scaled` or one lap of the specials.
    """
    if scale < 1.0:
        return max(_RISK.min_trials_floor_when_scaled, len(_SPECIALS),
                   round(budget * scale))
    return budget


def claim_sampling_budget(setup: "SamplingSetup", facts, cj_domain: dict) -> "tuple[dict, int]":
    """Intent:
        The risk and trial budget for one claim: the function's own
        setup, with the `language` factor read off the claim's domain
        (a written binding or an inferred one), and the budget set from
        the complexity that factor adds. An explicit trial count is kept
        as given.
    """
    language = _language_risk(facts.params, cj_domain)
    if language is None or language == setup.risk.get("language"):
        return setup.risk, setup.budget
    risk = {**setup.risk, "language": language}
    if setup.explicit_trials:
        return risk, setup.budget
    return risk, _scaled_budget(_starting_budget(risk, setup.affine), setup.scale)


def string_domain_hint(p: str) -> str:
    """Intent:
        Why a string parameter `p` with no domain is not sampled, and
        the spelling that declares one: `L[unicode]` when that string
        language is installed, a finite set of strings otherwise.
    """
    from .languages import resolves
    example = (f"'for {p} in L[unicode], ...'" if resolves("unicode")
               else f"'for {p} in {{\"a\", \"b\"}}, ...'")
    return (f"parameter {p!r} is a string with no declared domain; "
            f"declare its values, e.g. {example}")


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
                "frozenset", "domain", "language"):
            return [Probe(
                "callable", callable_statement, "skipped",
                note=string_domain_hint(p) + " in a claim, or annotate it "
                     "Literal[...]",
                meta={"mathema.probe_gap": "string-domain-missing"})]
    # budget/risk/route_value aren't needed here, domain_enforced below
    # is the only law left in this function (everything else migrated to
    # claims, see suggest_claims()), and it reports its own fixed route
    # rather than a sampling-informed one.
    setup = _prepare_sampling(fn, facts, domain, trials, trials_scale, extensive)
    rng, specials = setup.rng, setup.specials
    critical_hints, extra_cycles = setup.critical_hints, setup.extra_cycles

    try:
        signature = callable_signature(fn).parameters
    except (TypeError, ValueError):
        signature = {}

    from . import dimensions as _dims
    from .types import shapes_from_signature
    try:
        resolver = _dims.resolve(facts, shapes_from_signature(fn),
                                 claim_domain=domain)
    except _dims.DimensionConflict:
        resolver = None

    def value_for(p, k, sizes):
        param = signature.get(p)
        if (param is not None and p not in domain
                and _keeps_default(fn, param)):
            return param.default
        if k == "table":
            # a table: equal-length columns, each drawn as a sequence
            n = rng.randint(2, 8)
            return {c: _synth("sequence", rng, None, specials=specials,
                              length=n) for c in ("a", "b")}
        shape = resolver.shapes.get(p) if resolver is not None else None
        if shape is not None and k not in SEQUENCE_KINDS and shape.ndim >= 1:
            # a space binding (`R^n`, `R^(n,n)`) from the claims shapes
            # a parameter whose kind the signature does not state
            return resolver.synth(
                p, sizes, lambda: _synth("float", rng, domain.get(p),
                                         specials=specials), rng)
        drawn = _synth(k, rng, domain.get(p), specials=specials,
                       extra=critical_hints.get(p),
                       extra_cycle=extra_cycles.get(p))
        if inputs_missing([drawn]):
            # the smoke call asks whether f can be called with a value;
            # a claim's own missing points are its own to execute
            return _synth(k, rng, None, specials=specials)
        return drawn

    def args_for() -> "tuple[list, dict]":
        sizes = resolver.draw_sizes(rng) if resolver is not None else {}
        return call_arguments(fn, facts.params, {
            p: value_for(p, k, sizes) for p, k in zip(facts.params, kinds)})

    # A parameter's own critical-point hint is drawn deterministically
    # exactly once (extra_cycle's own guaranteed lap), which may be
    # this very first call; retrying a few times tells a genuine
    # signature mismatch (fails identically every time) apart from a
    # one-off arithmetic exception from landing exactly on a pole.
    last_exc: Exception | None = None
    from .runtime_types import calling
    call = calling(fn, facts)
    for _ in range(3):
        try:
            call_args, call_kwargs = args_for()
            call(*call_args, **call_kwargs)
            break
        except Exception as e:
            last_exc = e
    else:
        hints = "".join(f"; {h['text']}" for h in
                        (getattr(facts, "runtime_hints", None) or {}).values())
        shown = ", ".join(
            f"{name}: {_annotation_text(param)}" if _annotation_text(param)
            else name for name, param in signature.items())
        return [Probe("callable", callable_statement, "skipped",
                      note=f"f could not be called with a value mathema built "
                           f"from the signature ({shown}): "
                           f"{type(last_exc).__name__}: {last_exc}" + hints,
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
