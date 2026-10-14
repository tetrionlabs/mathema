# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function over a mapping parameter, in a module that imports pandas
without using it."""
import pandas as pd  # noqa: F401


def total_qty(order: dict) -> int:
    return sum(order.values())
