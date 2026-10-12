# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`_rational_cover` encloses an interval of numbers in rational
endpoints, and anything that is not a number gives None. A sequence is
never scaled: a tuple times the cover's scale of ten to the ninth would
be the tuple repeated a billion times, built in memory before any
error could be raised."""
import sympy

from mathema.symbolic._extensive import _rational_cover


class _Recorded(tuple):
    """A tuple that records each multiplication instead of repeating."""

    def __new__(cls, items, seen):
        self = super().__new__(cls, items)
        self.seen = seen
        return self

    def __mul__(self, other):
        self.seen.append(other)
        return ()

    __rmul__ = __mul__


def test_a_sequence_endpoint_is_never_scaled():
    seen: list = []
    lo = _Recorded((0, sympy.Rational(1, 2), True), seen)
    assert _rational_cover(lo, -1.0934722528221021) is None
    assert _rational_cover(-1.0, _Recorded((1, 2), seen)) is None
    assert seen == []


def test_a_tuple_endpoint_gives_none():
    assert _rational_cover((0, sympy.Rational(1, 2), True), 2.0) is None
    assert _rational_cover([1, 2], 2.0) is None


def test_text_and_objects_give_none():
    assert _rational_cover("1", 2.0) is None
    assert _rational_cover(object(), 2.0) is None


def test_numbers_are_covered_by_rationals():
    half, two = sympy.Rational(1, 2), sympy.Integer(2)
    assert _rational_cover(half, two) == (half, two, False)
    scale = 10 ** 9
    assert _rational_cover(sympy.sqrt(2), two) == (
        sympy.Rational(1414213562, scale), two, True)
    assert _rational_cover(0.5, 1.25) == (half, sympy.Rational(5, 4), True)
    assert _rational_cover(-1, 3) == (-1, 3, True)
