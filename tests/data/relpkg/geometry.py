# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A module with a relative import: the shape that breaks any loader
that executes files without package context."""
from .helpers import scale


def doubled(x: float) -> float:
    return scale(x, 2.0)


def half_sum(a: float, b: float) -> float:
    return scale(a + b, 0.5)


class Norms:
    @staticmethod
    def taxicab(a: float, b: float) -> float:
        return abs(a) + abs(b)

    def weighted(self, a: float, b: float) -> float:
        return scale(a, 0.5) + scale(b, 0.5)
