# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`range(n)` runs `max(n, 0)` times, and only for an integer `n`.

A loop's closed form is a sum over its iterations. Summation's own
convention for a reversed range (`sum_{k=0}^{n-1}` with `n < 0` is the
negated sum over the gap) is not what Python does: `range(n)` with a
negative `n` is empty, so the loop leaves its accumulator at the initial
value. A float `n` raises TypeError, so a claim over a real domain is
false wherever `n` is not a whole number.
"""
import pytest

from mathema.conjecture import check_conjectures, claim


def count_up(n: int) -> int:
    s = 0
    for k in range(n):
        s += 1
    return s


def triangle(n: int) -> int:
    s = 0
    for i in range(1, n + 1):
        s += i
    return s


def odd_sum(n: int) -> int:
    s = 0
    for k in range(1, n, 2):
        s += k
    return s


def doubling(n: int) -> float:
    s = 1.0
    for _ in range(n):
        s = 2.0 * s
    return s


def fib_pair(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def float_count(n: float) -> float:
    s = 0.0
    for k in range(n):
        s += 1.0
    return s


def _verdict(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.parametrize("fn,law", [
    (count_up, "for n in [-10, -1] subset Z, f(n) == n"),
    (count_up, "for n in [-10, 10] subset Z, f(n) == n"),
    (triangle, "for n in [-10, -2] subset Z, f(n) == n*(n+1)/2"),
    (doubling, "for n in [-50, -1] subset Z, f(n) == 2.0**n"),
])
def test_a_negative_trip_count_is_an_empty_loop_not_a_negative_sum(fn, law):
    p = _verdict(fn, law)
    assert p.verdict == "falsified", (law, p.verdict, p.sketch, p.note)


@pytest.mark.parametrize("fn,law", [
    (count_up, "for n in [-10, -1] subset Z, f(n) == 0"),
    (triangle, "for n in [-100000, -2] subset Z, f(n) == 0"),
    (odd_sum, "for n in [-5000, -1] subset Z, f(n) == 0"),
    (doubling, "for n in [-50, -1] subset Z, f(n) == 1"),
    (fib_pair, "for n in [-50, -1] subset Z, f(n) == 0"),
])
def test_an_empty_loop_keeps_its_initial_value(fn, law):
    p = _verdict(fn, law)
    assert p.verdict in ("proven", "holds"), (law, p.verdict, p.sketch,
                                              p.counterexample)


@pytest.mark.parametrize("fn,law", [
    (count_up, "for n in [0, 10] subset Z, f(n) == n"),
    (triangle, "for n in [0, 100] subset Z, f(n) == n*(n+1)/2"),
    (float_count, "for n in [1, 20] subset Z, f(n) == n"),
])
def test_a_nonnegative_trip_count_still_proves(fn, law):
    p = _verdict(fn, law)
    assert p.verdict == "proven", (law, p.verdict, p.sketch, p.note)


def test_a_float_trip_count_raises_so_the_claim_is_false():
    p = _verdict(float_count, "for n in [1, 20], f(n) == n")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "TypeError" in (p.sketch or "") + (p.note or "")


def test_a_corroborating_point_is_called_with_an_integer_on_an_integer_domain():
    """The witness of a disproof over `subset Z` is a whole number, and
    the real function is called with it as an int, the way the probe
    route draws it; `range(-3.0)` raising is no evidence about the
    claim."""
    from mathema.analysis import analyze_source
    from mathema.domain import split_quantifier
    from mathema.gates import _point_evaluator

    cj = claim("for n in [-50, -1] subset Z, f(n) == 1")
    domain, _ = split_quantifier("for n in [-50, -1] subset Z, f(n) == 1")
    deps = _point_evaluator(cj, doubling, analyze_source(doubling), domain,
                            {})
    assert deps["evaluate"]({"n": -3.0}) is True


def compound(P: float, r: float, n: float) -> float:
    balance = P
    for _ in range(n):
        balance = balance * (1 + r)
    return balance


def test_an_unquantified_trip_count_is_not_proven():
    """With no domain on `n`, the claim covers floats (TypeError) and
    negative counts (an empty loop), and is false at both."""
    p = _verdict(compound, "f(P, r, n) == P*(1+r)**n")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    p = _verdict(compound, "for n in [0, 50] subset Z, f(P, r, n) == P*(1+r)**n")
    assert p.verdict == "proven", (p.verdict, p.sketch)
