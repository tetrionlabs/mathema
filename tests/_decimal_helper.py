# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A helper module whose Decimal work happens in a 4-digit context, for
callers that reach Decimal only through it."""
import decimal
from decimal import Decimal

_CTX4 = decimal.Context(prec=4)


def root_squared(x):
    # sqrt rounded to 4 digits, squared: 1.999396 at x = 2
    return Decimal(x).sqrt(context=_CTX4) ** 2


class Calc:
    def root_squared(self, x):
        return Decimal(x).sqrt(context=_CTX4) ** 2
