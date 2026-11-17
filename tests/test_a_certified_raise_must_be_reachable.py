# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise guard certified by interval arithmetic falsifies a claim only
where the raising branch can actually run: an exponent the claim fixes to
an integer leaves no negative-base region, and a loop index only takes the
values its range gives it."""
import math

import pytest

import mathema
from mathema.claims import check_conjectures, claim


def power(r, n):
    return r ** n


def power_int(r: float, n: int) -> float:
    return r ** n


def one(n: int) -> float:
    return 1.0


def loop_sum(k: int) -> float:
    total = 0
    for j in range(k + 1):
        total += math.factorial(k - j)
    return total


def sqrt_just_above(x: float) -> float:
    return math.sqrt(x - (0.3 + 1e-20))


def _verdict(fn, law, funcs=None):
    c = claim(law, name=None, route="derive", funcs=funcs or {}, tolerance=None)
    return check_conjectures(fn, [c], extensive=False)[0]


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law", [
    "for r in [-2,2], f(r,2) == r*r",
    "for r in [-2,2], f(r,0) == 1",
    "for r in [-2,2], f(r,3) == f(r,3)",
])
@pytest.mark.parametrize("fn", [power, power_int])
def test_a_pinned_integer_exponent_has_no_negative_base_region(fn, law):
    r = _verdict(fn, law)
    assert r.verdict == "proven", (r.verdict, r.note)


@pytest.mark.needs_full_proof_budget
def test_a_loop_index_outside_its_range_is_not_a_raise_witness():
    r = _verdict(one, "for n in [5,15] ⊂ Z, f(n) == 1 + g(3) - g(3)",
                 {"g": loop_sum})
    assert r.verdict == "proven", (r.verdict, r.note)


@pytest.mark.needs_full_proof_budget
def test_the_same_loop_claim_on_a_single_point_domain_is_not_falsified():
    r = _verdict(one, "for n in [5,5] ⊂ Z, f(n) == 1 + g(3) - g(3)",
                 {"g": loop_sum})
    assert r.verdict == "proven", (r.verdict, r.note)


def test_a_reachable_certified_guard_still_falsifies():
    (p,) = [p for p in mathema.check(
        sqrt_just_above,
        claims=[mathema.claim("for x in [0.3, 1], f(x) >= 0", name="c")]).probes
        if p.name == "c"]
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "certified by interval arithmetic" in p.note
