# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""How much of a parameter's domain a claim ranges over, counted in the
values the parameter's type can actually hold.

A float parameter holds float64 doubles, so a range covers the doubles
inside it: `[0, 1]` holds about a quarter of all finite doubles, because
doubles crowd towards zero, and `[0, inf)` about half. An int parameter
is unbounded, so a bounded range of integers is a vanishing share of it
and a half-line half of it, unless the function bounds the parameter
itself to a bounded range, when the integers in that range are counted. A finite domain
counts its members. Any other type (a string, a language, an object)
has unboundedly many values, so a finite set or a narrower language is
a vanishing share and only a binding as wide as the type covers it.

Every share is between 0 and 1. A region is one of:

- `("points", frozenset)`, a finite set of values;
- `("intervals", ((lo, hi), ...), integer)`, closed ranges, of
  integers only when `integer`;
- `("whole",)`, everything the parameter's type holds;
- `("narrower",)`, a narrower set no count is made for (a language).
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

_MAX = 1.7976931348623157e308


def _ordinal(x: float) -> int:
    """The position of a finite double among all doubles in order, with
    0.0 and -0.0 both at 0, so the doubles in `[a, b]` number
    `_ordinal(b) - _ordinal(a) + 1`."""
    x = max(-_MAX, min(_MAX, float(x)))
    (bits,) = struct.unpack("<q", struct.pack("<d", abs(x)))
    return -bits if x < 0 else bits


_ALL_DOUBLES = _ordinal(_MAX) - _ordinal(-_MAX) + 1


@dataclass(frozen=True)
class Universe:
    """What one parameter's domain holds, for counting: `kind` is
    "float", "int", "finite" or "other"; `members` the members of a
    finite domain; `ranges` the closed ranges the function bounds a
    numeric parameter to, empty when it is unbounded."""
    kind: str = "other"
    members: frozenset = frozenset()
    ranges: tuple = ()


def _real(v) -> "float | None":
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _merged(intervals) -> list:
    """Closed intervals sorted and merged where they overlap."""
    out: list = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _clipped(intervals, ranges) -> list:
    """The parts of `intervals` inside `ranges` (all of them when
    `ranges` is empty), merged."""
    if not ranges:
        return _merged(intervals)
    return _merged([(max(lo, a), min(hi, b)) for lo, hi in intervals
                    for a, b in ranges if max(lo, a) <= min(hi, b)])


def _doubles(intervals) -> int:
    return sum(_ordinal(hi) - _ordinal(lo) + 1 for lo, hi in intervals)


def _integers(intervals) -> float:
    """How many integers the intervals hold, `inf` when unbounded."""
    total = 0.0
    for lo, hi in intervals:
        if math.isinf(lo) or math.isinf(hi):
            return math.inf
        total += max(0, math.floor(hi) - math.ceil(lo) + 1)
    return total


def _half_lines(intervals) -> float:
    """The share of the unbounded integers the intervals hold: a
    bounded stretch is a vanishing share, each half-line half."""
    if any(math.isinf(lo) and math.isinf(hi) for lo, hi in intervals):
        return 1.0
    below = any(math.isinf(lo) for lo, _hi in intervals)
    above = any(math.isinf(hi) for _lo, hi in intervals)
    return 0.5 * below + 0.5 * above


