# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Corroborating a derive verdict against the REAL function.

Derive attests two things at once: the mathematics is correct AND the
implementation reflects it. So a derive verdict is only trusted once it
is checked against the actual callable, never the internal (possibly
corrupt) residual:

- a `disproven` must REPRODUCE: a concrete, in-domain, assumption-
  respecting counterexample where the original function genuinely
  violates the claim. Reproduced -> `falsified`; not reproduced -> the
  verdict downgrades to `unknown`, with
  `meta["mathema.corroboration"] = "uncorroborated"` and an engine-bug
  note (a symbolic sign error, e.g. sympy's `is_nonnegative`
  mis-signing an interval, must neither assert the falsification nor
  hide that it was claimed).
- a `proven` is exact in real arithmetic, but its IMPLEMENTATION can
  still be numerically unstable (a raise / NaN / catastrophic
  deviation) somewhere in the declared domain. Pedantically, a claim
  over a domain promises the code holds across ALL of it, so a genuine
  break falsifies, unless the claim caps infinity with a declared
  `pseudo_infinity` (the domain approximation, parallel to tolerance).
  With no cap, the full extreme range is checked. This proven-route
  sweep is opt-in for now (see conjecture.set_numerical_stability_check)
  because the extreme corners of an unbounded domain break otherwise
  sound proofs; the disproof-reproduction gate above is always live.

Every dependency is injected, evaluator, sampler, in-domain predicate,
corner points, so the engine has no hidden coupling.
"""
import random
from dataclasses import dataclass, field
from typing import Callable

from ._sampling import _RNG_SEED

_CORROBORATION_BUDGET = 40
_PERTURBATIONS = (1e-6, -1e-6, 1e-3, -1e-3, 1e-9, -1e-9)


@dataclass
class Corroboration:
    """A disproof-corroboration search outcome: `point` is a concrete
    counterexample when one reproduced (else None), `checked` how many
    candidates were evaluated, `seeded` whether the disproof's own
    witness guided the find (route tag probe:semi_analytical)."""
    point: dict | None
    checked: int = 0
    seeded: bool = False
    reason: str = ""


@dataclass
class StabilitySweep:
    """A proven claim's numerical-stability outcome: `fragile_point`
    is the first in-domain point where the implementation breaks
    beyond tolerance (else None), `detail` naming the failure."""
    fragile_point: dict | None = field(default=None)
    detail: str = ""


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _seed_points(witness: dict | None, names: list[str]) -> list[dict]:
    """Intent:
        The candidates to try FIRST when reproducing a disproof: the
        exact witness derive supplied, then small perturbations of it,
        so a narrow failure region reproduces cheaply before blind
        sampling.

    Notes:
        Numeric witness coordinates are used and perturbed; a list
        coordinate (a sequence parameter's witness) is carried into
        every seed unchanged; a coordinate absent from the witness is
        left to the sampler. Empty witness -> [].
    """
    if not witness:
        return []
    base = {n: float(witness[n]) for n in names
            if n in witness and not isinstance(witness[n], (list, tuple))
            and _is_number(witness[n])}
    fixed = {n: list(witness[n]) for n in names
             if isinstance(witness.get(n), (list, tuple))}
    if not base and not fixed:
        return []
    points = [{**fixed, **base}]
    if base:
        for delta in _PERTURBATIONS:
            points.append({**fixed, **{n: base[n] * (1.0 + delta) + delta
                                       for n in base}})
    return points


def corroborate_disproof(evaluate: Callable[[dict], "bool | None"],
                         names: list[str], *, sample: Callable,
                         admits: Callable[[dict], bool],
                         witness: dict | None = None,
                         budget: int = _CORROBORATION_BUDGET) -> Corroboration:
    """Intent:
        Search for a concrete point where the ORIGINAL claim genuinely
        fails, corroborating a derive `disproven`. `evaluate(point)`:
        True = holds, False = fails (a real counterexample), None =
        can't tell. Seeds (the witness and its perturbations) first,
        then a blind `sample`d sweep; every candidate passes `admits`.

    Notes:
        `point` None -> nothing reproduced in `budget` ->
        `falsified:uncorroborated`. `seeded` marks a seed-guided find.
    """
    checked = 0
    seeds = _seed_points(witness, names)
    for point in seeds:
        if not admits(point):
            continue
        checked += 1
        if evaluate(point) is False:
            return Corroboration(point, checked, seeded=True,
                                 reason="reproduced from the analytical seed")
    rng = random.Random(_RNG_SEED)
    for _ in range(budget):
        point = {n: sample(n, rng) for n in names}
        if not admits(point):
            continue
        checked += 1
        if evaluate(point) is False:
            return Corroboration(point, checked, seeded=bool(seeds),
                                 reason="reproduced by sampling")
    return Corroboration(None, checked, seeded=bool(seeds),
                         reason="no in-domain counterexample reproduced")


def sweep_stability(probe_finite: Callable[[dict], "str | None"],
                    names: list[str], *, sample: Callable, corners: list,
                    admits: Callable[[dict], bool],
                    budget: int = _CORROBORATION_BUDGET) -> StabilitySweep:
    """Intent:
        Sweep a proven-exact claim's IMPLEMENTATION for numerical
        instability across the declared domain (with infinity taken at
        the caller's pseudo-infinity cap, or full float extremes when
        uncapped). `probe_finite(point)` returns a failure description
        (a raise / NaN / catastrophic deviation past a magnitude-scaled
        tolerance) or None when stable there.

    Notes:
        Returns the first fragile point (conservative: one real break
        falsifies, since the claim promised the code holds there). The
        corners (domain endpoints at the cap) come first; that is
        where a division/sqrt/log/exp implementation breaks.
    """
    rng = random.Random(_RNG_SEED)
    interior = [{n: sample(n, rng) for n in names} for _ in range(budget)]
    for point in list(corners) + interior:
        if not admits(point):
            continue
        detail = probe_finite(point)
        if detail is not None:
            return StabilitySweep(point, detail)
    return StabilitySweep()
