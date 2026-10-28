# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A Decimal built from exact arguments is exact, and so are the
operations that keep it exact (addition, subtraction, multiplication,
comparison, an integer power within the context's precision). A Decimal
operation that rounds to the context's precision (a division, a square
root) computes another number than the mathematics: the exact reading
declines such a point, so a claim resting on it is never proven exactly
from the rounded value."""
from decimal import Decimal

from mathema.conjecture import check_conjectures, claim


def third_back(x: int):
    i = 0
    while i < 3:
        i += 1
    return Decimal(x) / Decimal(3) * 3


def root_squared(x: int):
    i = 0
    while i < 3:
        i += 1
    return Decimal(x).sqrt() ** 2


def tenths(n: int):
    i = 0
    while i < 3:
        i += 1
    return Decimal("0.1") * n + Decimal(n) - 1


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_a_decimal_division_that_rounds_is_not_proven_exactly():
    # Decimal(1) / 3 * 3 is 0.9999999999999999999999999999 in the default
    # context, below 1, yet the mathematics 1/3 * 3 is exactly 1: the
    # claim f(x) < x is false read exactly
    p = _v(third_back, "for x in {1, 4}, f(x) < x")
    assert p.route != "derive:brute_force" or p.verdict != "proven", \
        (p.verdict, p.route, p.sketch)


def test_a_decimal_square_root_that_rounds_is_not_proven_exactly():
    # sqrt(2) ** 2 is exactly 2, so f(x) != x is false read exactly
    p = _v(root_squared, "for x in {2, 3, 5}, f(x) != x")
    assert p.route != "derive:brute_force" or p.verdict != "proven", \
        (p.verdict, p.route, p.sketch)


def test_exact_decimal_arithmetic_is_still_proven_exactly():
    # 0.1 n + n - 1 is exactly 11n/10 - 1
    p = _v(tenths, "for n in {0, 1, 7}, f(n) == 11 * n / 10 - 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route, p.sketch)
