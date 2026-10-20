# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bare tolerance declared on `==` belongs to the computation line
only. The mathematics line is exact equality: an exact gap smaller than
the tolerance falsifies the claim there, with the executed witness, on
derive and on an exhaustive sweep alike. The computation line (the
probe route) still compares the floats within the declared tolerance.
"Close enough mathematically" is `~=`."""
from mathema.conjecture import check_conjectures, claim


def close_fn(x: float) -> float:
    return x + 1e-6


def just_above(x: float) -> float:
    return x + 1e-10


def identity(x: float) -> float:
    return x


def swept_close(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + 1e-6


def _v(fn, law, route, tolerance):
    (p,) = check_conjectures(fn, [claim(law, route=route,
                                        tolerance=tolerance)])
    return p


def test_an_exact_gap_inside_the_tolerance_falsifies_the_mathematics():
    # exactly f(x) - x = 1/10**6, nonzero at every x, inside 1e-3
    for route in ("derive", "best"):
        p = _v(close_fn, "for x in [0, 10], f(x) == x", route, 1e-3)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample, (route, p)
        assert p.meta.get("mathema.corroboration") == "reproduced", \
            (route, p.meta)


def test_a_gap_below_the_default_allowance_falsifies_under_a_tolerance():
    # exactly f(x) - x = 1/10**10, inside the declared 1e-9
    p = _v(just_above, "for x in [0, 1], f(x) == x", "best", 1e-9)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "mathema bug" not in (p.note or "")


def test_an_exhaustive_sweep_reads_equality_exactly_under_a_tolerance():
    # 1e-6 in the body is 1/10**6 as written: f(1) = 1 + 1/10**6
    p = _v(swept_close, "for x in {1, 2}, f(x) == x", "best", 1e-3)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route
    assert "exact arithmetic" in p.counterexample, p.counterexample


def test_an_exact_equality_is_still_proven_under_a_tolerance():
    p = _v(identity, "for x in [0, 10], f(x) == x", "best", 1e-3)
    assert p.verdict == "proven", (p.verdict, p.note)


def test_the_computation_line_keeps_the_declared_tolerance():
    p = _v(close_fn, "for x in [0, 10], f(x) == x", "probe", 1e-3)
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "within the tolerance (declared 0.001)" in p.note, p.note
