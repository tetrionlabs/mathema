# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A helper module whose functions write their own module state."""
HITS = [0]


def bump(x):
    HITS[0] += 1
    return x


def same(v):
    return v
