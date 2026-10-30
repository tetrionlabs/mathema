# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value the code returns exactly (a Fraction, an int too large for a
float) is compared with the claim's own side read exactly, its literals
as written: `n + 1/3` is the rational it says, never the float nearest
it. A gap the record states between such
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
    # the code returns exactly n + 1/3, and the body is read exactly
    p = _v(third, "for n in {0, 1}, f(n) == n + 1/3")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route, p.counterexample)


def test_a_ground_fraction_result_equals_the_claim_read_exactly():
    p = _v(third, "f(2) == 2 + 1/3")
    assert p.verdict == "proven", (p.verdict, p.route, p.counterexample)


def test_a_fraction_result_exactly_above_a_float_literal_falsifies():
    # 0.3333333333333333 as written is 3333333333333333/10**16 < 1/3:
    # exactly f(n) exceeds it by 1/(3 * 10**16) at every n
    for route in ("probe", "best"):
        p = _v(third, "for n in [0, 10] subset Z, f(n) <= n + 0.3333333333333333",
               route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)


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
