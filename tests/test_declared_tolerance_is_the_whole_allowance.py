# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On the probe route a declared tolerance is the whole allowance an
equality gets: two sides count as equal when they differ by at most
that much, with no relative allowance on top. With no tolerance
declared, the default keeps its relative 1e-6 or absolute 1e-9,
whichever is larger."""
from mathema.conjecture import check_conjectures, claim


def scaled(x: float) -> float:
    return x * 1.0000005


def scaled_pair(x: float) -> list:
    return [x * 1.0000005, x]


def nearly_scaled(x: float) -> float:
    return x * (1 + 1e-8)


def test_a_declared_tolerance_rejects_a_gap_inside_the_default_relative_allowance():
    (p,) = check_conjectures(
        scaled, [claim("for x in [1, 10], f(x) == x", route="probe",
                       tolerance=1e-12)])
    assert p.verdict == "falsified"
    (x,) = p.meta["mathema.counterexample_args"]
    assert abs(scaled(x) - x) > 1e-12


def test_a_declared_tolerance_governs_a_matrix_valued_side_too():
    (p,) = check_conjectures(
        scaled_pair, [claim("for x in [1, 10], f(x) == [x, x]",
                            route="probe", tolerance=1e-12)])
    assert p.verdict == "falsified"


def test_a_declared_tolerance_still_admits_a_gap_within_it():
    (p,) = check_conjectures(
        scaled, [claim("for x in [1, 10], f(x) == x", route="probe",
                       tolerance=1e-4)])
    assert p.verdict == "holds"


def test_the_undeclared_default_keeps_its_relative_allowance():
    (p,) = check_conjectures(
        nearly_scaled, [claim("for x in [1, 10], f(x) == x", route="probe")])
    assert p.verdict == "holds"
