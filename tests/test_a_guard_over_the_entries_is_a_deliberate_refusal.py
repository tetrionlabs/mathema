# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard that checks each entry of a sequence and raises on a hole
(`for v in xs: if math.isnan(v): raise`, or `if any(math.isnan(v) for
v in xs): raise`) is the function refusing a missing value on purpose,
as the same guard on a scalar is, so `is_missing_safe(f)` reads it as
the policy. A raise the body stumbles into at a hole is not a guard
and still falsifies, even where a guard for the same hole with the same
exception sits after it."""
import math

from mathema.conjecture import check_conjectures, claim


def loop_guard(xs: list[float]) -> float:
    for v in xs:
        if math.isnan(v):
            raise ValueError("a hole in xs")
    return sum(xs)


def any_guard(xs: list[float]) -> float:
    if any(math.isnan(v) for v in xs):
        raise ValueError("a hole in xs")
    return sum(xs)


def stumbles(xs: list[float]) -> float:
    return float(sum(int(v) for v in xs))


def late_loop_guard(xs: list[float]) -> float:
    t = 0
    for v in xs:
        t += int(v)
        if math.isnan(v):
            raise ValueError("a hole in xs")
    return float(t)


def late_guard(x: float) -> float:
    t = int(x)
    if math.isnan(x):
        raise ValueError("x is a hole")
    return float(t)


def _missing(fn):
    (p,) = check_conjectures(fn, [claim("is_missing_safe(f)")])
    return p


def test_a_loop_guard_over_the_entries_is_the_policy():
    p = _missing(loop_guard)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    assert "from the guard on line 3" in (p.note or ""), p.note


def test_a_generator_guard_over_the_entries_is_the_policy():
    p = _missing(any_guard)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    assert "from the guard on line 2" in (p.note or ""), p.note


def test_a_raise_the_body_stumbles_into_still_falsifies():
    p = _missing(stumbles)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "no claim says it may" in (p.note or ""), p.note


def test_a_raise_before_the_guard_is_not_the_guard_s():
    # int(nan) raises ValueError before the guard is reached: the
    # exception matches the guard's, but the guard did not raise it
    for fn in (late_guard, late_loop_guard):
        p = _missing(fn)
        assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
        assert "from the guard" not in (p.note or ""), p.note
