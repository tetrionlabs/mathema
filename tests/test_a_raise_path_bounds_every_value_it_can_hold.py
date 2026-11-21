# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reading of a path to a `raise` bounds the size of every number on
it, and a `raises(f(x), E)` claim is proven only when those bounds show
nothing on the path overflows. The bound of `a % c` covers the divisor
too, since the remainder of a negative `a` by a positive `c` is close to
`c`; the bound of `a // c` is one more than the bound of `a`; and every
bound is rounded up to a float, so a value just under the largest float
is never read as fitting below it when it does not."""
import sys

import pytest

from mathema.conjecture import check_conjectures, claim

_BIG = 10 ** 300


def _row(fn, exception: str = "ValueError", domain: str = "[-5, -1]", route: str = "best"):
    (row,) = check_conjectures(
        fn, [claim(f"for x in {domain}, raises(f(x), {exception})", route=route)])
    return row


# ---- the remainder by a large divisor ----------------------------------------

def remainder_squared(x: int) -> int:
    if x < 0:
        y = x % 1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
        z = y * y
        w = z + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def remainder_as_text(x: int) -> int:
    if x < 0:
        y = x % 1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
        z = y * y * y * y * y * y * y * y * y * y * y * y * y * y * y
        raise TypeError(str(z))
    return x


def small_remainder(x: int) -> int:
    if x < 0:
        y = x % 7
        z = y * y
        w = z + 0.5  # noqa: F841
        raise ValueError(str(z))
    return x


@pytest.mark.parametrize("fn,exception,instead", [
    (remainder_squared, "ValueError", OverflowError),
    (remainder_as_text, "TypeError", ValueError),
], ids=["squared", "as_text"])
def test_a_remainder_that_overflows_is_not_proven_to_raise(fn, exception, instead):
    with pytest.raises(instead):
        fn(-1)
    assert _row(fn, exception, route="derive").verdict != "proven"
    assert _row(fn, exception).verdict == "falsified"


def test_a_remainder_by_a_small_divisor_is_still_proven_to_raise():
    row = _row(small_remainder, route="derive")
    assert row.verdict == "proven", (row.verdict, row.sketch)


def test_the_remainder_of_a_negative_number_is_bounded_by_its_divisor():
    from mathema._raise_reading import ValueKind, _arithmetic
    import ast
    a = ValueKind(frozenset({int}), 5.0, 1.0)
    c = ValueKind(frozenset({int}), float(_BIG), float(_BIG))
    _, kind = _arithmetic(ast.Mod(), a, c, ast.Constant(_BIG))
    assert kind.magnitude >= _BIG - 1
    _, kind = _arithmetic(ast.FloorDiv(), a, ValueKind(frozenset({int}), 1.0, 1.0),
                          ast.Constant(-1))
    assert kind.magnitude >= 6
    assert -5 // -1 == 5 and -5 % _BIG == _BIG - 5
    assert sys.float_info.max > _BIG


# ---- bounds rounded up -------------------------------------------------------

def sum_just_past_the_float_maximum(x: int) -> int:
    if x < 0:
        y = 179769313486231580793728971405303415079934132710037826936173778980444968292764750946649017977587207096330286416692887910946555547851940402630657488671505820681908902000708383676273854845817711531764475730270069855571366959622842914819860834936475292719074168444365510704342711559699508093042880177904174497791 + 4989600773836799529132479070093925771226990714529979588052066548876451785318362793117968131290681654971765441016278723103616304651091870092985811934760035582204005558722307158063310116666923386609933687578536986926478638411270796957755769718436085405946387916809117520482063620781496216846336
        w = y + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def test_a_sum_just_past_the_float_maximum_is_not_proven_to_raise():
    with pytest.raises(OverflowError):
        sum_just_past_the_float_maximum(-1)
    assert _row(sum_just_past_the_float_maximum, route="derive").verdict != "proven"
    assert _row(sum_just_past_the_float_maximum).verdict == "falsified"


def test_the_magnitude_of_an_int_is_rounded_up_and_its_least_down():
    from mathema._raise_reading import kind_of_value
    for value in (2 ** 53 + 1, -(2 ** 53 + 1), 10 ** 300 + 1, 3 ** 500,
                  int(sys.float_info.max) - 1):
        kind = kind_of_value(value)
        assert kind.magnitude >= abs(value), value
        assert kind.least <= abs(value), value
    assert kind_of_value(int(sys.float_info.max) + 1).magnitude == float("inf")


def test_every_arithmetic_bound_covers_the_exact_result():
    import ast
    from fractions import Fraction
    from mathema._raise_reading import _arithmetic, kind_of_value
    values = [2 ** 53 + 1, 2 ** 60 + 3, 10 ** 300 + 7, 3, 1]
    for op, exact in ((ast.Add(), lambda a, b: a + b), (ast.Sub(), lambda a, b: a - b),
                      (ast.Mult(), lambda a, b: a * b),
                      (ast.Div(), lambda a, b: Fraction(a, b))):
        for a in values:
            for b in values:
                _, kind = _arithmetic(op, kind_of_value(a), kind_of_value(b),
                                      ast.Name("b"))
                if kind.types:
                    assert kind.magnitude >= abs(exact(a, b)), (type(op).__name__, a, b)
