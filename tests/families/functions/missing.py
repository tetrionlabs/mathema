# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions that treat a missing value (None, nan) differently from a
number, and functions over empty inputs."""
import math
from typing import Optional, Sequence, Union


def none_in_band(x, y):
    if x is None and 0.25 < y < 0.75:
        return 1.0
    return 0.0


def nan_in_band(x, y):
    if x != x and 0.25 < y < 0.75:
        return 1.0
    return 0.0


def always_zero(x, y):
    return 0.0


def doubled(x):
    return x * 2.0


def none_in_narrow_band(x, y):
    if x is None and 0.6 < y < 0.7:
        raise ValueError("n")
    return 1.0


def floored(x):
    return float(math.floor(x))


def guarded_double(x):
    if x is None or x != x:
        return 0.0
    return x * 2.0


def mean_union(xs: Union[list, tuple]):
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_optional(xs: Optional[Sequence[float]]):
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_list_or_text(xs: Union[list, str]):
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def mean_list_or_range(xs: Union[list, range]):
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def mean_union_not(xs: Union[list, tuple]):
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def mean_list(xs: list):
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_unannotated(xs):
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)
