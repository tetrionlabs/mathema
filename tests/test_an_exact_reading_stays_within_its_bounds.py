# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body is evidence for what an infinity or a nan
the float run returned means, and it stays bounded: it gives up past the
fast wall-clock cap, and before building an exact rational of more than
`_exact_body._EXACT_BITS` bits, since one product of two enormous
integers runs on inside a single operation no alarm interrupts.
Squaring x 31 times overflows the float run for x >= 2, and exactly it is
x ** (2 ** 31), a number of about two billion bits."""
import time

from mathema._exact_body import exact_callee
from mathema.claim_families import _exact_reading
from mathema.conjecture import check_conjectures, claim


def repeated_square(x: float) -> float:
    i = 0
    while i < 31:
        x = x * x
        i += 1
    return x


def repeated_square_in_place(x: float) -> float:
    i = 0
    while i < 31:
        x *= x
        i += 1
    return x


def repeated_power(x: float) -> float:
    i = 0
    while i < 31:
        x = x ** 2
        i += 1
    return x


def ten_squarings(x: float) -> float:
    i = 0
    while i < 10:
        x = x * x
        i += 1
    return x


def doubled_list(xs: list) -> list:
    ys = xs
    ys *= 2
    return xs


def test_a_reading_past_the_size_bound_declines():
    for fn in (repeated_square, repeated_square_in_place, repeated_power):
        started = time.monotonic()
        assert _exact_reading(fn, (2.0,), {}) is None, fn.__name__
        assert time.monotonic() - started < 3, fn.__name__


def test_the_definedness_claim_is_decided_within_the_cap():
    started = time.monotonic()
    (p,) = check_conjectures(repeated_square,
                             [claim("for x in [2, 3], is_defined(f)")])
    assert time.monotonic() - started < 60, time.monotonic() - started
    assert p.verdict == "unknown", (p.verdict, p.counterexample, p.note)


def test_an_in_place_product_keeps_its_meaning_in_the_reading():
    assert exact_callee(doubled_list)([1, 2]) == [1, 2, 1, 2]


def test_a_product_within_the_bound_is_exact():
    # 2 ** 1024 overflows float64 and is exact within the bound
    assert _exact_reading(ten_squarings, (2.0,), {}) == "overflow"
