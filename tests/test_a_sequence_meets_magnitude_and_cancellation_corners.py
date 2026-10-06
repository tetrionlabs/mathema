# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Sequence draws include the corners where float arithmetic breaks:
entries that cancel at a large magnitude ([1e16, -1e16]), entries near
the largest double, and a nearly constant series one ulp from
constant, the cases a uniform draw almost never makes. A float result
that misses the mathematics there beyond the result's own precision
falsifies the computation line, with the conditioning at the witness in
the note (rulings of 2026-10-01, 2026-10-05 and 2026-10-06 on G94: the
corners are turned on with the strata work, the mathematics is exact,
the absolute part of the allowance never exceeds the relative part of
the result)."""
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


def test_a_cancelling_pair_falsifies_the_computation_with_its_conditioning():
    # the shift is exact mathematics; at [1e16, -1e16, ...] the float
    # sum misses it by about 1, far past the result's precision, a loss
    # the conditioning at the draw explains
    (p,) = check_conjectures(running_total, [claim(
        "for xs in R^n, y0 in [-10, 10], f(xs, y0 + 1) == f(xs, y0) + 1",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "xs = [1e+16, -1e+16" in p.counterexample or \
        "xs = [1e+300, -1e+300" in p.counterexample, p.counterexample
    assert "ill-conditioned here (κ ≈" in p.note, p.note
    assert p.meta["mathema.conditioning"]["inherent"] is True


def test_entries_near_the_float_limit_break_a_range_claim():
    (p,) = check_conjectures(middle, [claim(
        "for xs in [-1.7e308, 1.7e308]^n, min(xs) <= f(xs) <= max(xs)",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_nearly_constant_series_meets_a_std_premise():
    # a series one ulp from constant passes `std > 0` and has a
    # mean-to-deviation ratio near 1e16, so the bound of 1e9 is false
    # there in exact arithmetic as in float: falsified at that series
    (p,) = check_conjectures(signal_to_noise, [claim(
        "for xs in [0.5, 1]^n, assuming n >= 2 and std(xs, ddof=1) > 0, "
        "abs(f(xs)) <= 1e9", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.counterexample)
    import re
    m = re.search(r"xs = \[([^\]]*)\]", p.counterexample)
    values = [float(v) for v in m.group(1).split(",")]
    assert len(set(values)) == 2 and \
        math.nextafter(min(values), 2.0) == max(values), values


def test_every_corner_entry_lies_in_the_element_range():
    import random

    from mathema.probing import _sequence_corner
    bounds = (1e307, 1.7e308)
    rng = random.Random(0)
    for _ in range(400):
        corner = _sequence_corner(rng, 5, bounds)
        assert corner is not None
        assert all(1e307 <= v <= 1.7e308 for v in corner), corner
