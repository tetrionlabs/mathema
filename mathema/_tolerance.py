# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The kind of tolerance an `f =:= g` claim states.

Beside a bare number (an absolute allowance), an equivalence claim's
tolerance may name its kind:

- `{abs: x}` allows `|a - b| <= x`;
- `{rel: x}` allows `|a - b| <= x * max(|a|, |b|)`;
- `{ulp: n}` allows `n` units in the last place of `max(|a|, |b|)`, `n`
  a whole number;

each with an optional `floor: x`, an absolute allowance added to the
kind's own part, so the allowance is `bound + floor`: the relative
plus absolute error of the standard rounding-error model. The floor
applies in full, uncapped. A kind carries no other slack. Every value
is a non-negative finite number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

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
