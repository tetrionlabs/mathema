# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Sequence draws include the corners where float arithmetic breaks:
entries that cancel at a large magnitude ([1e16, -1e16]), entries near
the largest double, and a nearly constant series one ulp from
constant, the cases a uniform draw almost never makes. A draw that
passes only within the tolerance there is decided in exact arithmetic
(rulings of 2026-10-01 and 2026-10-05: the corners are turned on with
the strata work, the mathematics is exact, tolerance belongs to the
computation)."""
import math

import numpy as np

from mathema.conjecture import check_conjectures, claim


def running_total(xs: list, y0: float) -> float:
    y = y0
    for v in xs:
        y = y + v
    return y


def middle(xs: np.ndarray) -> float:
    return float(np.percentile(xs, 50))


def signal_to_noise(xs: list) -> float:
    m = sum(xs) / len(xs)
    var = sum((v - m) ** 2 for v in xs) / (len(xs) - 1)
    return m / math.sqrt(var)


def test_a_cancelling_pair_is_drawn_and_decided_exactly():
    # the shift is exact mathematics; at [1e16, -1e16, ...] the float
    # sum is off by 1, which passes within that draw's round-off only
    # because the code run on exact numbers satisfies the claim there
    (p,) = check_conjectures(running_total, [claim(
        "for xs in R^n, y0 in [-10, 10], f(xs, y0 + 1) == f(xs, y0) + 1",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "at xs = [1e+16, -1e+16" in p.note, p.note


def test_entries_near_the_float_limit_break_a_range_claim():
    (p,) = check_conjectures(middle, [claim(
        "for xs in [-1.7e308, 1.7e308]^n, min(xs) <= f(xs) <= max(xs)",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_nearly_constant_series_meets_a_std_premise():
    # a series one ulp from constant passes `std > 0` and has an
    # enormous mean-to-deviation ratio; the square root keeps it from
    # being evaluated exactly, so those draws are inconclusive
    (p,) = check_conjectures(signal_to_noise, [claim(
        "for xs in [0.5, 1]^n, assuming n >= 2 and std(xs, ddof=1) > 0, "
        "abs(f(xs)) <= 1e9", route="probe")])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert "could not be evaluated in exact arithmetic" in p.note, p.note


def test_every_corner_entry_lies_in_the_element_range():
    import random

    from mathema.probing import _sequence_corner
    bounds = (1e307, 1.7e308)
    rng = random.Random(0)
    for _ in range(400):
        corner = _sequence_corner(rng, 5, bounds)
        assert corner is not None
        assert all(1e307 <= v <= 1.7e308 for v in corner), corner
