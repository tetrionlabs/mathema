# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_reproducible, the member for a function that takes a seed or a
generator: every draw must come through that parameter, so the same
seed gives the same output. It is decided from the source, as
is_deterministic is (no state, no seed, anywhere)."""
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


def test_a_draw_from_the_global_generator_is_neither_reproducible_nor_deterministic():
    rep = _one(seeded_noise, "is_reproducible")
    assert rep.verdict == "falsified"
    assert rep.route == "examine"
    assert "draws from the shared random generator (random.random)" in \
        rep.counterexample
    det = _one(seeded_noise, "is_deterministic")
    assert det.verdict == "falsified"


def test_clock_reads_are_not_reproducible_by_any_seed():
    probe = _one(clocked, "is_reproducible")
    assert probe.verdict == "falsified"
    assert "calls time.time" in probe.counterexample


def test_deterministic_body_is_a_fortiori_reproducible():
    probe = _one(line, "is_reproducible")
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "no random generator included" in probe.sketch


def test_suggestions_gate_reproducibility_on_structural_randomness():
    noisy = {c.name for c in suggest_claims(seeded_noise)}
    assert "is_deterministic" in noisy
    assert "is_reproducible" in noisy
    plain = {c.name for c in suggest_claims(line)}
    assert "is_deterministic" in plain
    assert "is_reproducible" not in plain
