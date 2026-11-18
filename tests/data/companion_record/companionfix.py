# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two functions whose derive claim spawns a `[float]` computation row.

The records beside this file were written by
`scripts/make_companion_record_fixture.py`: `scale` carries an accepted
risk on its `doubles[float]` row, and `scale_checked` carries accepted
evidence on its `doubles[float]` row.
"""


def scale(x: float) -> float:
    """Twice x.

    Claims:
        doubles [derive]: for x in [-10, 10], f(x) == 2 * x
    """
    return 2.0 * x


def scale_checked(x: float) -> float:
    """Twice x, accepted as evidence.

    Claims:
        doubles [derive]: for x in [-10, 10], f(x) == 2 * x
    """
    return x + x
