# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) holds an exact
number where the computation held a float. A decision on such a number
(a comparison, a branch or loop test, a dict or set key, `floor`,
`ceil`, `trunc`, `int()`, `round`, `divmod`, `//`, `%`, or an `except`
catching an arithmetic error) can go the other way from the
computation's, whose float was rounded: a loop counting 0.1 steps runs
ten times exactly and eleven times in float. The reading does not take
such a decision: the point is undecided and the sweep, every point run,
is proven within float64. A correct body is never falsified on a path
the computation did not take. Decisions on integers stay exact.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import math
from fractions import Fraction

import pytest

from mathema._exact_body import NotExact, exact_callee, exact_twin
from mathema.conjecture import check_conjectures, claim


def _spin():
    i = 0
    while i < 3:
        i += 1


# branch divergence: a loop counting float steps
def steps(n: int) -> int:
    _spin()
    t = 0.0
    k = 0
    while t < 1.0:
        t += 0.1
        k += 1
    return k + 0 * n


# floor of a value rounding flattens
def floor_flat(x: int) -> int:
    _spin()
    return math.floor(x - 1e-17)


# round on a binary vs decimal tie
def cents_tie(x: int) -> float:
    _spin()
    return round(2.675 + 0 * x, 2)


# int() of a product rounding moves
def int_cut(x: int) -> int:
    _spin()
    return int(0.1 * 3 * 10) + 0 * x


def float_pow_overflow(x: int) -> float:
    _spin()
    try:
        return 10.0 ** (300 * x)
    except OverflowError:
        return -1.0


# equality branch on a float sum
def eq_branch(x: int) -> int:
    _spin()
    if 0.1 + 0.2 == 0.3:
        return 1
    return 0


# `==` between two transcendental values that are mathematically equal
def log_check(x: int) -> float:
    _spin()
    if math.log(8 * x) == math.log(8) + math.log(x):
        return 1.0
    return 0.0


def pythag(x: int) -> float:
    _spin()
    if math.sin(x) ** 2 + math.cos(x) ** 2 == 1:
        return 1.0
    return 0.0


def log_key(x: int) -> float:
    _spin()
    table = {math.log(8): 3.0}
    return table.get(3 * math.log(2), -1.0) + 0 * x


def _at_most_threshold(y):
    if y <= 0.3:
        return 1
    return 0


def under_threshold(x: int) -> int:
    _spin()
    return _at_most_threshold(x / 10)


def eq_bool(x: int) -> bool:
    _spin()
    return 0.1 + 0.2 == 0.3


def eq_int(x: int) -> int:
    _spin()
    return int(0.1 + 0.2 == 0.3)


def swallowed(x: int) -> float:
    _spin()
    try:
        if x / 10 <= 0.3:
            return 1.0
        return 0.0
    except Exception:
        return 1.0


def divisors(n: int) -> int:
    _spin()
    count = 0
    for d in range(1, n + 1):
        if n % d == 0:
            count += 1
    return count


def by_index(n: int) -> float:
    _spin()
    table = {1: 0.5, 2: 0.25}
    if n in table:
        return table[n]
    return 0.0


def unless_missing(x: float) -> float:
    _spin()
    if x is None:
        return 0.0
    return x * 0.5


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


#: the review's bodies: correct code each, every point run in float64
DECIDED_BY_ROUNDING = [
    (steps, "for n in {1, 2}, f(n) == 11"),
    (cents_tie, "for x in {1}, f(x) == 2.67"),
    (floor_flat, "for x in {1, 2}, f(x) == x"),
    (float_pow_overflow, "for x in {1, 2}, f(x) <= 1e300"),
    (int_cut, "for x in {1}, f(x) == 3"),
    (eq_branch, "for x in {1}, f(x) == 0"),
    (eq_int, "for x in {1}, f(x) == 0"),
    (eq_bool, "for x in {1}, f(x) == False"),
    (log_check, "for x in {1, 2}, f(x) == 1"),
    (pythag, "for x in {1, 2, 4}, f(x) == 1"),
    (log_key, "for x in {1}, f(x) == 3"),
    (under_threshold, "for x in {1, 2, 3}, f(x) == 1"),
    (swallowed, "for x in {1, 2, 3}, f(x) == 1"),
]


