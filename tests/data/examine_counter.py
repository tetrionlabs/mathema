# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A module-level counter, the global twin of the nonlocal counter."""
N = 0


def w_global_counter(x: float) -> float:
    global N
    N += 1
    return x + N
