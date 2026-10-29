# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The rounding watch reads the Decimal methods a point's computation
calls through a profiler, which every call then pays for. A body that
cannot reach Decimal (its module does not import it, and no code it
reaches names it) runs with the profiler it had: the watch costs it
nothing. This module imports no decimal itself."""
import sys

import pytest

from mathema.conjecture import check_conjectures, claim

_PROFILERS: list = []


def plain_float(x: float) -> float:
    _PROFILERS.append(sys.getprofile())
    i = 0
    while i < 3:
        i += 1
    return x * 0.5


@pytest.mark.parametrize("law", ["for x in {0.5, 1.5}, f(x) == x / 2",
                                 "for x in [0, 1], f(x) <= x"])
@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_body_that_never_touches_decimal_runs_with_no_profiler(law, route):
    outer = sys.getprofile()
    _PROFILERS.clear()
    check_conjectures(plain_float, [claim(law, route=route)])
    assert _PROFILERS, "the body never ran"
    assert all(p is outer for p in _PROFILERS), _PROFILERS[:3]
