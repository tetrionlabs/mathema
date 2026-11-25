# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Named finite collections, and the functions claimed over them, for
the tests of the collection domain (`for fn in pkg.mod.NAME, ...`)."""
from __future__ import annotations

from dataclasses import dataclass


def percent_to_fraction(percent: float) -> float:
    """A percent as a fraction."""
    return percent / 100


def fraction_to_growth_factor(fraction: float) -> float:
    """A fraction as the factor it grows a value by."""
    return 1 + fraction


def halve(value: float) -> float:
    """Half a value."""
    return value / 2


def clamp(x: float, lo: float, hi: float) -> float:
    """`x` held to the interval from `lo` to `hi`."""
    return min(max(x, lo), hi)


def describe(fn) -> str:
    """One line for a function, the types it maps from and to as its
    annotations write them: `(float, float) -> float`."""
    notes = dict(fn.__annotations__)
    result = notes.pop("return", "?")
    return f"({', '.join(str(note) for note in notes.values())}) -> {result}"


#: three maps of one float to a float
STAGES = (percent_to_fraction, fraction_to_growth_factor, halve)

#: the same maps with `clamp`, of three floats, among them
MAPS_WITH_CLAMP = (percent_to_fraction, clamp, fraction_to_growth_factor)

#: the stages by the name of the step they perform
STAGES_BY_STEP = {"scale": percent_to_fraction, "grow": fraction_to_growth_factor}

#: the same, with `clamp` under a step of its own
STEPS_WITH_CLAMP = {"scale": percent_to_fraction, "hold": clamp}

#: the stages as a set
STAGE_SET = frozenset(STAGES)


def square(n: int) -> int:
    """`n` times itself."""
    return n * n


#: whole numbers whose squares are at most 9
SMALL = (1, -2, 3)

#: the same with one whose square is larger
SMALL_AND_FOUR = (1, -2, 3, 4)

#: texts
WORDS = ["alpha", "beta", "gamma"]


def shout(word: str) -> str:
    """The word in capitals."""
    return word.upper()


@dataclass(frozen=True)
class Box:
    """A box of whole-number sides."""
    width: int
    height: int


def area(box: Box) -> int:
    """The box's area."""
    return box.width * box.height


#: boxes of area at least 2
BOXES = (Box(1, 2), Box(3, 4), Box(2, 2))

#: the same with a box of area 0
BOXES_WITH_A_FLAT_ONE = (Box(1, 2), Box(0, 4))

#: no members
NOTHING = ()

#: more members than the budget enumerates
MANY = tuple(range(1500))

#: a number, not a collection
ONE_NUMBER = 42


def emit(fn) -> str:
    """The key a stage is filed under: `text-key` for the stages of
    one float."""
    return "text-key" if len(fn.__annotations__) == 2 else "tuple-key"


def decline_category(key: str) -> str:
    """The category a key is declined in: the key itself."""
    return key


#: the numbers `remember` was called with
SEEN: list = []


def remember(n: int) -> int:
    """`n`, kept in `SEEN`."""
    SEEN.append(n)
    return n
