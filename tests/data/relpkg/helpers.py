# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Numeric helpers the sibling module imports relatively."""


def scale(x: float, k: float) -> float:
    return x * k


def shift(x: float, c: float) -> float:
    return x + c
