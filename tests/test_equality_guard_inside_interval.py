# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard `x == c` or `x != c` with `c` strictly inside an interval
domain is live: it is true at one point and false everywhere else, so
the branch it guards is part of the function over that domain. Only the
ordering comparisons are decided by their value at the two endpoints."""
import pytest

from mathema.conjecture import check_conjectures, claim


def spike(x: float) -> float:
    if x == 1:
        return 10.0
    return x


def spike_ne(x: float) -> float:
    if x != 1:
        return x
    return 10.0


def spike_int(n: int) -> int:
    if n == 4:
        return -1
    return n


@pytest.mark.parametrize("fn", [spike, spike_ne])
def test_a_point_guard_inside_the_interval_is_not_pruned(fn):
    (p,) = check_conjectures(fn, [claim("for x in [0, 3], f(x) == x",
                                        route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)


@pytest.mark.parametrize("fn", [spike, spike_ne])
def test_a_point_guard_outside_the_interval_is_still_decided(fn):
    (p,) = check_conjectures(fn, [claim("for x in [2, 3], f(x) == x",
                                        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_an_integer_point_guard_is_not_pruned():
    (p,) = check_conjectures(spike_int, [claim("for n in [0, 10] ⊂ Z, f(n) >= 0",
                                               route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
