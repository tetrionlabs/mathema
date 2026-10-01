# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A generator passed in as a parameter belongs to the caller, who
expects it to move: drawing from it is not a state change for
is_state_safe, and such a function is reproducible when every draw
comes through that parameter. Drawing from the shared generators
(`random`, `numpy.random`) advances state every other caller sees, and
falsifies is_state_safe with that site named. All of it is read from
the source."""
import random

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

VOLATILITY = 0.01


def simulated_return(mu: float, rng: np.random.Generator) -> float:
    return mu + 0.01 * rng.standard_normal()


def simulated_return_stdlib(mu: float, rng: random.Random) -> float:
    return mu + 0.01 * rng.gauss(0, 1)


def simulated_return_scaled(mu: float, rng: np.random.Generator) -> float:
    return mu + VOLATILITY * rng.standard_normal()


def global_noise(mu: float) -> float:
    return mu + 0.01 * np.random.rand()


def draw_then_reseed(mu: float, rng) -> float:
    value = mu + 0.01 * rng.random()
    random.seed(1)
    return value


def _one(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


@pytest.mark.parametrize("fn", [simulated_return, simulated_return_stdlib,
                                simulated_return_scaled])
def test_a_function_drawing_from_its_own_generator_is_state_safe(fn):
    p = _one(fn, "is_state_safe(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (
        fn.__name__, p.verdict, p.note)


@pytest.mark.parametrize("fn", [simulated_return, simulated_return_stdlib])
def test_it_is_reproducible_through_that_generator(fn):
    p = _one(fn, "is_reproducible(f)")
    assert (p.verdict, p.route) == ("proven", "examine"), (
        fn.__name__, p.verdict, p.note)


def test_a_global_numpy_draw_is_falsified_with_the_site_named():
    p = _one(global_noise, "is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "advances the shared random generator" in p.counterexample


def test_an_unannotated_rng_is_the_callers_and_a_global_write_falsifies():
    p = _one(draw_then_reseed, "is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "random.seed" in p.counterexample
