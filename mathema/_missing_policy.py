# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a function does with a missing input, read from executed calls.

A value holds no-value slots of two kinds: `absent`, the object itself
not present (a `None` argument, a `None` field of a record), and
`missing`, a hole in a slot (a `nan` float, a `nan`, `None`, `pd.NA` or
`NaT` element of a list, an array, a Series or a table column). Every
slot is named by its member word: `None` for an absence, `nan`, `null`
(a `None` held in a slot), `NA`, `NaT` for a hole.

One call at a missing input is one of five behaviours, the same five
for either kind, by counting no-value slots in the inputs and the
output:

- `raises`: the call raised.
- `drops`: the output holds no no-value slot.
- `propagates`: the output holds as many no-value slots of the same
  kind as the inputs, at the same positions where the shapes match.
- `converts`: the count is kept and the kind changes (a `None` in, a
  `nan` out; a hole in, `None` out). A hole spelled as another member
  (a `None` slot returned as `nan`) keeps its kind, and propagates.
- `introduces`: any other count, a no-value from present inputs
  included.

A reduction (an output of another shape than the input, a scalar from
a vector) has as many slots as its own shape: the count the inputs
carry into it is capped at that many, so a vector with two holes whose
mean is one `nan` propagates.

Over many calls the behaviours per (parameter, kind, member) aggregate
to one behaviour, or to `mixed` with a witness for each behaviour seen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

BEHAVIOURS = ("raises", "drops", "propagates", "converts", "introduces")
ABSENT, MISSING = "absent", "missing"


@dataclass(frozen=True)
class Slot:
    """One no-value slot: its position inside the value (`()` for the
    value itself), its kind and its member word."""
    position: tuple
    kind: str
    member: str


@dataclass(frozen=True)
class Slots:
    """The no-value slots of one value and its shape (`()` for a
    scalar, the length or the rows and columns of a container, the
    field names of a record)."""
    slots: tuple
    shape: tuple

    def count(self, kind: "str | None" = None) -> int:
        return sum(1 for s in self.slots if kind is None or s.kind == kind)

    def capacity(self) -> int:
        """How many slots the value has: one for a scalar, one per
        element, entry or cell for a container."""
        n = 1
        for d in self.shape:
            n *= d if isinstance(d, int) else 1
        return max(n, 1)


def _hole_word(v) -> "str | None":
    """The member word of a value held in a slot, or None for a value."""
    from .domain import member_of
    if v is None:
        return "null"
    word = member_of(v)
    return word if word not in (None, "None") else None


def _table_columns(value) -> "dict | None":
    """`{name: [cell, ...]}` for a pandas or polars DataFrame, or a dict
    of equal-length columns (a table as drawn), or None."""
    if isinstance(value, dict) and value and all(
            isinstance(c, (list, tuple)) for c in value.values()):
        return {str(k): list(c) for k, c in value.items()}
    module = type(value).__module__.split(".")[0]
    if module == "pandas" and type(value).__name__ == "DataFrame":
        return {str(c): value[c].tolist() for c in value.columns}
    if module == "polars" and type(value).__name__ == "DataFrame":
        return {str(c): value[c].to_list() for c in value.columns}
    return None


def _cells(value) -> "list | None":
    """A 1-D container's elements as Python values, or None."""
    module = type(value).__module__.split(".")[0]
    if isinstance(value, (list, tuple)) and not any(
            isinstance(v, (list, tuple)) for v in value):
        return list(value)
    if module == "pandas" and type(value).__name__ == "Series":
        return value.tolist()
    if module == "polars" and type(value).__name__ == "Series":
        return value.to_list()
    if module == "numpy" and getattr(value, "ndim", None) == 1:
        return value.tolist()
    return None


def _rows(value) -> "list | None":
    """A matrix's rows as lists of Python values, or None."""
    module = type(value).__module__.split(".")[0]
    if module == "numpy" and getattr(value, "ndim", None) == 2:
        return value.tolist()
    if isinstance(value, (list, tuple)) and value and all(
            isinstance(r, (list, tuple)) for r in value):
        return [list(r) for r in value]
    return None


def _fields(value) -> "dict | None":
    """A record's fields (a dict, a pydantic model, a dataclass or an
    object with attributes), or None for anything else."""
    if isinstance(value, dict):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump) and type(value).__module__.split(".")[0] != "pandas":
        try:
            return {k: getattr(value, k) for k in dump()}
        except Exception:
            return None
    fields = getattr(value, "__dataclass_fields__", None)
    if fields:
        return {k: getattr(value, k) for k in fields}
    return None


