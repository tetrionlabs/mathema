# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that names no missing value (no None, nan, absent or missing
beside its domain) is checked as before: its verdict, the route that
decided it, its canonical text and the statement of its row are the
values recorded under reasoning version 1, before the named missing
value reading, for the same function and text."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.spec import canonical_claim_text


def ident(x: float) -> float:
    return x


def unannotated(x):
    return x


def square(x: float) -> float:
    return x * x


def add(a: float, b: float) -> float:
    return a + b


def double(n: int) -> int:
    return 2 * n


def clamp01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def absval(x: float) -> float:
    return abs(x)


def negate(x):
    return -x


def triangle(n: int) -> int:
    return n * (n + 1) // 2


def recip(x: float) -> float:
    return 1.0 / x


def hypot2(x: float, y: float) -> float:
    return x * x + y * y


#: function, claim text, verdict, route, canonical text, row statement
CASES = [
    (ident, 'for x in [1, 5], f(x) == x',
     'proven', 'derive',
     'for x in [1.0, 5.0] : float|absent|missing, f(x) = x',
     'for x in [1.0, 5.0] : float|missing, f(x) = x'),
    (ident, 'for x in R, f(x) == x',
     'proven', 'derive',
     'for x in R|absent|missing, f(x) = x',
     'for x in R|missing, f(x) = x'),
    (unannotated, 'for x in [0, 1], f(x) >= 0',
     'proven', 'derive',
     'for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0',
     'for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0'),
    (square, 'for x in [-3, 3], f(x) >= 0',
     'proven', 'derive',
     'for x in [-3.0, 3.0] : float|absent|missing, f(x) >= 0',
     'for x in [-3.0, 3.0] : float|missing, f(x) >= 0'),
    (square, 'for x in [0, 2], f(x) <= 4',
     'proven', 'derive',
     'for x in [0.0, 2.0] : float|absent|missing, f(x) <= 4',
     'for x in [0.0, 2.0] : float|missing, f(x) <= 4'),
    (square, 'for x in [0, 2], f(x) < 3',
     'falsified', 'probe:semi_analytical',
     'for x in [0.0, 2.0] : float|absent|missing, f(x) < 3',
     'for x in [0.0, 2.0] : float|missing, f(x) < 3'),
    (add, 'for a in [0, 1], b in [0, 1], f(a, b) == f(b, a)',
     'proven', 'derive',
     'for a in [0.0, 1.0] : float|absent|missing, b in [0.0, 1.0] : float|absent|missing, f(a, b) = f(b, a)',
     'for a in [0.0, 1.0] : float|missing, b in [0.0, 1.0] : float|missing, f(a, b) = f(b, a)'),
    (add, 'for a in [-1, 1], b in [-1, 1], f(a, b) <= 2',
     'proven', 'derive',
     'for a in [-1.0, 1.0] : float|absent|missing, b in [-1.0, 1.0] : float|absent|missing, f(a, b) <= 2',
     'for a in [-1.0, 1.0] : float|missing, b in [-1.0, 1.0] : float|missing, f(a, b) <= 2'),
    (double, 'for n in Z, f(n) == 2 * n',
     'proven', 'derive',
     'for n in Z|absent|missing, f(n) = 2*n',
     'for n in Z, f(n) = 2*n'),
    (double, 'for n in {1, 2, 3}, f(n) == 2 * n',
     'proven', 'derive',
     'for n in {1, 2, 3}, f(n) = 2*n',
     'for n in {1, 2, 3}, f(n) = 2*n'),
    (double, 'for n in [0, 10] subset Z, f(n) >= n',
     'proven', 'derive',
     'for n in [0, 10] : int, f(n) >= n',
     'for n in [0, 10] : int, f(n) >= n'),
    (clamp01, 'for x in R, f(x) <= 1',
     'proven', 'derive',
     'for x in R|absent|missing, f(x) <= 1',
     'for x in R|missing, f(x) <= 1'),
    (clamp01, 'for x in [-5, 5], f(x) >= 0',
     'proven', 'derive',
     'for x in [-5.0, 5.0] : float|absent|missing, f(x) >= 0',
     'for x in [-5.0, 5.0] : float|missing, f(x) >= 0'),
    (absval, 'for x in [-10.0, 10.0] : float, f(x) >= 0',
     'proven', 'derive',
     'for x in [-10.0, 10.0] : float, f(x) >= 0',
     'for x in [-10.0, 10.0] : float, f(x) >= 0'),
    (absval, 'for x in [-1, 1], f(x) == x',
     'falsified', 'probe:semi_analytical',
     'for x in [-1.0, 1.0] : float|absent|missing, f(x) = x',
     'for x in [-1.0, 1.0] : float|missing, f(x) = x'),
    (negate, 'for x in [-2, 2], f(f(x)) == x',
     'proven', 'derive',
     'for x in [-2.0, 2.0] : float|absent|missing, f(f(x)) = x',
     'for x in [-2.0, 2.0] : float|absent|missing, f(f(x)) = x'),
    (double, 'for n in [-5, 5] subset Z, f(n) <= 10',
     'proven', 'derive',
     'for n in [-5, 5] : int, f(n) <= 10',
     'for n in [-5, 5] : int, f(n) <= 10'),
    (triangle, 'for n in [1, 100] subset Z, f(n) >= n',
     'proven', 'derive:brute_force',
     'for n in [1, 100] : int, f(n) >= n',
     'for n in [1, 100] : int, f(n) >= n'),
    (recip, 'for x in [1, 4], f(x) * x ~= 1',
     'proven', 'derive',
     'for x in [1.0, 4.0] : float|absent|missing, x*f(x) ~= 1',
     'for x in [1.0, 4.0] : float|missing, x*f(x) ~= 1'),
    (square, 'let root = math.sqrt, for x in [1, 100], root(f(x)) ~= x',
     'holds', 'probe',
     'let root = math.sqrt, for x in [1.0, 100.0] : float|absent|missing, root(f(x)) ~= x',
     'let root = math.sqrt, for x in [1.0, 100.0] : float|missing, root(f(x)) ~= x'),
    (hypot2, 'for x in [0, 1], y in [-1, 0], f(x, y) == f(y, x)',
     'proven', 'derive',
     'for x in [0.0, 1.0] : float|absent|missing, y in [-1.0, 0.0] : float|absent|missing, f(x, y) = f(y, x)',
     'for x in [0.0, 1.0] : float|missing, y in [-1.0, 0.0] : float|missing, f(x, y) = f(y, x)'),
    (ident, 'for x in {1, 4}, f(x) == x',
     'proven', 'derive',
     'for x in {1, 4}, f(x) = x',
     'for x in {1, 4}, f(x) = x'),
    (square, 'for x in [1, 2], let c be [0.1, 10], f(x) * c >= 0',
     'proven', 'derive',
     'let c be [0.1, 10.0], for x in [1.0, 2.0] : float|absent|missing, c*f(x) >= 0',
     'let c be [0.1, 10.0], for x in [1.0, 2.0] : float|missing, c*f(x) >= 0'),
    (unannotated, 'for x in [-1, 1], f(x) <= 1',
     'proven', 'derive',
     'for x in [-1.0, 1.0] : float|absent|missing, f(x) <= 1',
     'for x in [-1.0, 1.0] : float|absent|missing, f(x) <= 1'),
    (square, 'for x in [1, 3], d(f(x), x) == 2 * x',
     'proven', 'derive',
     'for x in [1.0, 3.0] : float|absent|missing, d(f(x), x) = 2*x',
     'for x in [1.0, 3.0] : float|missing, d(f(x), x) = 2*x'),
]


@pytest.mark.parametrize("fn, text, verdict, route, canonical, statement", CASES,
                         ids=[f"{c[0].__name__}: {c[1]}" for c in CASES])
def test_a_claim_naming_no_missing_value_reads_and_checks_as_on_develop(
        fn, text, verdict, route, canonical, statement):
    cj = claim(text)
    assert canonical_claim_text(cj) == canonical
    (row,) = check_conjectures(fn, [cj])
    assert (row.verdict, row.route, row.statement) == (verdict, route, statement), (
        row.verdict, row.route, row.statement, row.counterexample, row.note)
