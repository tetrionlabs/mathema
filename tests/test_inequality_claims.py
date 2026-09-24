# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `!=` claim is falsified only where its two sides are actually
equal. The default comparison tolerance absorbs floating-point
representation error in favour of an equality holding; it never turns
two different values into a counterexample for an inequality."""
from mathema.conjecture import check_conjectures, claim
from mathema.probing import relation_holds_elementwise


def bump(x: float) -> float:
    return 1 / (1 + x * x)


def nudged(x: float) -> float:
    return x + 0.001


def flat(x: float) -> float:
    return x * 0.0


def test_a_tiny_nonzero_value_is_not_a_counterexample_on_the_probe_route():
    (p,) = check_conjectures(bump, [claim("f(x) != 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_small_gap_at_large_magnitude_is_not_a_counterexample():
    (p,) = check_conjectures(nudged, [claim("f(x) != x", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_genuine_equality_still_falsifies():
    (p,) = check_conjectures(flat, [claim("f(x) != 0", route="probe")])
    assert p.verdict == "falsified"


def test_the_default_inequality_compares_exactly():
    assert relation_holds_elementwise(1e-12, 0.0, "!=", 1e-9,
                                      exact_inequality=True)
    assert relation_holds_elementwise(1e6 + 1e-3, 1e6, "!=", 1e-9,
                                      exact_inequality=True)
    assert not relation_holds_elementwise(2.0, 2.0, "!=", 1e-9,
                                          exact_inequality=True)
    # a declared tolerance still means what it says
    assert not relation_holds_elementwise(1e-12, 0.0, "!=", 1e-9)
