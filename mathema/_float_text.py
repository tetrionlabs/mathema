# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The spelling of a float in text that is read back as a float, and the
number literals in a claim's text that a double does not read exactly.
A leaf (stdlib and `_scan` only), shared by the claim-grammar printer,
the operational infinity binding and the derive stage."""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

from ._scan import blank_strings


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


_NUMBER_LITERAL = re.compile(
    r"(?<![\w.])(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?(?![\w.])")


def overlong_literals(text: str) -> list[str]:
    """Intent:
        The number literals in a claim's text that a double does not
        read exactly as written: the literal's decimal value differs
        from the decimal the nearest double prints as
        (`0.30000000000000000001` reads as 0.3), or that is beyond the
        double range (`1e400` reads as infinity, `1e-400` as zero).
        Strings are skipped.
    """
    found = []
    for m in _NUMBER_LITERAL.finditer(blank_strings(text or "")):
        literal = m.group(0)
        try:
            value = float(literal)
            if not math.isfinite(value) or Decimal(repr(value)) != Decimal(literal):
                found.append(literal)
        except (ValueError, OverflowError, InvalidOperation):
            continue
    return found


def exact_literal_text(text: str) -> str:
    """Intent:
        `text` with every literal a double does not read exactly
        (`overlong_literals`) spelled as the exact fraction it names,
        `(N/D)` in integers, which the symbolic reading takes as an
        exact rational. Strings are left alone.
    """
    targets = set(overlong_literals(text))
    if not targets:
        return text
    blanked = blank_strings(text)
    out, last = [], 0
    for m in _NUMBER_LITERAL.finditer(blanked):
        if m.group(0) not in targets:
            continue
        num, den = Decimal(m.group(0)).as_integer_ratio()
        out.append(text[last:m.start()])
        out.append(f"({num}/{den})")
        last = m.end()
    out.append(text[last:])
    return "".join(out)
