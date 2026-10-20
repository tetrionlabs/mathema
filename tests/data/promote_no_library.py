# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unannotated parameter used as a vector in a module that imports
no library with a runtime type adapter."""
import math  # noqa: F401


def spread(xs):
    """The largest value less the smallest."""
    return xs.max() - xs.min()
