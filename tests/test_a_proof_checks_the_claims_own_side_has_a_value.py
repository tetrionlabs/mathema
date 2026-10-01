# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A proof covers every point of the claim's domain, and the claim's
own expression must have a real value at each of them. `f(x) + 1/x**2`
has none at x = 0, and `(f(x) + x**2)/x**2` cancels to `x + 1` only
away from 0, so neither claim over [-1, 1] is proven; both are
falsified at x = 0, where the claim's side has no real value."""
from mathema.conjecture import check_conjectures, claim


def sq(x: float) -> float:
    return x * x


def cube(x: float) -> float:
    return x ** 3


def zero(x: float) -> float:
    return 0.0


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_a_claim_side_pole_in_the_domain_falsifies_the_claim():
    for fn, law in ((sq, "for x in [-1, 1], f(x) + 1/x**2 >= 0"),
                    (cube, "for x in [-1, 1], (f(x) + x**2)/x**2 >= 0")):
        p = _one(fn, law)
        assert p.verdict == "falsified", law
        assert "no real value" in p.counterexample, law
        head = p.counterexample.split(":")[0].strip("()")
        assert float(head.split("=")[-1]) == 0.0, law


def test_a_claim_side_root_of_a_negative_is_not_proven():
    p = _one(zero, "for x in [-1, 1], f(x) <= sqrt(x) + 1")
    assert p.verdict != "proven"


def test_a_claim_side_with_a_value_everywhere_still_proves():
    assert _one(sq, "for x in [0.5, 1], f(x) + 1/x**2 >= 0").verdict == "proven"
    assert _one(zero, "for x in [0.5, 1], f(x) <= sqrt(x)").verdict == "proven"
    assert _one(sq, "for x in [-1, 1], f(x) + 1/(x**2 + 1) >= 0").verdict == "proven"
