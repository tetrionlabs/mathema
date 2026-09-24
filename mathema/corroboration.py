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
  hide that it was claimed). When the difference is known to exist in
  exact arithmetic and the executed code was compared exactly at the
  point that shows it, floating point simply does not reproduce it:
  `meta["mathema.corroboration_reason"] = "exact arithmetic only"`, and
  the note says that instead of naming an engine bug.
- a `proven` is exact in real arithmetic and says nothing about the
  float implementation. That is a claim of its own, the `<name>[float]`
  companion a derive proof spawns (gates._float_companion): the sweep
  below executes the relation against the real code at the domain's
  corners and sampled interior points, and a raise, a NaN, or an inf or
  a precision loss where the relation fails falsifies the companion,
  never the proof. An unbounded direction runs to the claim's declared
  `pseudo_infinity`, else to a large sampled magnitude.

Every dependency is injected, evaluator, sampler, in-domain predicate,
corner points, so the engine has no hidden coupling.
"""
import random
from dataclasses import dataclass, field
from typing import Callable

from ._sampling import _RNG_SEED

_CORROBORATION_BUDGET = 40
#: why a disproof is uncorroborated when the executed code, compared
#: exactly where the exact difference is, agrees with the claim
EXACT_ARITHMETIC_ONLY = "exact arithmetic only"
#: the note an exact-arithmetic-only disproof carries
EXACT_ARITHMETIC_ONLY_NOTE = ("the difference exists in exact arithmetic "
                              "and floating point does not reproduce it")
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
    """A float sweep's outcome: `fragile_point` is the first in-domain
    point where the implementation breaks (else None), `detail` naming
    the failure, `checked` how many in-domain points were executed, and
    `in_flight` the point being executed when the sweep was cut short
    (a wall-clock cap), else None."""
    fragile_point: dict | None = field(default=None)
    detail: str = ""
    checked: int = 0
    in_flight: dict | None = None


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
                    budget: int = _CORROBORATION_BUDGET,
                    progress: "StabilitySweep | None" = None) -> StabilitySweep:
    """Intent:
        Execute a claim's relation against the real implementation
        across the declared domain: the corners first (where a
        division, sqrt, log or exp implementation breaks), then `budget`
        sampled interior points. `probe_finite(point)` returns a failure
        description (a raise, a NaN, or an inf or a deviation past a
        magnitude-scaled tolerance where the relation fails) or None
        when the code agrees with the relation there.

    Notes:
        Returns the first fragile point (one real break falsifies,
        since the claim promised the code holds there). `progress`,
        when passed, is updated in place as the sweep runs, so a caller
        that cuts the sweep short with a wall-clock cap still knows how
        far it got and which point was executing.
    """
    out = progress if progress is not None else StabilitySweep()
    rng = random.Random(_RNG_SEED)
    interior = [{n: sample(n, rng) for n in names} for _ in range(budget)]
    for point in list(corners) + interior:
        if not admits(point):
            continue
        out.in_flight = point
        detail = probe_finite(point)
        out.in_flight = None
        out.checked += 1
        if detail is not None:
            out.fragile_point, out.detail = point, detail
            return out
    return out