def share(regions, universe: Universe) -> float:
    """Intent:
        The share of `universe` the union of `regions` covers, counted
        in the values the parameter's type holds (see the module
        docstring), between 0 and 1.
    """
    regions = list(regions)
    if any(r[0] == "whole" for r in regions):
        return 1.0
    points = frozenset().union(*[r[1] for r in regions if r[0] == "points"])
    spans = [r for r in regions if r[0] == "intervals"]
    if universe.kind == "finite":
        if not universe.members:
            return 0.0
        covered = set(points & universe.members)
        for _kind, intervals, integer in spans:
            for m in universe.members:
                x = _real(m)
                if x is not None and (not integer or x == int(x)) and any(
                        lo <= x <= hi for lo, hi in intervals):
                    covered.add(m)
        return len(covered) / len(universe.members)
    if universe.kind not in ("float", "int"):
        return 0.0
    numbers = {x for x in (_real(v) for v in points) if x is not None}
    if universe.ranges:
        numbers = {x for x in numbers
                   if any(a <= x <= b for a, b in universe.ranges)}
    if universe.kind == "int":
        covered = _clipped([iv for _k, ivs, _i in spans for iv in ivs],
                           universe.ranges)
        whole = _integers(_merged(universe.ranges)) if universe.ranges \
            else math.inf
        if math.isinf(whole):
            halves = _half_lines(universe.ranges) if universe.ranges else 1.0
            return min(1.0, _half_lines(covered) / halves) if halves else 0.0
        stray = {x for x in numbers if x == int(x)
                 and not any(lo <= x <= hi for lo, hi in covered)}
        return min(1.0, (_integers(covered) + len(stray)) / whole) \
            if whole else 0.0
    real = _clipped([iv for _k, ivs, integer in spans if not integer
                     for iv in ivs], universe.ranges)
    whole = _doubles(_merged(universe.ranges)) if universe.ranges \
        else _ALL_DOUBLES
    whole_numbers = _integers(_clipped(
        [iv for _k, ivs, integer in spans if integer for iv in ivs],
        universe.ranges))
    if math.isinf(whole_numbers):
        whole_numbers = 0.0         # unboundedly many integers, a vanishing share
    loose = sum(1 for x in numbers if not any(lo <= x <= hi for lo, hi in real))
    return min(1.0, (_doubles(real) + whole_numbers + loose) / whole)


def region(bound) -> tuple:
    """Intent:
        The region a domain value (a claim's binding, or a parameter's
        completed domain) names, in the shapes `share` reads: a finite
        set, closed ranges (of integers for a `Z`/`N` domain), the
        whole type (`R`, an unbounded named type), or a narrower set no
        count is made for (a language).
    """
    from .domain import Domain, LanguageRef, is_sentinel
    if bound is None:
        return ("whole",)
    if isinstance(bound, frozenset):
        return ("points", frozenset(v for v in bound if not is_sentinel(v)))
    if isinstance(bound, str):
        if bound in ("Z", "N"):
            return ("intervals", ((0.0 if bound == "N" else -math.inf,
                                   math.inf),), True)
        return ("whole",)
    if isinstance(bound, LanguageRef):
        return ("narrower",)
    if isinstance(bound, tuple):
        lo, hi = (_real(v) for v in bound[:2])
        if lo is None or hi is None:
            return ("narrower",)
        return ("intervals", ((lo, hi),), False)
    if isinstance(bound, Domain):
        if bound.base_type == "L" or bound.dims:
            return ("narrower",)
        integer = bound.base_type in ("Z", "N")
        pieces = [p for p in bound.pieces if not (
            isinstance(p, frozenset) and all(is_sentinel(v) for v in p))]
        if not pieces:
            if integer:
                return ("intervals", ((0.0 if bound.base_type == "N"
                                       else -math.inf, math.inf),), True)
            return ("whole",)
        if all(isinstance(p, frozenset) for p in pieces):
            return ("points", frozenset(v for p in pieces for v in p
                                        if not is_sentinel(v)))
        spans = []
        for p in pieces:
            if isinstance(p, frozenset) or not isinstance(p, tuple):
                return ("narrower",)
            lo, hi = (_real(v) for v in p[:2])
            if lo is None or hi is None:
                return ("narrower",)
            if bound.base_type == "N":
                lo = max(lo, 0.0)
            spans.append((lo, hi))
        return ("intervals", tuple(spans), integer)
    return ("narrower",)


def universe(bound, kind: str, members: frozenset = frozenset()) -> Universe:
    """Intent:
        The `Universe` of one parameter: a finite domain by its
        `members`, a numeric one (`kind` "scalar" or "int", or a `Z`/`N`
        domain) by the ranges its completed domain `bound` holds it to,
        anything else as "other".
    """
    if members:
        return Universe("finite", frozenset(members))
    reading = region(bound)
    integer = kind == "int" or (reading[0] == "intervals" and reading[2])
    if kind not in ("scalar", "int", "unknown") and not integer:
        return Universe("other")
    ranges = ()
    if reading[0] == "intervals" and not all(
            math.isinf(lo) and math.isinf(hi) for lo, hi in reading[1]):
        ranges = tuple(_merged(reading[1]))
    elif reading[0] not in ("whole", "intervals"):
        return Universe("other")
    return Universe("int" if integer else "float", ranges=ranges)
