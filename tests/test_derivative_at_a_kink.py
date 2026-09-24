# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derivative claim is proven only where the function is
differentiable.

sympy differentiates `Abs(x)` to `sign(x)` and a branch to the branch
derivatives, both of which have a value at the kink or the jump
(`sign(0) == 0`) where the derivative itself does not exist. A claim
about the derivative at such a point, or over a domain containing one,
is not proven.
"""
from mathema.conjecture import check_conjectures, claim


def absolute(x: float) -> float:
    return abs(x)


def step_up(x: float) -> float:
    if x < 0:
        return 0.0
    return 1.0


def relu(x: float) -> float:
    if x > 0:
        return x
    return 0.0


def square(x: float) -> float:
    return x * x


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_no_derivative_at_a_kink():
    for fn, law in ((absolute, "d(f(x), x)@{x=0} == 0"),
                    (relu, "d(f(x), x)@{x=0} == 0"),
                    (relu, "d(f(x), x)@{x=0} == 1"),
                    (step_up, "d(f(x), x)@{x=0} == 0")):
        p = _v(fn, law)
        assert p.verdict != "proven", (fn.__name__, law, p.sketch)


def test_a_derivative_away_from_the_kink_still_proves():
    for fn, law in ((absolute, "d(f(x), x)@{x=2} == 1"),
                    (relu, "d(f(x), x)@{x=-1} == 0"),
                    (step_up, "d(f(x), x)@{x=3} == 0"),
                    (square, "d(f(x), x)@{x=3} == 6")):
        p = _v(fn, law)
        assert p.verdict == "proven", (fn.__name__, law, p.sketch)


def test_a_domain_containing_the_kink_is_not_proven():
    for fn, law in ((relu, "for x in [-1, 1], d(f(x), x) >= 0"),
                    (absolute, "for x in [-1, 1], d(f(x), x) >= -1"),
                    (step_up, "for x in [-1, 1], d(f(x), x) == 0")):
        p = _v(fn, law)
        assert p.verdict != "proven", (fn.__name__, law, p.sketch)


def test_a_domain_clear_of_the_kink_still_proves():
    for fn, law in ((relu, "for x in [0.5, 2], d(f(x), x) == 1"),
                    (absolute, "for x in [1, 2], d(f(x), x) == 1"),
                    (step_up, "for x in [1, 2], d(f(x), x) == 0")):
        p = _v(fn, law)
        assert p.verdict == "proven", (fn.__name__, law, p.sketch)


def test_a_kink_on_the_domain_boundary_is_not_proven():
    """On `[-1, 0]` the domain settles relu's branch and fixes the sign
    of x, but relu and |x| are still not differentiable at 0, which the
    domain contains."""
    for fn, law in ((relu, "for x in [-1, 0], d(f(x), x) == 0"),
                    (absolute, "for x in [-1, 0], d(f(x), x) == -1")):
        p = _v(fn, law)
        assert p.verdict != "proven", (fn.__name__, law, p.sketch)
    p = _v(relu, "for x in [-1, 0), d(f(x), x) == 0")
    assert p.verdict == "proven", p.sketch
