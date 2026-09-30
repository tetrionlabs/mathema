# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Cases where a policy row, a gate or a value claim once claimed more
than the calls showed: each pins the verdict the calls support."""
from typing import Optional

import pytest

from mathema import analyze
from mathema.conjecture import check_conjectures, claim
from mathema.policy import guard_policies


def _rows(fn, *texts):
    return {r.name: r for r in check_conjectures(fn, [claim(t) for t in texts])}


# --- a guard covers x only when the raise depends on x alone -------------

def raise_unless_y(x: Optional[float], y: float) -> float:
    if x is None and y != 0.125:
        raise TypeError("x is None")
    if x is None:
        return 0.0
    return x + y


def either_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        raise ValueError("x is missing")
    return x


def test_a_guard_that_also_reads_another_parameter_covers_nothing():
    assert ("x", "absent", "None") not in guard_policies(analyze(raise_unless_y))
    gate = _rows(raise_unless_y, "for x in [0, 1], y in [0, 1], f(x, y) >= 0",
                 "is_absent_safe(f)")["is_absent_safe[f]"]
    assert gate.verdict != "proven", gate.note


def test_a_guard_joined_by_or_covers_each_of_its_tests():
    guards = guard_policies(analyze(either_missing))
    assert guards[("x", "absent", "None")][0] == "raises"
    assert guards[("x", "missing", "nan")][0] == "raises"


# --- a library row speaks for a parameter only while the body leaves it be

np = pytest.importorskip("numpy")


def mean_after_fill(xs: np.ndarray) -> float:
    if len(xs) > 20:
        xs = np.nan_to_num(xs)
    return float(np.mean(xs))


def test_no_library_row_is_composed_when_the_body_rebinds_the_parameter():
    from mathema.policy import composed_policies
    assert composed_policies(mean_after_fill, analyze(mean_after_fill)) == {}


# --- a call holding two members keeps its own raise -----------------------

def refuses_two_kinds(xs: list) -> float:
    has_null = any(x is None for x in xs)
    has_nan = any(x is not None and x != x for x in xs)
    if has_null and has_nan:
        raise ValueError("both kinds of hole")
    return sum(x for x in xs if x is not None and x == x)


def test_a_raise_at_two_members_together_is_recorded():
    rows = _rows(refuses_two_kinds, "for xs in [0, 1]^n, f(xs) >= 0",
                 "missing(f, xs) drops", "is_missing_safe(f)")
    assert rows["missing_f_xs_drops"].verdict == "falsified"
    assert rows["missing_f_xs_drops"].counterexample.endswith("f raised ValueError")
    assert rows["is_missing_safe[f]"].verdict == "falsified"
