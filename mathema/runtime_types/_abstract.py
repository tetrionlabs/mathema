# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Abstract values: what a vector, a matrix or a table IS, apart from
the runtime type a library hands a function.

A sampler draws an abstract value; a runtime type adapter realises it
as the object the function receives (a list, a `numpy.ndarray`, a
`pandas.Series`) and observes what the function returns back into an
abstract value. A missing position is a property of the abstract
value, a set of positions, never a float NaN, so each runtime type
represents it natively (`None` in a list, NaN in a float array or a
pandas float Series, null in polars).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


#: the types the elements of a vector, and so the cells of a table
#: column, can have
ELEMENT_TYPES = ("float", "int", "bool", "str")


@dataclass(frozen=True)
class AbstractVec:
    """A vector of `len(values)` numbers, strings or booleans, with
    `missing` the positions that hold no value and `spelling` the
    member they are held as (`nan`, `null`, `NA`), None for the runtime
    type's own default; `members` the member each missing position
    holds, `((position, member), ...)`, when they are not all one. The
    value stored at a missing position is NaN and carries no meaning.
    `labels` names
    each position when the vector is indexed by name (a pandas Series
    labelled by column names, as a table's reduction answers), `()`
    when its positions carry no names. `element` is the type of its
    elements, one of `ELEMENT_TYPES`, when it was drawn or returned as
    that type; None when the values say it (`element_type`). A vector
    of strings or booleans holds them in `values` as they are."""
    values: tuple
    missing: frozenset = frozenset()
    spelling: "str | None" = None
    members: tuple = ()
    labels: tuple = ()
    element: "str | None" = None

    def __len__(self) -> int:
        return len(self.values)

    def non_missing(self) -> tuple:
        """The values at the positions that are not missing, in order."""
        return tuple(v for k, v in enumerate(self.values)
                     if k not in self.missing)


@dataclass(frozen=True)
class AbstractMat:
    """A matrix as a tuple of equal-length rows of numbers, with
    `missing` the `(row, column)` positions that hold no value (NaN in
    `rows`) and `spelling` the member they are held as, or `members`
    per position when they are not all one."""
    rows: tuple
    missing: frozenset = frozenset()
    spelling: "str | None" = None
    members: tuple = ()

    @property
    def shape(self) -> tuple:
        return (len(self.rows), len(self.rows[0]) if self.rows else 0)


def element_type(vec: AbstractVec) -> str:
    """Intent:
        The type of a vector's elements, one of `ELEMENT_TYPES`: its
        `element` when stated, else what its values show, `str` or
        `bool` when every value present is one, `int` when every value
        present is an integer, and `float` otherwise (a vector of holes
        only, or of no positions, included).
    """
    if vec.element is not None:
        return vec.element
    present = vec.non_missing()
    if present and all(isinstance(v, bool) for v in present):
        return "bool"
    if present and all(isinstance(v, str) for v in present):
        return "str"
    if present and all(isinstance(v, int) for v in present):
        return "int"
    return "float"


@dataclass(frozen=True)
class AbstractTable:
    """Named columns of equal length, each an `AbstractVec`, in order.
    `column_names`, `column_types`, `column` and `row_count` read it
    whatever runtime type it was realised as or observed from."""
    columns: dict = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(tuple(self.columns.items()))

    def column_names(self) -> tuple:
        """The column names, in order."""
        return tuple(self.columns)

    def column_types(self) -> dict:
        """`{name: type}`, each column's `element_type`, in order."""
        return {name: element_type(col) for name, col in self.columns.items()}

    def column(self, name: str) -> AbstractVec:
        """Intent:
            The column called `name`.

        Raises:
            KeyError: the table has no such column; the message names
                the columns it has.
        """
        try:
            return self.columns[name]
        except KeyError:
            raise KeyError(f"the table has no column {name!r} (columns: "
                           f"{', '.join(self.columns) or 'none'})") from None

    def row_count(self) -> int:
        """The number of rows: the length of its columns, 0 with none."""
        return len(next(iter(self.columns.values()))) if self.columns else 0


