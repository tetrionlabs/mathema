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


def _is_ndarray(value) -> bool:
    """Whether `value` is a numpy array, a subclass included."""
    import sys
    np = sys.modules.get("numpy")
    return np is not None and isinstance(value, np.ndarray)


def _array_list(value) -> list:
    """A numpy array as nested Python lists, each position an array
    marks in `hole_values` (a hole drawn as `None` that the array holds
    as nan) restored to the value it stands for."""
    out = value.tolist()
    for position, held in (getattr(value, "hole_values", None) or {}).items():
        target = out
        for k in position[:-1]:
            target = target[k]
        target[position[-1]] = held
    return out


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
    if _is_ndarray(value) and value.ndim == 1:
        return _array_list(value)
    return None


def _rows(value) -> "list | None":
    """A matrix's rows as lists of Python values, or None."""
    if _is_ndarray(value) and value.ndim == 2:
        return _array_list(value)
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


def classify_call(inputs: dict, output=None, raised: "str | None" = None,
                  unseen: tuple = ()) -> str:
    """Intent:
        The behaviour of one call, from its arguments `{param: value}`
        and its output (or the name of the exception it `raised`):
        `raises`, `drops`, `propagates`, `converts` or `introduces`,
        by the counts in the module docstring. `unseen` lists the kinds
        of no-values the arguments hold that no slot shows (a key left
        out, reached by a path), counted as inputs.
    """
    if raised is not None:
        return "raises"
    ins = [s for s in (no_value_slots(v) for v in inputs.values()) if s.count()]
    out = no_value_slots(output)
    if out.count() == 0:
        return "drops"
    if unseen and not ins:
        kinds_out = {sl.kind for sl in out.slots}
        if out.count() > 1 or out.shape != ():
            return "introduces"
        return "propagates" if kinds_out <= set(unseen) else "converts"
    total_in = sum(s.count() for s in ins)
    # holding arguments of the output's own shape carry the union of
    # their hole positions, count and place; anything else carries at
    # most as many as the output has
    aligned = bool(ins) and all(s.shape == out.shape for s in ins) and (
        len(ins) == 1 or out.shape != ())
    union = {sl.position for s in ins for sl in s.slots}
    carried = (len(union) if len(ins) > 1 else total_in) if aligned \
        else min(total_in, out.capacity())
    if total_in == 0 or out.count() != carried:
        return "introduces"
    kinds_in = {sl.kind for s in ins for sl in s.slots}
    kinds_out = {sl.kind for sl in out.slots}
    if kinds_out <= kinds_in and len(kinds_in) == 1:
        if aligned and out.shape != () and union != {sl.position for sl in out.slots}:
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


def record_fields(value) -> "dict | None":
    """The fields of a value read as a record (a dict of values, a
    pydantic model, a dataclass), or None for a table, a vector, a
    matrix or anything else."""
    if _table_columns(value) is not None or _rows(value) is not None \
            or _cells(value) is not None:
        return None
    return _fields(value)


def path_members(value, root: str, path: str) -> list:
    """Intent:
        `[(kind, member, where), ...]`: what a path (`o.lines[*].qty`)
        reaches from `value`, the value of its root parameter, that is not
        a value: `("absent", "null", ...)` for a field or key holding
        `None`, `("absent", "unset", ...)` for one not there, an index
        past the end or a step below an absent object, and `("missing",
        member, ...)` for a hole, a `None` element being `null`. `where`
        is the concrete steps taken.
    """
    from .domain import ABSENT_NULL, ABSENT_UNSET, member_of, path_leaves, path_steps
    out = []
    for where, leaf in path_leaves(value, path_steps(path[len(root):])):
        if leaf == ABSENT_NULL:
            out.append((ABSENT, "null", where))
        elif leaf == ABSENT_UNSET:
            out.append((ABSENT, "unset", where))
        else:
            word = member_of(leaf)
            if word is not None:
                out.append((MISSING, "null" if word == "None" else word, where))
    return out


def is_path(name: str) -> bool:
    """Whether a policy's target names a path (`o.note`, `o.lines[*]`)
    rather than a parameter."""
    return "." in name or "[" in name


def path_root(name: str) -> str:
    """The parameter a path starts at: `o` for `o.lines[*].qty`."""
    for i, ch in enumerate(name):
        if ch in ".[":
            return name[:i]
    return name


def keys_of(inputs: dict, paths: "dict | None" = None) -> list:
    """Intent:
        `[(param, kind, member), ...]`: every missing member each argument
        holds, in argument order, each once. A record's field or key
        holding a no-value is filed under its path (`o.note`, member
        `null` for an absence), and each path in `paths` (`{param:
        [path, ...]}`, the paths a claim binds) under the path as written
        with the member it reached, `unset` for a key left out. A field
        on the way to a bound path is left to the path.
    """
    keys: list = []

    def add(key) -> None:
        if key not in keys:
            keys.append(key)
    for p, v in inputs.items():
        bound = list((paths or {}).get(p, ()))
        fields = record_fields(v) if v is not None else None
        for sl in no_value_slots(v).slots:
            if fields is not None and sl.position:
                path = f"{p}.{sl.position[0]}"
                if any(b != path and b.startswith(path) for b in bound):
                    continue
                add((path, sl.kind, "null" if sl.kind == ABSENT else sl.member))
            else:
                add((p, sl.kind, sl.member))
        for path in bound:
            for kind, member, _where in path_members(v, p, path):
                add((path, kind, member))
    return keys


def unseen_kinds(inputs: dict, keys: list) -> tuple:
    """The kinds of the keys no slot of the arguments shows: a path's
    `unset`."""
    return tuple(k for _q, k, m in keys if m == "unset")


def value_at(inputs: dict, name: str):
    """The argument a key's parameter or path starts at."""
    return inputs.get(path_root(name))


@dataclass
class PolicyTable:
    """The behaviours seen per (parameter, kind, member) over many calls,
    the first witness of each behaviour kept."""
    seen: dict = field(default_factory=dict)
    # the exception first raised per key
    raised: dict = field(default_factory=dict)

    def add(self, inputs: dict, output=None, raised: "str | None" = None,
            paths: "dict | None" = None) -> None:
        """Classify one call and file it under every missing member its
        arguments hold, and every path in `paths` reaches."""
        keys = keys_of(inputs, paths)
        if not keys:
            return
        from ._missing_words import point_shown
        behaviour = classify_call(inputs, output, raised, unseen_kinds(inputs, keys))
        witness = point_shown(inputs)
        for key in keys:
            self.seen.setdefault(key, {}).setdefault(behaviour, witness)
            if raised is not None:
                self.raised.setdefault(key, raised)

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

    def mixed_raised(self) -> dict:
        """`{param: {member: exception}}` for the mixed keys that raised."""
        out: dict = {}
        for key, found in self.seen.items():
            if len(found) > 1 and key in self.raised:
                out.setdefault(key[0], {})[key[2]] = self.raised[key]
        return out
