# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_reproducible, the WEAKER stateless member: reproducible up to
an RNG seed; fix the seed, rerun, get the same output. Its trials
capture and restore the recognized RNG states (stdlib random, numpy's
legacy global) around paired calls; is_deterministic remains the
strong member (no state, no seed, anywhere)."""
import random
import time as _time

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def seeded_noise(x: float) -> float:
    # the plain module spelling on purpose: the structural randomness
    # detector recognizes the canonical module roots, not aliases
    return x + random.random()


def clocked(x: float) -> float:
    return x + _time.time()


def line(x: float) -> float:
    return 3.0 * x + 2.0


def _one(fn, name):
    (probe,) = check_conjectures(
        fn, [claim("f(x) == f(x)", name=name, route="best")],
        facts=analyze_source(fn))
    return probe


def test_rng_draw_is_reproducible_up_to_the_seed_but_not_deterministic():
    rep = _one(seeded_noise, "is_reproducible")
    assert rep.verdict == "holds"
    assert rep.route == "probe:algorithmic"
    det = _one(seeded_noise, "is_deterministic")
    assert det.verdict == "falsified"


def test_clock_reads_are_not_reproducible_by_any_seed():
    probe = _one(clocked, "is_reproducible")
    assert probe.verdict == "falsified"
    assert "different results" in probe.counterexample


def test_deterministic_body_is_a_fortiori_reproducible():
    probe = _one(line, "is_reproducible")
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "implies reproducible" in probe.sketch


def test_suggestions_gate_reproducibility_on_structural_randomness():
    noisy = {c.name for c in suggest_claims(seeded_noise)}
    assert "is_deterministic" in noisy
    assert "is_reproducible" in noisy
    plain = {c.name for c in suggest_claims(line)}
    assert "is_deterministic" in plain
    assert "is_reproducible" not in plain
