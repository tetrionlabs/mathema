# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Unannotated parameters in a module that imports numpy and pandas."""
import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401


def spread(xs):
    """The largest value less the smallest: both an array and a Series
    support it."""
    return xs.max() - xs.min()


def first_by_position(xs):
    """The first value by position: only a Series supports `.iloc`."""
    return xs.iloc[0]
