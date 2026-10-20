# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions over a mapping parameter, in a module that imports numpy
without using it, so the mapping's methods share names with array
attributes the module's library carries."""
from typing import Mapping

import numpy as np  # noqa: F401


def total_qty(order: dict) -> int:
    return sum(order.values())


def total_qty_generic(order: dict[str, int]) -> int:
    return sum(order.values())


def total_qty_mapping(order: Mapping[str, int]) -> int:
    return sum(order.values())


def item_count(order: dict) -> int:
    return len(order.copy())


def first_position(xs: list[float]) -> int:
    return xs.index(xs[0])


def unannotated_values(x):
    return x.values


def unannotated_shape(x):
    return x.shape


class Box:
    """A box whose `shape` is its side lengths."""

    def __init__(self, shape):
        self.shape = shape


def box_volume(b: Box) -> int:
    w, h = b.shape
    return w * h