class _NotMine:
    """What an adapter's `observe` returns for an object that is not
    one of its runtime types."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NotMine"

    def __bool__(self) -> bool:
        return False


#: the one `observe` answer meaning "not one of my runtime types"
NotMine = _NotMine()


def _is_missing_element(v) -> bool:
    from ..domain import is_missing
    return is_missing(v)


def _one_spelling(words) -> "str | None":
    """The member every hole is held as, when they all share one."""
    found = set(words)
    return found.pop() if len(found) == 1 else None


def _members(words: dict) -> tuple:
    """`((position, member), ...)` when the holes are not all one
    member, else `()`."""
    if len(set(words.values())) < 2:
        return ()
    return tuple(sorted(words.items()))


def _hole_word(v) -> "str | None":
    from ..domain import member_of
    return member_of(v)


def _is_number(v) -> bool:
    return (isinstance(v, (int, float, complex)) and not isinstance(v, bool)
            or type(v).__module__ == "numpy" and hasattr(v, "item")
            and getattr(v, "ndim", 0) == 0)


def _number(v):
    """A plain Python number for `v` (a numpy scalar becomes its
    `.item()`)."""
    if type(v).__module__ == "numpy" and hasattr(v, "item"):
        return v.item()
    return v


def abstract_of(value):
    """Intent:
        The abstract value a plain drawn value stands for: a list or
        tuple of numbers, of strings or of booleans (missing elements
        allowed) is an `AbstractVec`, its `element` `str` or `bool`
        for strings or booleans, a list of equal-length lists of
        numbers an `AbstractMat`, a dict of such lists an
        `AbstractTable`. Anything else (a scalar, a list mixing
        numbers and strings, an empty nested list) gives None, meaning
        the value is passed as drawn.
    """
    if isinstance(value, (AbstractVec, AbstractMat, AbstractTable)):
        return value
    if isinstance(value, dict):
        cols = {}
        for name, col in value.items():
            vec = abstract_of(col)
            if not isinstance(vec, AbstractVec):
                return None
            cols[str(name)] = vec
        return AbstractTable(cols) if cols else None
    if not isinstance(value, (list, tuple)):
        return None
    if value and all(isinstance(r, (list, tuple)) for r in value):
        widths = {len(r) for r in value}
        if len(widths) != 1 or not all(
                _is_number(v) or _is_missing_element(v) for r in value for v in r):
            return None
        holes = {(i, j): _hole_word(v) for i, r in enumerate(value)
                 for j, v in enumerate(r) if _is_missing_element(v)}
        return AbstractMat(tuple(tuple(math.nan if (i, j) in holes else _number(v)
                                       for j, v in enumerate(r))
                                 for i, r in enumerate(value)),
                           frozenset(holes), _one_spelling(holes.values()),
                           _members(holes))
    values, missing, words, kinds = [], set(), [], set()
    for k, v in enumerate(value):
        if _is_missing_element(v):
            values.append(math.nan)
            missing.add(k)
            words.append(_hole_word(v))
        elif _is_number(v):
            values.append(_number(v))
            kinds.add("number")
        elif isinstance(v, (str, bool)):
            values.append(v)
            kinds.add("bool" if isinstance(v, bool) else "str")
        else:
            return None
    if len(kinds) > 1:
        return None
    element = next(iter(kinds)) if kinds and kinds != {"number"} else None
    return AbstractVec(tuple(values), frozenset(missing), _one_spelling(words),
                       _members(dict(zip(sorted(missing), words))),
                       element=element)


class Labelled(list):
    """A vector whose positions are named: a list, read by position as
    any list is, that also reads the value at a name (`v["x"]`).
    `labels` holds one name per position."""

    def __init__(self, values=(), labels: tuple = ()):
        super().__init__(values)
        self.labels = tuple(labels)

    def __getitem__(self, key):
        if isinstance(key, str):
            return list.__getitem__(self, label_position(self.labels, key))
        return list.__getitem__(self, key)


def label_position(labels: tuple, name: str) -> int:
    """Intent:
        The position `name` labels among `labels`.

    Raises:
        KeyError: no position is labelled `name`; the message lists
            the labels there are.
    """
    try:
        return labels.index(name)
    except ValueError:
        raise KeyError(f"no position is labelled {name!r} (labels: "
                       f"{', '.join(map(str, labels)) or 'none'})") from None


def plain(value):
    """Intent:
        The plain Python value an abstract value compares as: an
        `AbstractVec` is a list with NaN at each missing position (a
        `Labelled` list when its positions are named), an
        `AbstractMat` a list of row lists, an `AbstractTable` a dict of
        column lists. Any other value is returned unchanged.
    """
    if isinstance(value, AbstractVec):
        values = [math.nan if k in value.missing else v
                  for k, v in enumerate(value.values)]
        return Labelled(values, value.labels) if value.labels else values
    if isinstance(value, AbstractMat):
        return [list(r) for r in value.rows]
    if isinstance(value, AbstractTable):
        return {name: plain(col) for name, col in value.columns.items()}
    return value
