# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Unannotated parameters in a module that imports numpy only."""
import numpy as np  # noqa: F401


def gram_trace(A):
    """The trace of A times its transpose."""
    return float(np.trace(A @ A.T))


def spread(xs):
    """The largest value less the smallest."""
    return xs.max() - xs.min()


def first_by_position(xs):
    """The first value by position, a use an array does not support."""
    return xs.iloc[0]
