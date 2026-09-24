# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`f =:= g` is behaviour equivalence. At a point where both sides raise
the same exception type, the two behave the same and agree. Where they
raise different exception types, they disagree, and the executed pair is
the witness. The symbolic rung proves the equivalence when the closed
forms agree wherever both return and both sides raise the same exception
on the same region."""
import math

from mathema.conjecture import check_conjectures, claim


def recip(x: float) -> float:
    return 1 / x


def recip_scaled(x: float) -> float:
    return 2 / (2 * x)


def recip_value_error(x: float) -> float:
    if x == 0:
        raise ValueError("x is zero")
    return 1 / x


def log_plain(x: float) -> float:
    return math.log(x)


def log_halved_doubled(x: float) -> float:
    return 2 * math.log(x) / 2


def recip_shifted(x: float) -> float:
    return 1 / (x - 0.5)


def gap_recip(x: float, y: float) -> float:
    return 1 / (x - y)


def gap_recip_scaled(x: float, y: float) -> float:
    return 2 / (2 * x - 2 * y)


def gap_recip_value_error(x: float, y: float) -> float:
    if x == y:
        raise ValueError("x equals y")
    return 1 / (x - y)


def _eq(f, g, domain, route="best"):
    (p,) = check_conjectures(f, [claim(f"for {domain}, f =:= g",
                                       funcs={"g": g}, route=route)])
    return p


def test_same_raise_region_and_same_exception_is_proven():
    p = _eq(recip, recip_scaled, "x in [-1, 1]")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "derive"
    assert "ZeroDivisionError" in (p.sketch or "")


def test_a_domain_error_raised_alike_on_both_sides_is_proven():
    p = _eq(log_plain, log_halved_doubled, "x in [-1, 1]")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_different_exception_types_at_the_same_point_falsify():
    p = _eq(recip, recip_value_error, "x in [-1, 1]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "f raised ZeroDivisionError" in p.counterexample
    assert "g raised ValueError" in p.counterexample


def test_raise_regions_that_differ_are_not_proven():
    p = _eq(recip, recip_shifted, "x in [-1, 1]")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_sampling_counts_a_shared_raise_as_agreement():
    p = _eq(gap_recip, gap_recip_scaled, "x in [-1, 1], y in [-1, 1]",
            route="probe")
    assert p.verdict == "holds", (p.verdict, p.note)
    sampling = p.meta["mathema.equivalence.sampling"]
    assert sampling.get("both_raised", 0) > 0
    assert "not_compared" not in sampling.get("discarded", {})


def test_sampling_falsifies_different_exception_types():
    p = _eq(gap_recip, gap_recip_value_error, "x in [-1, 1], y in [-1, 1]",
            route="probe")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "f raised ZeroDivisionError" in p.counterexample
    assert "g raised ValueError" in p.counterexample
