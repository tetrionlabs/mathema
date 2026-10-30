# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval's ends are the numbers written: `[0.29, 0.31]` is
[29/100, 31/100]. The float nearest 0.29 is 0.28999999999999998, just
below it, so a draw at that end moves inward to the nearest float inside
the interval; every draw the probe runs lies inside the domain as
written."""
from fractions import Fraction

import pytest

from mathema.conjecture import check_conjectures, claim

import sys

#: the points the function itself ran at: a run of its exact reading's
#: float shadow, which reads the float nearest an exact point, is not a
#: draw
SEEN: list = []
_CODE: list = []


def recorded(b: float) -> float:
    if sys._getframe().f_code is _CODE[0]:
        SEEN.append(b)
    return b


_CODE.append(recorded.__code__)


@pytest.mark.parametrize("law,lo,hi", [
    ("for b in [0.29, 0.31], f(b) >= 0", Fraction(29, 100), Fraction(31, 100)),
    ("for b in [0.1, 0.7], f(b) >= 0", Fraction(1, 10), Fraction(7, 10)),
])
def test_every_draw_lies_inside_the_interval_as_written(law, lo, hi):
    SEEN.clear()
    (p,) = check_conjectures(recorded, [claim(law, route="probe")])
    drawn = [b for b in SEEN if isinstance(b, float) and b == b]
    assert drawn, p
    outside = [b for b in drawn if not lo <= Fraction(b) <= hi]
    assert outside == [], outside


@pytest.mark.parametrize("law,lo,hi", [
    ("for b in [1/3, 1], f(b) >= 0", Fraction(1, 3), Fraction(1)),
    ("for b in [0, 2/3], f(b) >= 0", Fraction(0), Fraction(2, 3)),
])
def test_an_end_written_as_a_fraction_is_that_fraction(law, lo, hi):
    # float(1/3) = 0.333...3148 lies below 1/3, outside [1/3, 1];
    # float(2/3) = 0.666...6297 lies below 2/3, inside [0, 2/3]: every
    # draw lies inside the interval the fractions write
    SEEN.clear()
    (p,) = check_conjectures(recorded, [claim(law, route="probe")])
    drawn = [b for b in SEEN if isinstance(b, float) and b == b]
    assert drawn, p
    outside = [b for b in drawn if not lo <= Fraction(b) <= hi]
    assert outside == [], outside
