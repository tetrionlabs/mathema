# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On the probe route a declared tolerance is the whole allowance an
equality gets: two sides count as equal when they differ by at most
that much, with no relative allowance on top. With no tolerance
declared, the default is a relative 1e-7 or an absolute 1e-9, whichever
is larger, and a draw that passes only through the relative part is
decided in exact arithmetic (ruling of 2026-10-01; options O1 and O3 of
the tolerance review)."""
from mathema.conjecture import check_conjectures, claim


def scaled(x: float) -> float:
    return x * 1.0000005


def scaled_pair(x: float) -> list:
    return [x * 1.0000005, x]


def nearly_scaled(x: float) -> float:
    return x * (1 + 1e-8)


#: a float read from the module, a double with no exact reading
_NUDGE = 1 + 1e-8


def nearly_scaled_by_global(x: float) -> float:
    return x * _NUDGE


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


def test_the_undeclared_default_decides_a_relative_pass_exactly():
    # f's literal is read as written: exactly f(x) = x + x / 10**8, which
    # differs from x by x / 10**8 > 0 at every x in [1, 10], so the first
    # draw that passed only through the relative part is false there in
    # exact arithmetic
    (p,) = check_conjectures(
        nearly_scaled, [claim("for x in [1, 10], f(x) == x", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "false here in exact arithmetic" in p.counterexample, \
        p.counterexample
    (x,) = p.meta["mathema.counterexample_args"]
    assert 1 <= x <= 10 and abs(nearly_scaled(x) - x) > 1e-9


def test_a_relative_pass_with_no_exact_reading_is_inconclusive():
    # the factor is a module float, a double with no exact reading, so
    # every draw that passed only through the relative part is
    # inconclusive and not counted
    (p,) = check_conjectures(
        nearly_scaled_by_global,
        [claim("for x in [1, 10], f(x) == x", route="probe")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "could not be evaluated in exact arithmetic" in p.note
