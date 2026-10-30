# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function of a real argument that returns a complex number has a
value there: `is_defined` asks for a value, and `complex(x, 1.0)`, `2j`
and, under a complex return annotation, `x ** 0.5` at a negative x are
values. A real-valued function whose computation turns complex (`x **
0.5` under `-> float`) has none. An ordering of a complex result is no
well formed claim on any route."""
from mathema.conjecture import check_conjectures, claim


def constant_imaginary(x: float) -> complex:
    return 2j


def lifted_pair(x: float) -> complex:
    return complex(x, 1.0)


def branch_pair(x: float) -> complex:
    if x > 0:
        return complex(0.0, 2.0)
    return complex(x, 0)


def complex_root(x: float) -> complex:
    return x ** 0.5


def real_root(x: float) -> float:
    return x ** 0.5


def rotate(x: float) -> complex:
    return x * 1j


def _row(fn, text, route="best"):
    return check_conjectures(fn, [claim(text, route=route)])[0]


def test_a_complex_result_is_a_value_on_every_spelling():
    for fn in (constant_imaginary, lifted_pair, branch_pair, complex_root):
        for route in ("best", "probe"):
            p = _row(fn, "for x in [-10, 10], is_defined(f)", route)
            assert p.verdict in ("proven", "holds"), (fn.__name__, route,
                                                      p.verdict, p.note)


def test_a_real_valued_root_of_a_negative_has_no_value():
    p = _row(real_root, "for x in [-10, 10], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_an_ordering_of_a_complex_result_is_misspecified_on_every_route():
    for route in ("best", "probe"):
        p = _row(rotate, "for x in [1, 5], f(x) <= 5", route)
        assert p.verdict == "skipped:misspecified", (route, p.verdict, p.note)
