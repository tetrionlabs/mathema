# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A nested submodule, for the package walk."""
from ..helpers import shift


def deepened(x: float) -> float:
    return shift(x, 1.0)
