# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The rounding watch reads the Decimal methods a point's computation
calls through a profiler, which every call then pays for. A body that
cannot reach Decimal (its module does not import it, and no code it
reaches names it) runs with the profiler it had: the watch costs it
nothing. A Decimal such a body returns anyway (from a module it calls
into, an object's method) came from a run nobody read, and is not
counted. This module imports no decimal itself."""
import sys
import time

import pytest

import tests._decimal_helper as dec_helper
from mathema._decimal_rounding import may_touch_decimal
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


CALC = dec_helper.Calc()


def via_module_attr(x: int):
    return dec_helper.root_squared(x)


def via_object(x: int):
    return CALC.root_squared(x)


@pytest.mark.parametrize("fn", [via_module_attr, via_object])
@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_decimal_from_a_run_not_read_is_not_counted(fn, route):
    # sqrt(n) ** 2 == n is true; 1.999396 at x = 2 is a 4-digit context's
    # rounding inside the helper, which the run did not watch
    (p,) = check_conjectures(fn, [claim("for x in {2, 3}, f(x) == x",
                                        route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample)


def test_the_reach_of_a_wide_dispatcher_is_answered_quickly():
    # a dispatcher naming 3000 functions: the walk stops at its node cap
    # and the answer is kept, so a second asking costs a lookup
    env: dict = {}
    for i in range(3000):
        exec(f"def leaf_{i}(x):\n    return x + {i}", env)
    names = ", ".join(f"leaf_{i}" for i in range(3000))
    exec(f"def dispatch(x, k):\n    return [{names}][k](x)", env)
    may_touch_decimal(env["dispatch"])
    start = time.perf_counter()
    may_touch_decimal(env["dispatch"])
    assert time.perf_counter() - start < 0.05
