# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`f(x) != g(x)` is proven only when the difference is never zero
anywhere in the domain, closed endpoints included. A difference that is
merely `<= 0` (zero at an endpoint, or a product with a factor that can
be zero) is not a proof, and the probe route agrees once the endpoint is
sampled."""
import pytest

from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


def neg(x: float) -> float:
    return -x


def product(x: float, y: float) -> float:
    return x * (y + 1)


@pytest.mark.parametrize("fn,law", [
    (ident, "for x in [0, 1], f(x) != 0"),
    (neg, "for x in [0, 1], f(x) != 0"),
    (ident, "for x in [-1, 0], f(x) != 0"),
    (product, "for x in [0, 1], y in [1, 2], f(x, y) != 0"),
])
def test_a_zero_at_a_closed_endpoint_is_never_proven_nonzero(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)


@pytest.mark.parametrize("fn,law", [
    (ident, "for x in [1, 2], f(x) != 0"),
    (neg, "for x in [1, 2], f(x) != 0"),
    (product, "for x in [1, 2], y in [1, 2], f(x, y) != 0"),
])
def test_a_difference_bounded_away_from_zero_is_proven(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_the_endpoint_zero_is_found_by_the_best_route():
    (p,) = check_conjectures(ident, [claim("for x in [0, 1], f(x) != 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample
