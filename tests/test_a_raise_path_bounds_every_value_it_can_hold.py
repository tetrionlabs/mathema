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
