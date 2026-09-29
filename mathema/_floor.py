# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The degenerate containers every claim over a vector, a matrix or a
table meets before any random draw, and the holes a random draw carries.

The floor, once per claim and parameter, in order:

- a vector: the zero vector (when the element domain holds 0), a
  constant vector, a vector of length 1; per admitted hole member, an
  all-hole vector of length 1 and of length 2, and a vector with one
  hole at the first position and one at the last;
- a matrix: the zero matrix (when the entries may be 0), a constant
  matrix, a rank-deficient one (its second row a copy of its first);
  per admitted member, one hole entry and an all-hole row;
- a table: per admitted member, one hole in every column and an
  all-hole first column;
- the container itself absent, when its domain admits that.

A length the claim's shape plan fixes is kept: the length-1 and
length-2 items then take the planned length. After the floor, a draw
carries holes at `HOLE_RATE`: one to three positions, one member per
draw, the members taken in turn.
"""
from __future__ import annotations

HOLE_RATE = 0.15


def vector_floor(holes: list, admits_zero: bool, length_free: bool,
                 absent: bool = False) -> list:
    """Intent:
        The floor of a vector parameter, as functions of the trial's
        random draw `base` (a list): each returns the degenerate vector
        built from it, or None when it cannot be built from `base`.
        `holes` are the realised hole values admitted, one per member.
    """
    items: list = []
    if admits_zero:
        items.append(lambda base: [0.0] * len(base) if base else None)
    items.append(lambda base: [base[0]] * len(base) if base else None)
    if length_free:
        items.append(lambda base: [base[0]] if base else None)
    for h in holes:
        if length_free:
            items.append(lambda base, h=h: [h])
            items.append(lambda base, h=h: [h, h])
        else:
            items.append(lambda base, h=h: [h] * len(base) if base else None)
        items.append(lambda base, h=h: [h, *base[1:]] if base else None)
        items.append(lambda base, h=h: [*base[:-1], h] if len(base) > 1 else None)
    if absent:
        items.append(lambda base: _ABSENT)
    return items


def matrix_floor(holes: list, admits_zero: bool, absent: bool = False) -> list:
    """Intent:
        The floor of a matrix parameter, as functions of the trial's
        random draw `base` (a list of equal-length rows).
    """
    items: list = []
    if admits_zero:
        items.append(lambda base: [[0.0] * len(r) for r in base] if base else None)
    items.append(lambda base: [[base[0][0]] * len(r) for r in base]
                 if base and base[0] else None)
    items.append(lambda base: [list(base[0]), list(base[0]), *map(list, base[2:])]
                 if len(base) > 1 else None)
    for h in holes:
        items.append(lambda base, h=h: [[h, *base[0][1:]], *map(list, base[1:])]
                     if base and base[0] else None)
        items.append(lambda base, h=h: [[h] * len(base[0]), *map(list, base[1:])]
                     if base and base[0] else None)
    if absent:
        items.append(lambda base: _ABSENT)
    return items


def table_floor(holes: list, absent: bool = False) -> list:
    """Intent:
        The floor of a table parameter, as functions of the trial's
        random draw `base` (a dict of equal-length column lists).
    """
    items: list = []
    for h in holes:
        items.append(lambda base, h=h: {c: [h, *col[1:]] for c, col in base.items()}
                     if base else None)
        items.append(lambda base, h=h: {c: ([h] * len(col) if k == 0 else list(col))
                                        for k, (c, col) in enumerate(base.items())}
                     if base else None)
    if absent:
        items.append(lambda base: _ABSENT)
    return items


class _Absent:
    """The floor's item for the container itself absent."""


_ABSENT = _Absent()


def gapped(values: list, holes: list, rng, turn: int) -> "tuple[list, int]":
    """Intent:
        `values` with one to three positions holding a hole, at rate
        `HOLE_RATE`, the member the `turn`-th of `holes`, as `(values,
        next turn)`; `values` unchanged when the draw carries none or
        no member is admitted.
    """
    if not holes or not values or rng.random() >= HOLE_RATE:
        return values, turn
    h = holes[turn % len(holes)]
    out = list(values)
    for k in rng.sample(range(len(out)), min(len(out), rng.randint(1, 3))):
        out[k] = h
    return out, turn + 1


def gapped_rows(rows: list, holes: list, rng, turn: int) -> "tuple[list, int]":
    """`gapped` over a matrix's entries."""
    if not holes or not rows or not rows[0] or rng.random() >= HOLE_RATE:
        return rows, turn
    h = holes[turn % len(holes)]
    out = [list(r) for r in rows]
    cells = [(i, j) for i in range(len(out)) for j in range(len(out[i]))]
    for i, j in rng.sample(cells, min(len(cells), rng.randint(1, 3))):
        out[i][j] = h
    return out, turn + 1


class ContainerDraws:
    """Intent:
        One container parameter's draws: the floor's items in order, one
        per trial, then random draws carrying holes at `HOLE_RATE`.
        `shape` is `"vec"`, `"mat"` or `"table"`.
    """

    def __init__(self, shape: str, floor: list, holes: list):
        self.shape, self.floor, self.holes = shape, list(floor), list(holes)
        self.turn = 0

    def remaining(self) -> int:
        return len(self.floor)

    def next(self, base, rng):
        """The value this trial draws, from the random draw `base`."""
        while self.floor:
            made = self.floor.pop(0)(base)
            if made is _ABSENT:
                return None
            if made is not None:
                return made
        if self.shape == "vec":
            out, self.turn = gapped(base, self.holes, rng, self.turn)
            return out
        if self.shape == "mat":
            out, self.turn = gapped_rows(base, self.holes, rng, self.turn)
            return out
        if isinstance(base, dict):
            out = {}
            for c, col in base.items():
                out[c], self.turn = gapped(col, self.holes, rng, self.turn)
            return out
        return base
