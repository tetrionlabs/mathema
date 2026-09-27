# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The spelling of a float in text that is read back as a float. Stdlib-only
leaf, shared by the claim-grammar printer and the operational infinity
binding."""
from __future__ import annotations


def exact_float_text(value: float, short: str) -> str:
    """Intent:
        `short` when it reads back as exactly `value`, else the shortest
        spelling that does (Python's `repr`).

    Notes:
        `short` is the caller's usual spelling (`f"{v:g}"`, a printer's
        default). It keeps an exact value's familiar text (`1e+100`,
        `30`, `0.5`), and a value that needs more digits than `short`
        carries (`1.7976931348623157e+308`) gets all of them. A
        non-finite value keeps `short`.
    """
    try:
        if float(short) == value:
            return short
    except ValueError:
        pass
    if value != value or value in (float("inf"), float("-inf")):
        return short
    return repr(float(value))
