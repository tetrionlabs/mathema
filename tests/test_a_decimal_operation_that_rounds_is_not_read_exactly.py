# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A Decimal built from exact arguments is exact, and so are the
operations that keep it exact (addition, subtraction, multiplication,
comparison). A Decimal operation that rounds to the context's precision
(a division, a square root) computes another number than the
mathematics, and a Decimal result is no float64 value: a point where one
rounds is neither read exactly nor credited within float64's precision.
It is not counted, and a claim resting on such points alone is
unknown."""
from decimal import Decimal

from mathema.conjecture import check_conjectures, claim

ROUNDED = "a Decimal operation rounded; the exact reading declined"


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


def _unknown_for_rounding(p):
    said = f"{p.note or ''} {p.sketch or ''}"
    assert p.verdict == "unknown" and ROUNDED in said, \
        (p.verdict, p.route, p.note, p.sketch)


def test_a_false_claim_on_a_rounded_division_is_unknown():
    # Decimal(1) / 3 * 3 is 0.9999999999999999999999999999 in the default
    # context, below 1, yet 1/3 * 3 is exactly 1: f(x) < x is false, and
    # the rounded value is the only evidence for it
    _unknown_for_rounding(_v(third_back, "for x in {1, 4}, f(x) < x"))


def test_a_false_claim_on_a_rounded_square_root_is_unknown():
    # sqrt(n) ** 2 is exactly n, so f(x) != x is false
    _unknown_for_rounding(_v(root_squared, "for x in {2, 3, 5}, f(x) != x"))


def test_a_true_claim_on_a_rounded_division_is_unknown():
    # 1/3 * 3 == 1 is true, but the rounded value 0.999... is no reading
    # of it, exact or within float64
    _unknown_for_rounding(_v(third_back, "for x in {1, 4}, f(x) == x"))


def test_a_true_claim_on_a_rounded_square_root_is_unknown():
    _unknown_for_rounding(_v(root_squared, "for x in {2, 3, 5}, f(x) == x"))


def test_exact_decimal_arithmetic_is_still_proven_exactly():
    # 0.1 n + n - 1 is exactly 11n/10 - 1
    p = _v(tenths, "for n in {0, 1, 7}, f(n) == 11 * n / 10 - 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route, p.sketch)


def test_a_point_where_no_decimal_operation_rounds_still_falsifies():
    # 3/3 * 3 is exactly 3 with no rounding, and 3 < 3 is false
    p = _v(third_back, "for x in {1, 3}, f(x) < x")
    assert p.verdict == "falsified" and "x = 3" in (p.counterexample or ""), \
        (p.verdict, p.route, p.counterexample)
