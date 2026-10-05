# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exact disproof witness (an irrational root, say) has no float of
its own: the nearest float may still satisfy the claim while one a
single ulp away breaks it. `-(x^3 - 3x + 1)^2 < 0` fails over the reals
at the root near 0.3472963553338607; the float there gives a tiny
negative value, and the float one ulp below gives `-0.0`, which is not
below zero. The claim is falsified with that float as its witness."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.corroboration import _seed_points


def negated_square(x: float) -> float:
    return -(x ** 3 - 3 * x + 1) ** 2


def test_the_seeds_include_floats_a_few_ulps_either_side():
    nearest = 0.3472963553338607
    seeds = [p["x"] for p in _seed_points({"x": nearest}, ["x"])]
    below = math.nextafter(nearest, 0.0)
    above = math.nextafter(nearest, 1.0)
    assert below in seeds and above in seeds
    assert math.nextafter(math.nextafter(math.nextafter(below, 0.0), 0.0), 0.0) in seeds


@pytest.mark.needs_full_proof_budget
def test_a_strict_claim_failing_at_an_irrational_root_is_falsified():
    (p,) = check_conjectures(negated_square, [claim("for x in [0, 1], f(x) < 0")],
                             extensive=True)
    assert p.verdict == "falsified"
    x = float(p.counterexample.split("=")[1])
    assert abs(x - 0.3472963553338607) < 1e-6
    assert p.meta.get("mathema.corroboration") == "reproduced"
