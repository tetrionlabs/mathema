# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value the code returns exactly (a Fraction, an int too large for a
float) is compared with the claim's own side read exactly, its literals
as written: `n + 1/3` is the rational it says, never the float nearest
it. Where the body itself is not read exactly, that comparison is the
computation's: an exact value equal to the claim proves within float64
(nothing rounded), and one that misses it is no rounding float64
explains, so nothing is proven. A gap the record states between such
values is their exact difference, never the infinity a float conversion
overflows to."""
from fractions import Fraction

from mathema.conjecture import check_conjectures, claim


def third(n: int) -> Fraction:
    return Fraction(1, 3) + n


def huge(n: int) -> int:
    return 10 ** 400 + n


def _v(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def test_a_fraction_result_equals_the_claim_read_exactly():
    # the code returns exactly n + 1/3; the body's Fraction is not read
    # by the exact reading, so the proof is capped at within_float64
    p = _v(third, "for n in {0, 1}, f(n) == n + 1/3")
    assert p.verdict == "proven", (p.verdict, p.route, p.counterexample)
    precision = p.meta["mathema.sweep_precision"]["precision"]
    assert precision["bound"] == 0.0 and precision["factor"] == 8, precision


def test_a_ground_fraction_result_equals_the_claim_read_exactly():
    p = _v(third, "f(2) == 2 + 1/3")
    assert p.verdict == "proven", (p.verdict, p.route, p.counterexample)


def test_a_fraction_result_exactly_above_a_float_literal_is_not_proven():
    # 0.3333333333333333 as written is 3333333333333333/10**16 < 1/3:
    # the returned value misses by 1/(3 * 10**16), which no float64
    # rounding explains
    for route in ("probe", "best"):
        p = _v(third, "for n in [0, 10] subset Z, f(n) <= n + 0.3333333333333333",
               route)
        assert p.verdict in ("unknown", "falsified"), (route, p.verdict, p.note)


def test_a_huge_int_pass_states_no_infinite_gap():
    # f(n) = 10**400 + n <= 10**400 + 10 holds outright at every n
    p = _v(huge, "for n in [0, 10] subset Z, f(n) <= 10**400 + 10", "probe")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "inf" not in (p.note or ""), p.note


def test_a_huge_int_miss_is_stated_by_its_exact_difference():
    # f(n) - (n + 10**400 + 1) = -1 exactly
    p = _v(huge, "for n in [0, 10] subset Z, f(n) == n + 10**400 + 1")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "by inf" not in (p.note or ""), p.note
