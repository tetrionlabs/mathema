# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The kind of tolerance an `f =:= g` or `a ~= b` claim states.

Beside a bare number (an absolute allowance), the tolerance of an
equivalence or an approximate equality may name its kind:

- `{abs: x}` allows `|a - b| <= x`;
- `{rel: x}` allows `|a - b| <= x * max(|a|, |b|)`;
- `{ulp: n}` allows `n` units in the last place of `max(|a|, |b|)`, `n`
  a whole number;

each with an optional `floor: x`, an absolute allowance added to the
kind's own part, so the allowance is `bound + floor`: the relative
plus absolute error of the standard rounding-error model. The floor
applies in full, uncapped. A kind carries no other slack. Every value
is a non-negative finite number.

On a computation line the allowance is computed in float64
(`ToleranceKind.allows`). On a mathematics line it is decided exactly
(`ToleranceKind.allows_exactly`): each number of the kind is the
decimal the claim writes (as a literal in the claim's text is), and an
ulp is that of the float64 nearest `max(|a|, |b|)`.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from fractions import Fraction

#: the kinds a tolerance may name, in the order a record writes them
KINDS = ("abs", "rel", "ulp")


@dataclass(frozen=True)
class ToleranceKind:
    """A tolerance with a kind: `kind` is `abs`, `rel` or `ulp`,
    `value` its allowance (a count of units in the last place for
    `ulp`), and `floor` the absolute allowance beside it, or None."""
    kind: str
    value: float
    floor: float | None = None

    def written(self) -> dict:
        """The tolerance as a claim writes it: `{rel: 1e-12, floor:
        1e-15}`."""
        out: dict = {self.kind: self.value}
        if self.floor is not None:
            out["floor"] = self.floor
        return out

    def bound(self, a: float, b: float) -> float:
        """The gap two finite values may differ by, in float64: the
        kind's part (`x`, `x * max(|a|, |b|)`, or `n` ulps of
        `max(|a|, |b|)`) plus the floor."""
        scale = max(abs(a), abs(b))
        if self.kind == "abs":
            part = self.value
        elif self.kind == "rel":
            part = self.value * scale
        else:
            part = self.value * math.ulp(scale)
        return part + (self.floor or 0.0)

    def allows(self, a: float, b: float) -> bool:
        """Whether two finite values are within this tolerance:
        `|a - b| <= bound + floor`, computed in float64."""
        return abs(a - b) <= self.bound(a, b)

    def bound_exactly(self, a, b) -> Fraction:
        """The gap two real values may differ by, as an exact rational:
        the kind's numbers read as the decimals they are written as,
        an ulp that of the float64 nearest `max(|a|, |b|)` (the largest
        finite float64's for a magnitude beyond float64's range)."""
        scale = max(abs(Fraction(a)), abs(Fraction(b)))
        if self.kind == "abs":
            part = _decimal(self.value)
        elif self.kind == "rel":
            part = _decimal(self.value) * scale
        else:
            try:
                nearest = float(scale)
            except OverflowError:
                nearest = sys.float_info.max
            if math.isinf(nearest):
                nearest = sys.float_info.max
            part = int(self.value) * Fraction(math.ulp(nearest))
        return part + (_decimal(self.floor) if self.floor is not None
                       else Fraction(0))

    def allows_exactly(self, a, b) -> bool:
        """Whether two real values (rationals, integers or floats, each
        read as the exact number it is) are within this tolerance,
        decided exactly."""
        return abs(Fraction(a) - Fraction(b)) <= self.bound_exactly(a, b)

    def reading(self, lhs: str, rhs: str) -> str:
        """`abs(lhs - rhs) <= ...`, the inequality `lhs ~= rhs` is read
        as under this tolerance, in words for a record's note."""
        scale = f"max(abs({lhs}), abs({rhs}))"
        if self.kind == "abs":
            bound = number_text(self.value)
        elif self.kind == "rel":
            bound = f"{number_text(self.value)} * {scale}"
        else:
            unit = "unit" if self.value == 1 else "units"
            bound = (f"{self.value} {unit} in the last place of the "
                     f"float64 nearest {scale}")
        if self.floor is not None:
            bound += f" + {number_text(self.floor)}"
        return f"abs({lhs} - {rhs}) <= {bound}"

    def text(self) -> str:
        """The tolerance as a claim writes it, in words: `{rel: 1e-7,
        floor: 1e-12}`."""
        amount = (str(self.value) if self.kind == "ulp"
                  else number_text(self.value))
        parts = [f"{self.kind}: {amount}"]
        if self.floor is not None:
            parts.append(f"floor: {number_text(self.floor)}")
        return "{" + ", ".join(parts) + "}"


class ToleranceKindRefused(Exception):
    """A tolerance kind reached a reading that takes one number."""


def number_text(value) -> str:
    """A number as a record writes it: `1e-7`, never `1e-07`."""
    mantissa, _, exponent = f"{value:g}".partition("e")
    return f"{mantissa}e{int(exponent)}" if exponent else mantissa


def _decimal(value) -> Fraction:
    """The exact decimal a number of a kind is written as: the shortest
    decimal that reads back as it, the reading a claim's own literals
    get."""
    return Fraction(repr(value)) if isinstance(value, float) \
        else Fraction(value)


def bare(value, where: str):
    """Intent:
        `value` where one number is read: a bare number or None comes
        back as it is.

    Raises:
        ToleranceKindRefused: `value` is a kind, which is no one number;
            the message names `where`.
    """
    if isinstance(value, ToleranceKind):
        raise ToleranceKindRefused(
            f"{where} reads the tolerance as one number, and "
            f"{value.text()} is a kind, not one number")
    return value


def _number(value, what: str) -> float:
    """Intent:
        `value` as a non-negative finite number.

    Raises:
        ValueError: anything else, naming `what`.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{what} must be a non-negative number, not "
                         f"{value!r}")
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"{what} must be a non-negative number, not "
                         f"{value!r}") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{what} must be a non-negative number, not "
                         f"{value!r}")
    return number


def read_tolerance(value):
    """Intent:
        A claim's tolerance as written, read: a mapping naming one kind
        with an optional floor is a `ToleranceKind`; anything else (None,
        a bare number, a `ToleranceKind`) is returned as it is.

    Raises:
        ValueError: a negative or non-finite value, a mapping that names
            no kind or more than one, a key that is not a kind or
            `floor`, or a `ulp` count that is not a whole number.
    """
    if not isinstance(value, dict):
        return value
    unknown = sorted(str(k) for k in value if k not in (*KINDS, "floor"))
    if unknown:
        raise ValueError(
            f"the tolerance names {', '.join(unknown)}, which is not a "
            f"kind; write one of {{abs: x}}, {{rel: x}} or {{ulp: n}}, "
            f"each with an optional floor: x")
    kinds = [k for k in KINDS if k in value]
    if len(kinds) != 1:
        raise ValueError(
            f"the tolerance names {len(kinds)} kinds where it takes one; "
            f"write one of {{abs: x}}, {{rel: x}} or {{ulp: n}}, each with "
            f"an optional floor: x")
    kind = kinds[0]
    amount = _number(value[kind], f"the tolerance's {kind}")
    if kind == "ulp":
        if amount != int(amount):
            raise ValueError(f"the tolerance's ulp counts units in the "
                             f"last place, a whole number, not "
                             f"{value[kind]!r}")
        amount = int(amount)
    floor = (None if value.get("floor") is None
             else _number(value["floor"], "the tolerance's floor"))
    return ToleranceKind(kind, amount, floor)


def written_tolerance(value):
    """A tolerance as a record writes it: a kind as its mapping, a
    number as itself."""
    return value.written() if isinstance(value, ToleranceKind) else value
