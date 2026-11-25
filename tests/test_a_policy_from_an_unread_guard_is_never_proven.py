# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing-value policy is proven from a guard only when the path to
the guard's raise was read: the guard is taken at the hole, and nothing
before it can return or raise something else first. A guard behind a
test that may return first leaves the policy at holds, whether the
policy names the class it raises or not."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def returns_first_on_a_rare_value(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        return y
    if x is None:
        raise TypeError("x is required")
    return x * y


def guard_first(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def _policy_row(fn, statement: str):
    rows = check_conjectures(fn, [claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
                                  claim(statement)])
    return rows[-1]


@pytest.mark.parametrize("statement", ["absent(f, x) raises",
                                       "absent(f, x) raises(TypeError)"])
def test_a_policy_behind_a_test_that_may_return_first_is_not_proven(statement):
    assert returns_first_on_a_rare_value(None, 0.123456) == 0.123456
    row = _policy_row(returns_first_on_a_rare_value, statement)
    assert row.verdict == "holds", (row.verdict, row.route, row.note)


@pytest.mark.parametrize("statement", ["absent(f, x) raises",
                                       "absent(f, x) raises(TypeError)"])
def test_a_policy_from_a_guard_read_from_the_entry_is_proven(statement):
    row = _policy_row(guard_first, statement)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