@pytest.mark.parametrize("fn,law", DECIDED_BY_ROUNDING,
                         ids=lambda v: getattr(v, "__name__", None))
def test_a_decision_on_an_exact_number_leaves_the_point_undecided(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route,
                                   p.sketch, p.counterexample)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta
    assert p.meta["mathema.sweep_inexact"]["points"] >= 1, p.meta


def test_a_bool_and_an_int_of_the_same_decision_agree():
    as_bool = _check(eq_bool, "for x in {1}, f(x) == False")
    as_int = _check(eq_int, "for x in {1}, f(x) == 0")
    assert (as_bool.verdict, as_bool.route) == (as_int.verdict, as_int.route)


@pytest.mark.parametrize("fn,law", [
    (divisors, "for n in {6, 12}, f(n) >= 4"),
    (divisors, "for n in {7, 13}, f(n) == 2"),
    (by_index, "for n in {1}, f(n) == 0.5"),
    (unless_missing, "for x in {1, 3}, f(x) == x / 2"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_decision_on_integers_stays_exact(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route


def compares(y):
    return y < 1


def keys(y):
    return {y: 1}


def members(y):
    return {y}


def looks_up(y):
    return {0.5: 1}.get(y)


def contains(y):
    return y in [0.5]


def floors(y):
    return math.floor(y)


def ceils(y):
    return math.ceil(y)


def truncs(y):
    return math.trunc(y)


def ints(y):
    return int(y)


def rounds(y):
    return round(y)


def rounds_to(y):
    return round(y, 1)


def splits(y):
    return divmod(y, 1)


def floor_divides(y):
    return y // 1


def remainders(y):
    return y % 1


def branches(y):
    if y:
        return 1
    return 0


def loops(y):
    while y > 0:
        y -= 1
    return y


def filters(y):
    return [v for v in [y] if v]


def truths(y):
    return bool(y)


def catches(y):
    try:
        return 1 / y
    except ZeroDivisionError:
        return 0.0


DECISIONS = [compares, keys, members, looks_up, contains, floors, ceils,
             truncs, ints, rounds, rounds_to, splits, floor_divides,
             remainders, branches, loops, filters, truths, catches]


@pytest.mark.parametrize("fn", DECISIONS, ids=lambda f: f.__name__)
def test_each_decision_on_a_number_standing_for_a_float_is_declined(fn):
    twin = exact_twin(fn)
    assert twin is not None, fn.__name__
    with pytest.raises(NotExact):
        twin(Fraction(1, 2))
    sympy = pytest.importorskip("sympy")
    with pytest.raises(NotExact):
        twin(sympy.sqrt(2))


@pytest.mark.parametrize("fn", [f for f in DECISIONS
                                if f not in (looks_up, contains, catches)],
                         ids=lambda f: f.__name__)
def test_the_same_decision_on_an_integer_is_taken(fn):
    twin = exact_twin(fn)
    assert twin(3) == fn(3), fn.__name__


def test_an_integer_division_under_a_catch_raises_as_the_computation():
    twin = exact_twin(catches)
    assert twin(2) == Fraction(1, 2)
    assert twin(0) == 0


def test_a_caught_decision_still_leaves_the_point_undecided():
    with pytest.raises(NotExact):
        exact_callee(swallowed)(1)


def orders_pairs(y):
    return sorted([(y, "a"), (2, "b")])[0][1]


def searches_lazily(y):
    return 1 in (v for v in [y])


def clamps(y):
    return max(y, 0)


def test_an_order_or_a_search_a_float_could_change_is_declined():
    for fn in (orders_pairs, searches_lazily):
        with pytest.raises(NotExact):
            exact_twin(fn)(Fraction(1, 2))
    # the largest value is the mathematics' own, whichever is larger
    assert exact_twin(clamps)(Fraction(1, 2)) == Fraction(1, 2)
    assert exact_twin(orders_pairs)(3) == "b"
