# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`x ** 0.5` and `x ** (1/3)` of a negative float are complex in
Python, not a raise and not a real number.

The derive route reads a function as real-valued, so a proof over a
domain where a fractional power meets a negative base is not kept;
the claim is left to the routes that execute the code. The same claim
over a domain that keeps the base nonnegative still proves.
"""
from mathema.conjecture import check_conjectures, claim


def half_power(x: float) -> float:
    return x ** 0.5


def cube_root(x: float) -> float:
    return x ** (1 / 3)


def shifted_root(x: float) -> float:
    return (x - 2.0) ** 0.5 + 1.0


def guarded_root(x: float) -> float:
    if x < 0:
        return 0.0
    return x ** 0.5


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_no_proof_where_the_power_is_complex():
    for fn, law in ((half_power, "for x in [-1, 1], f(x) * f(x) == x"),
                    (cube_root, "for x in [-8, 8], f(x) ** 3 == x"),
                    (shifted_root, "for x in [0, 3], (f(x) - 1)**2 == x - 2")):
        p = _v(fn, law)
        assert p.verdict != "proven", (fn.__name__, law, p.sketch)


def test_a_nonnegative_base_still_proves():
    for fn, law in ((half_power, "for x in [0, 1], f(x) * f(x) == x"),
                    (cube_root, "for x in [1, 8], f(x) ** 3 == x"),
                    (shifted_root, "for x in [2, 3], (f(x) - 1)**2 == x - 2"),
                    (guarded_root, "for x in [-1, 1], f(x) >= 0")):
        p = _v(fn, law)
        assert p.verdict == "proven", (fn.__name__, law, p.sketch, p.note)
