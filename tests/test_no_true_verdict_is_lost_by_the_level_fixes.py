# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two fixes lower a reported level: a library's policy row inherited
through a body that is more than the one library call, and a result
decided within float64. This table holds ordinary true claims of varied
shapes with the verdict of every row each produced before those fixes
(`UNCHANGED`, recorded from the tree the fixes were made on), and
asserts each row has the same verdict now. The rows the fixes move, each
from `proven` to `holds`, are listed apart in `MOVED` with the reason.
"""
from __future__ import annotations

import math

import pytest

import mathema

EPS = 1e-16
RATE = 0.5


def _spin():
    i = 0
    while i < 3:
        i += 1


def square(x: float) -> float:
    return x * x


def cube(x: float) -> float:
    return x ** 3


def affine(x: float) -> float:
    return 2 * x + 1


def clamp(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def absolute(x: float) -> float:
    return abs(x)


def larger(a: float, b: float) -> float:
    return max(a, b)


def mean_of_two(a: float, b: float) -> float:
    return (a + b) / 2


def pythagoras(x: float) -> float:
    return math.sin(x) ** 2 + math.cos(x) ** 2


def exp_of(x: float) -> float:
    return math.exp(x)


def log_of(x: float) -> float:
    return math.log(x)


def root(x):
    return math.sqrt(x)


def root_documented(x: float) -> float:
    """The square root of x."""
    return math.sqrt(x)


def hypotenuse(a: float, b: float) -> float:
    return math.sqrt(a * a + b * b)


def total(xs: list) -> float:
    return sum(xs)


def count(xs: list) -> int:
    return len(xs)


def ordered(xs: list) -> list:
    return sorted(xs)


def double_all(xs: list) -> list:
    return [2 * x for x in xs]


def factorial(n: int) -> int:
    out = 1
    for k in range(2, n + 1):
        out *= k
    return out


def triangular(n: int) -> int:
    return n * (n + 1) // 2


def parity(n: int) -> int:
    return n % 2


def half(x: float) -> float:
    _spin()
    return x * 0.5


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def relu(x: float) -> float:
    return x if x > 0 else 0.0


def is_positive(x: float) -> bool:
    return x > 0


def tiny(n):
    return math.exp(EPS * n)


def tiny_unread(n):
    _spin()
    return math.exp(EPS * n)


def halve(x: float) -> float:
    _spin()
    return x * RATE


def narrow_raise(x: float, y: float) -> float:
    if x != x and 0.6180 < y < 0.6181:
        raise ValueError("narrow")
    return math.sqrt(x)


def converted_root(x: float) -> float:
    return float(math.sqrt(x))


#: (id, function, claim): each claim is true of its function
CLAIMS = [
    ("square_nonneg", square, "for x in [-3, 3], f(x) >= 0"),
    ("square_even", square, "for x in [-3, 3], f(-x) == f(x)"),
    ("square_value", square, "for x in [-3, 3], f(x) == x ** 2"),
    ("square_ground", square, "f(3) == 9"),
    ("square_set", square, "for x in {1, 2, 3}, f(x) == x * x"),
    ("cube_odd", cube, "for x in [-2, 2], f(-x) == -f(x)"),
    ("cube_increasing", cube, "for x in [1, 2], d(f(x), x) > 0"),
    ("affine_value", affine, "for x in [0, 10], f(x) == 2 * x + 1"),
    ("affine_bounds", affine, "for x in [0, 1], 1 <= f(x) <= 3"),
    ("affine_slope", affine, "for x in [0, 1], d(f(x), x) == 2"),
    ("clamp_range", clamp, "for x in [-5, 5], 0 <= f(x) <= 1"),
    ("clamp_idempotent", clamp, "for x in [-5, 5], f(f(x)) == f(x)"),
    ("clamp_inside", clamp, "for x in [0, 1], f(x) == x"),
    ("abs_nonneg", absolute, "for x in [-4, 4], f(x) >= 0"),
    ("abs_even", absolute, "for x in [-4, 4], f(-x) == f(x)"),
    ("larger_ge_a", larger, "for a in [-1, 1], b in [-1, 1], f(a, b) >= a"),
    ("larger_symmetric", larger, "for a in [-1, 1], b in [-1, 1], f(a, b) == f(b, a)"),
    ("mean_between", mean_of_two, "for a in [0, 1], b in [0, 1], 0 <= f(a, b) <= 1"),
    ("mean_symmetric", mean_of_two, "for a in [0, 1], b in [0, 1], f(a, b) == f(b, a)"),
    ("pythagoras_one", pythagoras, "for x in [-3, 3], f(x) == 1"),
    ("pythagoras_tolerant", pythagoras, "for x in [-3, 3], f(x) ~= 1"),
    ("exp_positive", exp_of, "for x in [-5, 5], f(x) > 0"),
    ("exp_increasing", exp_of, "for x in [-5, 5], d(f(x), x) > 0"),
    ("exp_at_zero", exp_of, "f(0) == 1"),
    ("log_increasing", log_of, "for x in (0, 100], d(f(x), x) > 0"),
    ("log_of_one", log_of, "f(1) == 0"),
    ("root_nonneg", root, "for x in [0, 1], f(x) >= 0"),
    ("root_documented_nonneg", root_documented, "for x in [0, 1], f(x) >= 0"),
    ("root_squares_back", root, "for x in [0, 4], f(x) ** 2 ~= x"),
    ("hypotenuse_ge_leg", hypotenuse, "for a in [0, 3], b in [0, 3], f(a, b) >= a"),
    ("total_bounded", total, "for xs in [0, 1]^n, f(xs) >= 0"),
    ("count_nonneg", count, "for xs in [0, 1]^n, f(xs) >= 0"),
    ("ordered_idempotent", ordered, "for xs in [0, 1]^n, f(f(xs)) == f(xs)"),
    ("double_all_length", double_all, "for xs in [0, 1]^n, len(f(xs)) == len(xs)"),
    ("factorial_values", factorial, "for n in {0, 1, 2, 3, 4, 5}, f(n) >= 1"),
    ("factorial_ground", factorial, "f(5) == 120"),
    ("triangular_set", triangular, "for n in {1, 2, 3, 4}, f(n) == n * (n + 1) / 2"),
    ("parity_members", parity, "for n in {0, 1, 2, 3, 4, 5}, f(n) in {0, 1}"),
    ("half_exact_sweep", half, "for x in {1, 2, 3}, f(x) == x / 2"),
    ("sign_members", sign, "for x in [-2, 2], f(x) in {-1, 0, 1}"),
    ("relu_nonneg", relu, "for x in [-3, 3], f(x) >= 0"),
    ("relu_idempotent", relu, "for x in [-3, 3], f(f(x)) == f(x)"),
    ("is_positive_true", is_positive, "for x in [1, 2], f(x) == True"),
    ("root_missing_safe", root, "is_missing_safe(f)"),
    ("square_deterministic", square, "is_deterministic(f)"),
    ("tiny_tolerant", tiny, "for n in {1, 2, 3}, f(n) ~= 1"),
    ("tiny_at_least_one", tiny, "for n in {1, 2, 3}, f(n) >= 1"),
]


def rows_of(fn, law) -> dict:
    """`{row name: verdict}` for every row the one claim produces."""
    return {p.name: p.verdict for p in mathema.check(
        fn, claims=[mathema.claim(law, name="c")]).probes}


#: {id: {row name: verdict}} before the fixes
UNCHANGED: dict = {
    "square_nonneg": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "square_even": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "square_value": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "square_ground": {"c": "proven", "c[float]": "holds"},
    "square_set": {"c": "proven", "c[float]": "holds"},
    "cube_odd": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "cube_increasing": {"c": "proven", "missing[x]": "holds"},
    "affine_value": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "affine_bounds": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "affine_slope": {"c": "proven", "missing[x]": "holds"},
    "clamp_range": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "clamp_idempotent": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "clamp_inside": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "abs_nonneg": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "abs_even": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "larger_ge_a": {
        "c": "proven",
        "c[float]": "holds",
        "missing[a]": "holds",
        "missing[b]": "falsified"},
    "larger_symmetric": {
        "c": "proven",
        "c[float]": "holds",
        "missing[a]": "holds",
        "missing[b]": "falsified"},
    "mean_between": {
        "c": "proven",
        "c[float]": "holds",
        "missing[a]": "holds",
        "missing[b]": "holds"},
    "mean_symmetric": {
        "c": "proven",
        "c[float]": "holds",
        "missing[a]": "holds",
        "missing[b]": "holds"},
    "pythagoras_one": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "pythagoras_tolerant": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "exp_positive": {"c": "proven", "c[float]": "holds", "missing[x]": "holds"},
    "exp_increasing": {"c": "proven", "missing[x]": "holds"},
    "exp_at_zero": {"c": "proven", "c[float]": "holds"},
    "log_increasing": {"c": "proven", "missing[x]": "holds"},
    "log_of_one": {"c": "proven", "c[float]": "holds"},
    "root_nonneg": {
        "c": "proven",
        "c[float]": "holds",
        "missing[x]": "proven",
        "absent[x]": "proven"},
    "root_documented_nonneg": {"c": "proven", "c[float]": "holds", "missing[x]": "proven"},
    "root_squares_back": {
        "c": "proven",
        "c[float]": "holds",
        "missing[x]": "proven",
        "absent[x]": "proven"},
    "hypotenuse_ge_leg": {
        "c": "proven",
        "c[float]": "holds",
        "missing[a]": "holds",
        "missing[b]": "holds"},
    "total_bounded": {
        "c": "proven",
        "c[float]": "holds",
        "is_empty_safe[xs]": "holds",
        "missing[xs, null]": "falsified",
        "missing[xs, nan]": "holds"},
    "count_nonneg": {"c": "holds", "is_empty_safe[xs]": "holds", "missing[xs]": "falsified"},
    "ordered_idempotent": {
        "c": "holds",
        "is_empty_safe[xs]": "holds",
        "missing[xs]": "falsified"},
    "double_all_length": {
        "c": "holds",
        "is_empty_safe[xs]": "holds",
        "missing[xs, null]": "falsified",
        "missing[xs, nan]": "holds"},
    "factorial_values": {"c": "proven"},
    "factorial_ground": {"c": "proven"},
    "triangular_set": {"c": "proven"},
    "parity_members": {"c": "proven"},
    "half_exact_sweep": {"c": "proven"},
    "sign_members": {"c": "holds", "missing[x]": "falsified"},
    "relu_nonneg": {"c": "proven", "c[float]": "holds", "missing[x]": "falsified"},
    "relu_idempotent": {"c": "proven", "c[float]": "holds", "missing[x]": "falsified"},
    "is_positive_true": {"c": "holds", "missing[x]": "falsified"},
    "root_missing_safe": {"c": "proven"},
    "square_deterministic": {"c": "proven"},
    "tiny_tolerant": {"c": "proven", "c[float]": "holds"},
    "tiny_at_least_one": {"c": "proven", "c[float]": "holds"},
}

#: (function, claim, row, verdict before, verdict now, why it moved)
MOVED = [
    (narrow_raise, "for x in [0, 1], y in [0, 1], f(x, y) >= 0", "missing[x]",
     "proven", "holds",
     "the library row is confirmed on the calls made; the body raises before "
     "the call on a path no call took"),
    (converted_root, "for x in [0, 1], f(x) >= 0", "missing[x]",
     "proven", "holds",
     "the body converts what the library call gives back, which is not read"),
    (tiny, "for n in {1, 2, 3}, f(n) == 1", "c",
     "proven", "holds",
     "every point ran in float64; exp(1e-16 n) is not 1"),
    (tiny_unread, "f(1) == 1", "c",
     "proven", "holds",
     "the one call ran in float64 and has no exact value"),
    (halve, "for x in {1, 2}, f(x) in {0.5, 1}", "c",
     "proven", "holds",
     "every point ran in float64 through a module constant with no exact reading"),
]


def test_the_table_holds_at_least_thirty_claims_each_with_a_recorded_verdict():
    assert len(CLAIMS) >= 30
    assert sorted(UNCHANGED) == sorted(name for name, _fn, _law in CLAIMS)
    assert all(rows["c"] in ("proven", "holds") for rows in UNCHANGED.values())


@pytest.mark.parametrize("name, fn, law", CLAIMS, ids=[c[0] for c in CLAIMS])
def test_every_row_of_a_true_claim_keeps_its_verdict(name, fn, law):
    assert rows_of(fn, law) == UNCHANGED[name]


@pytest.mark.parametrize("fn, law, row, before, now, why", MOVED,
                         ids=[f"{m[0].__name__}:{m[2]}" for m in MOVED])
def test_a_moved_row_goes_from_proven_to_holds_and_no_lower(fn, law, row, before,
                                                           now, why):
    assert (before, now) == ("proven", "holds") and why
    assert rows_of(fn, law)[row] == now