def no_value_slots(value) -> Slots:
    """Intent:
        The no-value slots `value` holds: itself when it is `None` (an
        absence) or a scalar hole; each hole element of a list, an
        array, a Series or a matrix; each hole cell of a table, by
        column; each `None` field of a record (the field's absence)
        and each hole field.
    """
    from .domain import absence_word
    absent = absence_word(value)
    if absent is not None:
        return Slots((Slot((), ABSENT, absent),), ())
    columns = _table_columns(value)
    if columns is not None:
        slots = tuple(Slot((c, k), MISSING, w)
                      for c, cells in columns.items()
                      for k, v in enumerate(cells)
                      if (w := _hole_word(v)) is not None)
        height = len(next(iter(columns.values()))) if columns else 0
        return Slots(slots, (height, len(columns)))
    rows = _rows(value)
    if rows is not None:
        slots = tuple(Slot((i, j), MISSING, w)
                      for i, row in enumerate(rows) for j, v in enumerate(row)
                      if (w := _hole_word(v)) is not None)
        return Slots(slots, (len(rows), len(rows[0]) if rows else 0))
    cells = _cells(value)
    if cells is not None:
        slots = tuple(Slot((k,), MISSING, w) for k, v in enumerate(cells)
                      if (w := _hole_word(v)) is not None)
        return Slots(slots, (len(cells),))
    fields = _fields(value)
    if fields is not None:
        slots = []
        for name, v in fields.items():
            if (word := absence_word(v)) is not None:
                slots.append(Slot((name,), ABSENT, word))
            elif (w := _hole_word(v)) is not None:
                slots.append(Slot((name,), MISSING, w))
        return Slots(tuple(slots), (len(fields),))
    word = _hole_word(value)
    if word is not None:
        return Slots((Slot((), MISSING, word),), ())
    return Slots((), ())


def classify_call(inputs: dict, output=None, raised: "str | None" = None) -> str:
    """Intent:
        The behaviour of one call, from its arguments `{param: value}`
        and its output (or the name of the exception it `raised`):
        `raises`, `drops`, `propagates`, `converts` or `introduces`,
        by the counts in the module docstring.
    """
    if raised is not None:
        return "raises"
    ins = [s for s in (no_value_slots(v) for v in inputs.values()) if s.count()]
    out = no_value_slots(output)
    if out.count() == 0:
        return "drops"
    total_in = sum(s.count() for s in ins)
    # one holding argument of the output's own shape keeps its count and
    # positions; anything else carries at most as many as the output has
    aligned = len(ins) == 1 and ins[0].shape == out.shape
    carried = total_in if aligned else min(total_in, out.capacity())
    if total_in == 0 or out.count() != carried:
        return "introduces"
    kinds_in = {sl.kind for s in ins for sl in s.slots}
    kinds_out = {sl.kind for sl in out.slots}
    if kinds_out <= kinds_in and len(kinds_in) == 1:
        if aligned and out.shape != () and \
                {sl.position for sl in ins[0].slots} != {sl.position for sl in out.slots}:
            return "introduces"
        return "propagates"
    if not (kinds_out & kinds_in):
        return "converts"
    return "introduces"


def member_changes(inputs: dict, output) -> list:
    """Intent:
        `[(param, position, value, member), ...]`: the slots of the one
        holding argument whose hole comes back at the same position of an
        output of the same shape spelled as another member (a `None`
        element returned as `nan`), with the value drawn and the member
        returned. A change of spelling within a kind, which is no
        conversion.
    """
    holding = [(p, v, no_value_slots(v)) for p, v in inputs.items()]
    holding = [(p, v, sl) for p, v, sl in holding if sl.count()]
    out = no_value_slots(output)
    if len(holding) != 1 or holding[0][2].shape != out.shape or out.shape == ():
        return []
    p, value, slots = holding[0]
    returned = {sl.position: sl for sl in out.slots}
    cells = _cells(value)
    changes = []
    for sl in slots.slots:
        back = returned.get(sl.position)
        if back is not None and back.kind == sl.kind and back.member != sl.member:
            drawn = cells[sl.position[0]] if cells is not None and len(sl.position) == 1 \
                else sl.member
            changes.append((p, sl.position, drawn, back.member))
    return changes


def keys_of(inputs: dict) -> list:
    """`[(param, kind, member), ...]`: every missing member each argument
    holds, in argument order, each once."""
    keys: list = []
    for p, v in inputs.items():
        for sl in no_value_slots(v).slots:
            key = (p, sl.kind, sl.member)
            if key not in keys:
                keys.append(key)
    return keys


def _shown(value) -> str:
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


@dataclass
class PolicyTable:
    """The behaviours seen per (parameter, kind, member) over many calls,
    the first witness of each behaviour kept."""
    seen: dict = field(default_factory=dict)

    def add(self, inputs: dict, output=None, raised: "str | None" = None) -> None:
        """Classify one call and file it under every missing member its
        arguments hold."""
        keys = keys_of(inputs)
        if not keys:
            return
        behaviour = classify_call(inputs, output, raised)
        witness = ", ".join(f"{p}={_shown(v)}" for p, v in inputs.items())
        for key in keys:
            self.seen.setdefault(key, {}).setdefault(behaviour, witness)

    def behaviour(self, key: tuple) -> "str | None":
        """The one behaviour seen for `key`, `mixed` for more than one,
        None when nothing was seen."""
        found = self.seen.get(key)
        if not found:
            return None
        return next(iter(found)) if len(found) == 1 else "mixed"

    def summary(self) -> dict:
        """`{param: {member: behaviour}}` over every key seen."""
        out: dict = {}
        for (p, _kind, member), _found in self.seen.items():
            out.setdefault(p, {})[member] = self.behaviour((p, _kind, member))
        return out

    def mixed(self) -> dict:
        """`{param: {member: {behaviour: witness}}}` for the mixed keys."""
        out: dict = {}
        for (p, _kind, member), found in self.seen.items():
            if len(found) > 1:
                out.setdefault(p, {})[member] = dict(found)
        return out
