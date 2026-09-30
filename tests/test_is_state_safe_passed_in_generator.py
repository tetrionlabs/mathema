# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A generator passed in as a parameter belongs to the caller, who
expects it to move: drawing from it is not a state change for
is_state_safe, and such a function is judged by is_reproducible (same
seed, same output). Drawing from the global generator (`random`,
`numpy.random`) advances state every other caller sees, and falsifies
is_state_safe with that state named."""
import random

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def simulated_return(mu: float, rng: np.random.Generator) -> float:
    return mu + 0.01 * rng.standard_normal()


def simulated_return_stdlib(mu: float, rng: random.Random) -> float:
    return mu + 0.01 * rng.gauss(0, 1)


def global_noise(mu: float) -> float:
    return mu + 0.01 * np.random.rand()


def _one(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


@pytest.mark.parametrize("fn", [simulated_return, simulated_return_stdlib])
def test_a_function_drawing_from_its_own_generator_is_state_safe(fn):
    p = _one(fn, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (fn.__name__, p.verdict, p.route,
                                      p.counterexample, p.note)


@pytest.mark.parametrize("fn", [simulated_return, simulated_return_stdlib])
def test_it_is_judged_by_is_reproducible(fn):
    p = _one(fn, "is_reproducible(f)")
    assert p.verdict == "holds", (fn.__name__, p.verdict, p.note)


def test_a_global_numpy_draw_is_falsified_with_the_state_named():
    p = _one(global_noise, "is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "the global state of numpy.random" in p.counterexample


VOLATILITY = 0.01


def simulated_return_scaled(mu: float, rng: np.random.Generator) -> float:
    # reads a module-level value, so structure alone cannot prove it and
    # the trials decide: the draw moves only the caller's generator
    return mu + VOLATILITY * rng.standard_normal()


def test_the_trials_do_not_count_a_draw_on_the_passed_in_generator():
    p = _one(simulated_return_scaled, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("holds", "probe:algorithmic"), (
        p.verdict, p.route, p.counterexample, p.note)


def draw_then_reseed(mu: float, rng) -> float:
    # an unannotated generator parameter: drawn from, then the global
    # generator is reseeded, a real state change
    value = mu + 0.01 * rng.random()
    random.seed(1)
    return value


def test_an_unannotated_rng_gets_a_real_generator_and_a_global_write_falsifies():
    p = _one(draw_then_reseed, "is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "the global state of random" in p.counterexample


def test_the_generator_in_a_witness_is_the_call_that_rebuilds_it():
    import re
    p = _one(draw_then_reseed, "is_state_safe(f)")
    assert re.search(r"rng = numpy\.random\.default_rng\(\d+\)",
                     p.counterexample), p.counterexample
    assert " at 0x" not in p.counterexample
