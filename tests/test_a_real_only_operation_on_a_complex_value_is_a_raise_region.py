# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Python's math functions, int, float, round, min and max, the
orderings and the % and // operators raise TypeError on a complex
value, whatever the value. A body that applies one to a complex
parameter raises at every call, so `is_defined` is never proven by
examination there, the same refusal the derive lifter makes."""
import cmath
import math

from mathema.analysis import effective_facts
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._partiality import partiality_walk


def finite_check(z: complex) -> bool:
    return math.isfinite(z)


def as_float(z: complex) -> float:
    return float(z)


def remainder(z: complex) -> complex:
    return z % 2


def plane_root(z: complex) -> complex:
    return cmath.sqrt(z)


def magnitude(z: complex) -> float:
    return abs(z)


def _defined(fn, route="best"):
    (p,) = check_conjectures(fn, [claim("is_defined(f)", route=route)])
    return p


def test_a_real_only_operation_on_a_complex_value_raises_everywhere():
    for fn in (finite_check, as_float, remainder):
        guards, _unread = partiality_walk(fn, effective_facts(fn))
        assert any(exc == "TypeError" for _cond, exc in guards), fn.__name__
        p = _defined(fn)
        assert p.verdict == "falsified", (fn.__name__, p.verdict, p.sketch)
        assert "TypeError" in (p.counterexample or ""), p.counterexample


def test_an_operation_on_the_plane_stays_defined():
    for fn in (plane_root, magnitude):
        guards, _unread = partiality_walk(fn, effective_facts(fn))
        assert not any(exc == "TypeError" for _c, exc in guards), fn.__name__
