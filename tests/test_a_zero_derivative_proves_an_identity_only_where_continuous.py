# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A difference whose derivative is zero is constant only on a connected
set where it is continuous and defined. Across a pole or a branch cut
it can jump, so an identity like `atan(tan(x)) == x` holds on
`[-1, 1]` but not on `[0, 3]`, and `atan2(y, x) == atan(y / x)` holds
for positive `x` but not across the negative x axis."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def atan_of_tan(x: float) -> float:
    return math.atan(math.tan(x))


def angle(x: float, y: float) -> float:
    return math.atan2(y, x)


def atan_and_reciprocal(x: float) -> float:
    return math.atan(x) + math.atan(1 / x)


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_an_identity_across_a_pole_of_tan_is_not_proven():
    # tan has a pole at pi/2 inside [0, 3]; atan(tan(3)) = 3 - pi.
    assert _one(atan_of_tan, "for x in [0, 3], f(x) == x").verdict != "proven"


@pytest.mark.needs_full_proof_budget
def test_the_same_identity_away_from_the_pole_is_proven_by_its_derivative():
    p = _one(atan_of_tan, "for x in [-1, 1], f(x) == x")
    assert p.verdict == "proven"
    assert "derivative" in p.sketch
    assert ".equals()" not in p.sketch


def test_atan2_is_not_atan_of_the_ratio_across_the_negative_axis():
    p = _one(angle, "for x in [-3, 3], y in [-3, 3], f(x, y) == atan(y/x)")
    assert p.verdict != "proven"


@pytest.mark.needs_full_proof_budget
def test_atan2_is_atan_of_the_ratio_in_the_right_half_plane():
    p = _one(angle, "for x in [0.5, 3], y in [-3, 3], f(x, y) == atan(y/x)")
    assert p.verdict == "proven"


def test_a_reciprocal_identity_across_zero_is_not_proven():
    # atan(x) + atan(1/x) is pi/2 for x > 0 and -pi/2 for x < 0.
    p = _one(atan_and_reciprocal, "for x in [-3, 3] \\ {0}, f(x) == pi/2")
    assert p.verdict != "proven"


@pytest.mark.needs_full_proof_budget
def test_a_reciprocal_identity_on_one_side_of_zero_is_proven():
    p = _one(atan_and_reciprocal, "for x in [0.5, 3], f(x) == pi/2")
    assert p.verdict == "proven"
