# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library adding one in Decimal, with no context of its own, for
callers that reach Decimal only through it."""
from decimal import Decimal


def plus_one(x):
    return Decimal(str(x)) + 1
