# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite sweep runs the function on each point's exact value with its
body read exactly: a float literal is the decimal written (`0.5` is
1/2, `2e-9` is 2/10^9), `int / int` is a ratio, `float()` is the
identity on an exact number, `int()`, `//`, `%`, `round`, `math.floor`
and `math.ceil` are exact, and a square root, a power with a fractional
exponent or `math.pi` becomes an exact sympy value whose comparison
sympy decides. A body that correctly computes the claim then proves it
at every point, whatever its return type says; one that misses by a
literal the float allowance absorbs is falsified with the exact
witness. A float the body reads from outside (a global, a numpy value)
has no exact reading, and the sweep records how far the floats missed
and the allowance that absorbed it.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import math

import pytest

import mathema
from mathema import lexicon
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

#: a float read from outside the body: no exact reading
RATE = 0.1


def _spin():
    i = 0
    while i < 3:
        i += 1


def half(x: float) -> float:
    _spin()
    return x * 0.5


def quarter(x: int) -> float:
    _spin()
    return x / 4


def half_down(x: int) -> int:
    _spin()
    return x // 2


def half_trunc(x: int) -> int:
    _spin()
    return int(x / 2)


def shifted(n: int) -> float:
    _spin()
    return float(n) + 0.25


def nearest(x: float) -> int:
    _spin()
    return round(x)


def cents(x: float) -> float:
    _spin()
    return round(x, 2)


def root_then_square(x: float) -> float:
    _spin()
    return math.sqrt(x) ** 2


def root(x: float) -> float:
    _spin()
    return math.sqrt(x)


def cube_root(x: float) -> float:
    _spin()
    return x ** (1 / 3)


def circumference(r: float) -> float:
    _spin()
    return 2 * math.pi * r


def root_two_squared(xs: list) -> float:
    _spin()
    return math.sqrt(2) * math.sqrt(2)


def drift(x: float) -> float:
    _spin()
    return x + 2e-9


def near(x: float) -> float:
    _spin()
    return x + 5e-10


def tenth_by_global(x: float) -> float:
    _spin()
    return x * RATE


def half_by_numpy(x: float) -> float:
    _spin()
    return float(np.float64(x) * 0.5)


def nudged(x: float) -> float:
    return x + 1e-17


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    (half, "for x in {1, 2, 3}, f(x) == x / 2"),
    (quarter, "for x in [0, 8] subset Z, f(x) == x / 4"),
    (half_down, "for x in [0, 9] subset Z, f(x) == floor(x / 2)"),
    (half_trunc, "for x in {1, 3, 5}, f(x) == floor(x / 2)"),
    (shifted, "for n in {0, 1, 2}, f(n) == n + 0.25"),
    (shifted, "for n in {0, 1, 2}, f(n) == n + 1/4"),
    (nearest, "for x in {0.5, 1.5, 2.5, 3.5}, f(x) % 2 == 0"),
    (cents, "for x in {0.125, 0.625}, f(x) == x - 0.005"),
])
def test_a_body_of_literals_and_exact_operations_is_proven(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route


@pytest.mark.parametrize("fn,law", [
    (root_then_square, "for x in {1, 4, 9, 16}, f(x) == x"),
    (root_then_square, "for x in {2, 3, 5}, f(x) == x"),
    (root, "for x in {2, 3}, f(x) * f(x) == x"),
    (root, "for x in {2, 3}, f(x) < x"),
    (cube_root, "for x in {8, 27}, f(x) ** 3 == x"),
    (circumference, "for r in {1, 2}, f(r) > 6 * r"),
])
def test_an_irrational_value_is_decided_by_sympy(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route


def test_a_product_of_roots_at_a_point_is_proven():
    # sqrt(2) * sqrt(2) is 2.0000000000000004 in float and 2 exactly
    p = _check(root_two_squared, "f([]) == 2")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("key,fn", [
    ("finite_domain_pinned", lexicon.divisor_count),
    ("finite_domain_small_range", lexicon.divisor_count),
    ("finite_domain_discrete_set", lexicon.divisor_count),
    ("floor_div_evaluable", lexicon.half_down),
])
def test_a_lexicon_example_returning_a_float_of_an_integer_is_proven(key, fn):
    # `float(total)` is the identity on the exact count
    (p,) = mathema.check(fn, claims=[mathema.claim(
        lexicon.LEXICON[key], name=key)]).probes
    assert p.verdict == "proven", (key, p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force", p.route


@pytest.mark.parametrize("law", [
    "for x in {1, 2}, f(x) == x",
    "for x in {1, 2}, f(x) ~= x",
])
def test_a_literal_gap_inside_the_allowance_is_an_exact_miss(law):
    p = _check(drift, law)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness
    assert witness["computation"] == "holds within its allowance", witness
    assert witness["exact"] == "500000001/500000000 vs 1", witness


def test_a_literal_gap_inside_epsilon_is_proven_approximately_equal():
    p = _check(near, "for x in {0, 1}, f(x) ~= x")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route


def test_a_float_literal_derive_disproves_is_read_as_written():
    # the point's free coordinate is drawn and the body read exactly
    # there: 1e-17 is 1/10^17, so f(x) == x is false
    p = _check(nudged, "for x in [1, 2], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.meta["mathema.exact_witness"]["reading"] == "mathematics", \
        p.meta


@pytest.mark.parametrize("fn,law", [
    (tenth_by_global, "for x in {1, 3}, f(x) == x / 10"),
    (half_by_numpy, "for x in {1, 3}, f(x) == x / 2"),
])
def test_a_float_from_outside_the_body_has_no_exact_reading(fn, law):
    p = _check(fn, law)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", p.route
    inexact = p.meta["mathema.sweep_inexact"]
    assert inexact["points"] == 2, inexact
    assert "mathema.exact_witness" not in p.meta, p.meta


def test_an_exhaustive_inexact_sweep_records_its_precision():
    # 3 * 0.1 is 0.30000000000000004 in float: the sweep holds within
    # the allowance, and says by how much the floats missed
    p = _check(tenth_by_global, "for x in {1, 3}, f(x) == x / 10")
    precision = p.meta["mathema.sweep_precision"]
    assert precision["points"] == 2, precision
    assert precision["representation"] == "float64", precision
    assert 0 < precision["largest_miss"] < 1e-15, precision
    assert precision["largest_miss"] < precision["allowance"], precision
    assert precision["at"] == "x = 3", precision


def test_an_exact_sweep_records_no_precision():
    p = _check(half, "for x in {1, 2, 3}, f(x) == x / 2")
    assert "mathema.sweep_precision" not in p.meta, p.meta
    assert "mathema.sweep_inexact" not in p.meta, p.meta
