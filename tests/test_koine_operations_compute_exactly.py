# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The operator families and rounding modes, computed exactly: each
against its definition, and the binary64 cases where the exact and the
rounded quotient part company."""
import math

import pytest
from mathema.koine.functions import (
    cbrt,
    div_euclid,
    div_floor,
    div_trunc,
    power,
    rem_euclid,
    rem_floor,
    rem_trunc,
    round_ties_away,
    round_ties_up,
    sign,
)


@pytest.mark.parametrize("a, b", [(7, 2), (-7, 2), (7, -2), (-7, -2), (6, 3), (0, 5)])
def test_integer_families_satisfy_their_identities(a, b):
    for q, r in ((div_trunc, rem_trunc), (div_floor, rem_floor), (div_euclid, rem_euclid)):
        assert q(a, b) * b + r(a, b) == a
        assert isinstance(q(a, b), int) and isinstance(r(a, b), int)
    assert rem_trunc(a, b) == 0 or (rem_trunc(a, b) > 0) == (a > 0)
    assert rem_floor(a, b) == 0 or (rem_floor(a, b) > 0) == (b > 0)
    assert 0 <= rem_euclid(a, b) < abs(b)


@pytest.mark.parametrize("a, b, trunc, floor, euclid", [
    (-7, 2, -3, -4, -4), (7, -2, -3, -4, -3), (-7, -2, 3, 3, 4), (7, 2, 3, 3, 3),
])
def test_the_three_quotients(a, b, trunc, floor, euclid):
    assert (div_trunc(a, b), div_floor(a, b), div_euclid(a, b)) == (trunc, floor, euclid)


def test_quotients_of_reals_use_the_exact_quotient():
    # 0.1 is slightly more than one tenth, so 1.0 / 0.1 rounds up to 10.0
    # while the exact quotient is just under 10
    assert 1.0 / 0.1 == 10.0
    assert div_floor(1.0, 0.1) == 9.0 == 1.0 // 0.1
    assert div_trunc(1.0, 0.1) == 9.0
    assert rem_floor(1.0, 0.1) == pytest.approx(0.1, rel=1e-15)
    assert rem_trunc(-7.5, 2.0) == -1.5 == math.fmod(-7.5, 2.0)
    assert isinstance(div_trunc(7.0, 2.0), float)


@pytest.mark.parametrize("fn", [div_trunc, div_floor, div_euclid, rem_trunc, rem_floor, rem_euclid])
def test_a_zero_divisor_is_singular(fn):
    with pytest.raises(ZeroDivisionError):
        fn(1, 0)


@pytest.mark.parametrize("x, even, away, up", [
    (2.5, 2, 3, 3), (-2.5, -2, -3, -2), (3.5, 4, 4, 4), (-0.5, 0, -1, 0),
    (0.49999999999999994, 0, 0, 0), (1.2, 1, 1, 1), (-1.7, -2, -2, -2),
])
def test_the_three_ties_modes(x, even, away, up):
    assert (round(x), round_ties_away(x), round_ties_up(x)) == (even, away, up)


def test_power_singular_and_domain():
    with pytest.raises(ZeroDivisionError):
        power(0, -1)
    with pytest.raises(ValueError):
        power(-8.0, 0.5)
    assert power(-8.0, 3) == -512.0


def test_sign_and_cube_root():
    assert (sign(-2.0), sign(0), sign(3)) == (-1, 0, 1)
    assert cbrt(-8.0) == pytest.approx(-2.0)
