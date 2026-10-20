# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sweep of every point of a finite domain proves a claim only when
the claim holds at every point exactly: `==` as exact equality, `~=` as
`abs(a - b) <= ε`, with the function run on each point's exact value
(the number as written) and the claim's own literals exact. The float
computation's allowance belongs to the computation line, so a gap the
allowance absorbs never reaches a proof.

- A point whose exact value misses while the float result passes
  within the allowance falsifies the claim with that exact witness; a
  float literal in the body is read as the decimal written, so a gap
  of `2e-9` is an exact miss.
- A point the function cannot be evaluated at exactly (a float it
  reads from outside its body, a module global, has no exact reading)
  caps the proof at float64: every point ran and agreed in the
  computation, so the claim is proven on
  `derive:brute_force:within_float64`, the record stating the largest
  delta, never an exact proof.
- A function that satisfies the claim exactly at every point is still
  proven.

Each body below runs a `while` loop so derive cannot read it and the
sweep decides the claim."""
import pytest

from mathema.conjecture import check_conjectures, claim

#: floats a body reads from outside: no exact reading
NUDGE = 2e-9
OFFSET = 5e-10
TINY = 1e-17


def drift_float(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + 2e-9


def offset_float(n: int) -> float:
    i = 0
    while i < 3:
        i += 1
    return n + 5e-10


def constant_float(xs: list) -> float:
    i = 0
    while i < 3:
        i += 1
    return 5e-10


def drift_global(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + NUDGE


def offset_global(n: int) -> float:
    i = 0
    while i < 3:
        i += 1
    return n + OFFSET


def constant_global(xs: list) -> float:
    i = 0
    while i < 3:
        i += 1
    return OFFSET


def constant_zero(xs: list) -> int:
    i = 0
    while i < 3:
        i += 1
    return 0


def inside_allowance(x: float) -> float:
    # exact gap x / 20000000, 5e-8 at 1: inside the float allowance
    i = 0
    while i < 3:
        i += 1
    return x + x / 20000000


def outside_allowance(x: float) -> float:
    # exact gap x / 5000000, 2e-7 at 1: past the float allowance
    i = 0
    while i < 3:
        i += 1
    return x + x / 5000000


def below_float_resolution(x: float) -> float:
    # exact gap x / 10^17: the float result is x itself
    i = 0
    while i < 3:
        i += 1
    return x + x / 100000000000000000


def within_epsilon(x: float) -> float:
    # exact gap x / 2000000000, 5e-10 at 1
    i = 0
    while i < 3:
        i += 1
    return x + x / 2000000000


def past_epsilon(x: float) -> float:
    # exact gap x / 500000000, 2e-9 at 1: past ε, inside the allowance
    i = 0
    while i < 3:
        i += 1
    return x + x / 500000000


def square(n: int) -> int:
    i = 0
    while i < 3:
        i += 1
    return n * n


def tripled(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + x + x


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    (drift_global, "for x in {1, 2}, f(x) == x"),
    (drift_global, "for x in {1, 2}, f(x) ~= x"),
    (offset_global, "for n in {0, 1, 2, 3}, f(n) == n"),
    (offset_global, "for n in [0, 3] subset Z, f(n) == n"),
    (constant_global, "f([]) == 0"),
])
def test_a_body_with_no_exact_value_is_proven_within_float64(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert "mathema.sweep_precision" in p.meta, p.meta


@pytest.mark.parametrize("fn,law", [
    (drift_float, "for x in {1, 2}, f(x) == x"),
    (drift_float, "for x in {1, 2}, f(x) ~= x"),
    (offset_float, "for n in {0, 1, 2, 3}, f(n) == n"),
    (offset_float, "for n in [0, 3] subset Z, f(n) == n"),
    (constant_float, "f([]) == 0"),
])
def test_a_literal_gap_inside_the_allowance_is_an_exact_miss(fn, law):
    # 2e-9 is 2/10^9 and 5e-10 is 5/10^10 as written: the floats agree
    # within the allowance, and the mathematics is false
    p = _check(fn, law)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness
    assert witness["computation"] == "holds within its allowance", witness


def test_the_record_names_the_point_with_no_exact_value():
    p = _check(drift_global, "for x in {1, 2}, f(x) == x")
    inexact = p.meta["mathema.sweep_inexact"]
    assert inexact["points"] == 2, inexact
    assert inexact["first"] == "x = 1", inexact
    assert "exactly" in p.sketch, p.sketch


@pytest.mark.parametrize("law", [
    "for x in {1, 2}, f(x) == x",
    "for x in [1, 3] subset Z, f(x) == x",
    "for x in {0.5, 1.5}, f(x) == x",
])
def test_a_gap_inside_the_allowance_falsifies_exactly(law):
    p = _check(inside_allowance, law)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route
    assert p.counterexample and "exact arithmetic" in p.counterexample, \
        p.counterexample
    witness = p.meta["mathema.exact_witness"]
    assert witness["computation"] == "holds within its allowance", witness


def test_the_exact_witness_reads_the_point_as_written():
    p = _check(inside_allowance, "for x in {0.5, 1.5}, f(x) == x")
    witness = p.meta["mathema.exact_witness"]
    # f(1/2) = 1/2 + 1/40000000 exactly
    assert witness["at"] == "x = 0.5", witness
    assert witness["exact"] == "20000001/40000000 vs 1/2", witness


def test_a_gap_past_the_allowance_falsifies():
    p = _check(outside_allowance, "for x in {1, 2}, f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route


def test_a_gap_below_float_resolution_falsifies_exactly():
    p = _check(below_float_resolution, "for x in {1, 2}, f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.counterexample.startswith("x = 1"), p.counterexample


def test_a_membership_sweep_reads_the_value_exactly():
    p = _check(below_float_resolution, "for x in {1, 2}, f(x) in {1, 2}")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route


def test_a_membership_sweep_with_no_exact_value_is_proven_within_float64():
    def nudged(x: float) -> float:
        i = 0
        while i < 3:
            i += 1
        return x + TINY
    p = _check(nudged, "for x in {1, 2}, f(x) in {1, 2}")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force:within_float64", p.route


def test_a_membership_sweep_reads_a_literal_exactly():
    # 1 + 1e-17 is the float 1.0, and 1 + 1/10^17 exactly, not a member
    def nudged(x: float) -> float:
        i = 0
        while i < 3:
            i += 1
        return x + 1e-17
    p = _check(nudged, "for x in {1, 2}, f(x) in {1, 2}")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route


def test_approximate_equality_within_epsilon_is_proven():
    p = _check(within_epsilon, "for x in {0, 1}, f(x) ~= x")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route


def test_approximate_equality_past_epsilon_is_falsified():
    # 2e-9 at x = 1: inside the computation allowance, past ε
    p = _check(past_epsilon, "for x in {1, 2}, f(x) ~= x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.counterexample.startswith("x = 1"), p.counterexample


@pytest.mark.parametrize("fn,law", [
    (square, "for n in {0, 1, 2, 3}, f(n) == n ** 2"),
    (square, "for n in [0, 9] subset Z, f(n) >= n"),
    (tripled, "for x in {0.1, 0.3}, f(x) == 3 * x"),
    (constant_zero, "f([]) == 0"),
])
def test_a_function_exact_at_every_point_is_proven(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route
