# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The stable, public registry of mathema-internal functions a claim's
`funcs={}` binding can reference by dotted path (`mathema.f.reverse_seq`,
for instance). A claim built with a live callable in `funcs` only works
for an in-process, one-off adjudication; a claim meant to survive
`declare()`/`entry_claims()`'s round trip through the declared-schema
dict shape (spec.py) needs a name that's still resolvable later, in a
different process, the same way a spec key resolves back to a live
function. Names here are the stable half of that contract, kept
here, not as private, module-local closures, precisely so a persisted
reference to one never breaks under an unrelated internal refactor.

Every function here is a plain, named, side-effect-free transform or
predicate over ordinary Python values, no closures over a claim's own
`fn`, since a closure can't survive being written to and read back from
YAML.
"""
from __future__ import annotations


def reverse_seq(xs):
    """The sequence in reverse order."""
    return list(reversed(xs))


def scale_seq(xs, c):
    """Every element of the sequence multiplied by `c`."""
    return [v * c for v in xs]


def shift_seq(xs, c):
    """Every element of the sequence with `c` added."""
    return [v + c for v in xs]


def concat_seq(xs, ys):
    """The two sequences joined, first then second."""
    return list(xs) + list(ys)


def sort_seq(xs):
    """The sequence in ascending order."""
    return sorted(xs)


def _is_nonfinite(out) -> bool:
    """True when a value is a silent non-finite number (nan/inf), a
    Python or numpy scalar (a complex one with a non-finite component)
    or a numpy array; False for a genuinely
    non-numeric value, which is not this predicate's concern."""
    import math
    if isinstance(out, bool):
        return False
    if isinstance(out, (int, float)):
        return math.isnan(out) or math.isinf(out)
    if isinstance(out, complex):
        # a NaN or an infinity in either component
        import cmath
        return not cmath.isfinite(out)
    try:
        import numpy as np
    except ImportError:
        return False
    try:
        arr = np.asarray(out)
        if arr.dtype.kind != "c":
            arr = arr.astype(float)
    except (TypeError, ValueError):
        return False
    return not bool(np.isfinite(arr).all())


def finite_no_error(fn, *args):
    """1 if calling `fn(*args)` raises none of `ZeroDivisionError`,
    `OverflowError` or `FloatingPointError` and returns a finite result
    (no `NaN`/infinite value, a numpy scalar or array included,
    checking every element when the result is a list or tuple), 0
    otherwise. Any other exception propagates to the caller, where the
    probe route reads it as a raise at that point."""
    try:
        r = fn(*args)
    except (ZeroDivisionError, OverflowError, FloatingPointError):
        return 0
    vals = r if isinstance(r, (list, tuple)) else [r]
    if any(_is_nonfinite(v) for v in vals):
        return 0
    return 1
