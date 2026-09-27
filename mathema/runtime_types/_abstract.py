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


@dataclass(frozen=True)
class AbstractVec:
    """A vector of `len(values)` numbers, with `missing` the positions
    that hold no value. The number stored at a missing position is NaN
    and carries no meaning."""
    values: tuple
    missing: frozenset = frozenset()

    def __len__(self) -> int:
        return len(self.values)

    def observed(self) -> tuple:
        """The values at the positions that are not missing, in order."""
        return tuple(v for k, v in enumerate(self.values)
                     if k not in self.missing)


@dataclass(frozen=True)
class AbstractMat:
    """A matrix as a tuple of equal-length rows of numbers."""
    rows: tuple

    @property
    def shape(self) -> tuple:
        return (len(self.rows), len(self.rows[0]) if self.rows else 0)


@dataclass(frozen=True)
class AbstractTable:
    """Named columns of equal length, each an `AbstractVec`, in order."""
    columns: dict = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(tuple(self.columns.items()))


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
        tuple of numbers (missing elements allowed) is an
        `AbstractVec`, a list of equal-length lists of numbers an
        `AbstractMat`, a dict of such lists an `AbstractTable`.
        Anything else (a scalar, a list of strings, an empty nested
        list) gives None, meaning the value is passed as drawn.
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
                _is_number(v) for r in value for v in r):
            return None
        return AbstractMat(tuple(tuple(_number(v) for v in r)
                                 for r in value))
    values, missing = [], set()
    for k, v in enumerate(value):
        if _is_missing_element(v):
            values.append(math.nan)
            missing.add(k)
        elif _is_number(v):
            values.append(_number(v))
        else:
            return None
    return AbstractVec(tuple(values), frozenset(missing))


def plain(value):
    """Intent:
        The plain Python value an abstract value compares as: an
        `AbstractVec` is a list with NaN at each missing position, an
        `AbstractMat` a list of row lists, an `AbstractTable` a dict of
        column lists. Any other value is returned unchanged.
    """
    if isinstance(value, AbstractVec):
        return [math.nan if k in value.missing else v
                for k, v in enumerate(value.values)]
    if isinstance(value, AbstractMat):
        return [list(r) for r in value.rows]
    if isinstance(value, AbstractTable):
        return {name: plain(col) for name, col in value.columns.items()}
    return value
