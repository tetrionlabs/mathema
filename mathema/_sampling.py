# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Seeded scalar sampling: the primitive `probing.py`'s own numeric
probes are built on, factored out so `symbolic/_proof_support.py` can
reuse the exact same sampler (same seed, same boundary/special-value
bias) to corroborate a claimed disproof numerically, rather than
re-implementing a plainer sampler of its own. Stdlib-only (`math`,
`random`), so both `probing.py` and the `symbolic` package can depend
on it with no cycle between them.
"""
from __future__ import annotations

import math
import random

_RNG_SEED = 20260718
_SPECIALS = [0.0, 1.0, -1.0, 0.5, -0.5, 2.0, 1e-9, -1e-9, 1e6, -1e6]
_LARGE = 1e6

# The string edge-case corpus the is_arbitrary_input_safe fuzzer draws
# from: the inputs real code forgets, empty and whitespace, control
# characters, combining and zero-width marks, non-ascii and astral
# scripts, a very long string, and injection-/format-/path-shaped
# strings. Every one is tried at least once (the family iterates the
# whole corpus), so a crash on any of them is always found, not left to
# a random draw.
_STRING_SPECIALS = [
    "",
    " ",
    "\t",
    "\n",
    "\r\n",
    "0",
    "-1",
    "1e309",
    "abc",
    "A" * 4096,
    "caf\u00e9",
    "\u65e5\u672c\u8a9e",
    "\U0001f642",
    "a\u0301",
    "\u200b",
    "\x00",
    "\x7f",
    "../../etc/passwd",
    "'; DROP TABLE users; --",
    "{0}",
    "%s%n",
    "{}",
    "null",
]


def _finite_bounds(lo: float, hi: float) -> tuple[float, float]:
    if math.isinf(lo) and math.isinf(hi):
        return -_LARGE, _LARGE
    if math.isinf(lo):
        return hi - _LARGE, hi
    if math.isinf(hi):
        return lo, lo + _LARGE
    return lo, hi


class _SpecialCycle:
    """Every value in _SPECIALS gets tested at least once, regardless of
    the random 30% special-vs-uniform draw below, the first
    `len(_SPECIALS)` calls to `.next()` deterministically dispense one
    each (shuffled, so the order is still seeded and reproducible, not
    identical run to run), forcing that guaranteed lap before the 30%
    gate is even consulted. Without this, i.i.d. random.choice needs
    ~29 draws on average to see all 10 values at least once (coupon
    collector: n * H(n)), a reduced trial budget (as low as
    _RiskPolicy.affine_budget) may spend far fewer than that on the
    pool overall, silently never reaching some of the exact points
    (`0`, `±1`, `±1e-9`, `±1e6`, ...) it exists to guarantee coverage
    of. After the first guaranteed lap, later calls fall back to a
    second (reshuffled) lap on the same schedule, still every value
    eventually, just no longer front-loaded. One cycle is shared across
    every scalar parameter drawn in a single probe() call, not one per
    parameter, so on a multi-parameter function the guarantee is that
    every special value is exercised *somewhere* in the run, not that
    each parameter individually sees all ten.

    `values` defaults to the module-level `_SPECIALS`. A caller with
    its own pool (a per-parameter critical-point hint, see
    `probing._critical_hint()`) passes `values=` directly."""
    def __init__(self, rng: random.Random, values: list[float] | None = None):
        self._rng = rng
        self._values = values if values is not None else _SPECIALS
        self._pool: list[float] = []
        self._dispensed = 0

    def next(self) -> float:
        if not self._pool:
            self._pool = list(self._values)
            self._rng.shuffle(self._pool)
        self._dispensed += 1
        return self._pool.pop()

    def guaranteed_remaining(self) -> bool:
        return self._dispensed < len(self._values)


def _synth_scalar(rng: random.Random, bounds=None,
                  specials: "_SpecialCycle | None" = None,
                  extra: list[float] | None = None,
                  extra_cycle: "_SpecialCycle | None" = None) -> float:
    """Intent:
        One scalar sample. `extra`/`extra_cycle` are a parameter's own
        analytically discovered critical points (see
        probing._critical_hint()), threaded in alongside the ordinary
        boundary/special pools.

    Notes:
        `extra` (a plain list) extends the boundary-candidate pool when
        a bound is declared, picked probabilistically alongside the
        ordinary boundary candidates. `extra_cycle` (its own
        _SpecialCycle over the same points) is the *guaranteed* form:
        checked first, bound or not, so a parameter's own analytically
        discovered pole gets tested at least once within its own
        guaranteed lap rather than only ever being one candidate among
        several a 30% draw might not even reach. A hint that falls
        outside a declared bound is skipped (not a valid sample here)
        without spending the guarantee on it. When no bound is
        declared, `extra_cycle` is also checked before the shared
        specials cycle, so a parameter's own pole isn't diluted into
        every other parameter's shared pool.
    """
    # an open endpoint is NOT in the domain: a boundary candidate drawn
    # exactly there is an out-of-domain point, and a claim "falsified"
    # at it is a phantom counterexample, so open ends contribute a
    # just-inside point instead of the endpoint itself
    closed_lo = getattr(bounds, "closed_lo", True)
    closed_hi = getattr(bounds, "closed_hi", True)
    if extra_cycle is not None and extra_cycle.guaranteed_remaining():
        v = extra_cycle.next()
        if bounds is None:
            return v
        flo, fhi = _finite_bounds(*bounds)
        if ((flo < v or (closed_lo and v == flo))
                and (v < fhi or (closed_hi and v == fhi))):
            return v
    if bounds is not None:
        lo, hi = bounds
        if rng.random() < 0.3:
            if rng.random() < 0.3 and (math.isinf(lo) or math.isinf(hi)):
                return rng.choice([b for b in (lo, hi) if math.isinf(b)])
            flo, fhi = _finite_bounds(lo, hi)
            span = fhi - flo
            # a relative step inside each end, at least one float (and
            # never past the other end), so a subnormal-width range
            # never rounds the step back onto the endpoint
            in_lo = min(max(flo + span * 1e-6, math.nextafter(flo, math.inf)), fhi)
            in_hi = max(min(fhi - span * 1e-6, math.nextafter(fhi, -math.inf)), flo)
            candidates = [flo if closed_lo else in_lo,
                         fhi if closed_hi else in_hi,
                         (flo + fhi) / 2,
                         in_lo, in_hi]
            if extra:
                candidates += [v for v in extra if flo < v < fhi]
            return rng.choice(candidates)
        return rng.uniform(*_finite_bounds(lo, hi))
    # extra_cycle's own guaranteed lap is already handled above,
    # unconditionally, before bounds is even consulted.
    if specials is not None and specials.guaranteed_remaining():
        return specials.next()
    if rng.random() < 0.3:
        return specials.next() if specials is not None else rng.choice(_SPECIALS)
    return rng.uniform(-10, 10)


def _synth_string(rng: random.Random) -> str:
    """Intent:
        One string sample biased toward the edge cases in
        `_STRING_SPECIALS`, with an occasional short random string
        (mixed ascii, whitespace, and non-ascii) so the fuzzer is not
        limited to the fixed corpus.
    """
    if rng.random() < 0.85:
        return rng.choice(_STRING_SPECIALS)
    alphabet = "abcXYZ 0_/\\.\"'{}\n\t\u65e5\U0001f642"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
