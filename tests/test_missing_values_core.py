# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Missing values on scalars: every row of the core battery, each
asserting the verdict a claim over a missing value comes to and, where
one is named, the member its witness holds.

`None` is the absence of the object; `missing` is a hole in a slot,
resolved per slot type (a `float` slot's hole is `nan`). A row carries
a strict `xfail` naming the stage of the build that makes it pass, so a
row that starts passing early fails the suite and is noticed."""
import math
from typing import Optional

import pytest

import mathema


def sqrt_plain(x: float) -> float:
    return math.sqrt(x)


def sqrt_guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing")
    return math.sqrt(x)


def double_or_missing(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return 2 * x


def zero_if_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        return 0.0
    return float(x)


def ident(x):
    return x


def add(x: float, y: float) -> float:
    return x + y


def stage(n: int):
    """The strict marker of a row a later stage of the build owns."""
    return pytest.mark.xfail(strict=True, reason=f"missing values stage {n}")


def run(fn, text: str):
    """The claim's own row and its companions, as `(probe, companions)`."""
    report = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    rows = [p for p in report.probes if p.name == "c" or p.name.startswith("c[")]
    main = next(p for p in rows if p.name == "c")
    return main, [p for p in rows if p.name != "c"]


def witness(probe) -> str:
    return probe.counterexample or ""


def assert_row(fn, text, verdicts, *, member=None, raised=None,
               companion=None, companion_member=None):
    """Intent:
        Adjudicate `text` over `fn` and check the row: the verdict is
        one of `verdicts`, the witness names `member` and the exception
        `raised` when given, and a companion comes to `companion` with
        its witness naming `companion_member` when given.
    """
    probe, companions = run(fn, text)
    assert probe.verdict in verdicts, (probe.verdict, probe.note, witness(probe))
    if member is not None:
        assert f"={member}" in witness(probe) or f"({member}" in witness(probe), \
            witness(probe)
    if raised is not None:
        said = f"{witness(probe)} {probe.note or ''} {probe.sketch or ''}"
        assert raised in said, said
    if companion is not None:
        assert any(c.verdict == companion for c in companions), \
            [(c.name, c.verdict, witness(c)) for c in companions]
        if companion_member is not None:
            assert any(c.verdict == companion and companion_member in witness(c)
                       for c in companions), \
                [(c.name, c.verdict, witness(c)) for c in companions]
    return probe, companions


PROVEN = ("proven",)
PROVEN_OR_HOLDS = ("proven", "holds")
FALSIFIED = ("falsified",)


@stage(3)
def test_s1_a_float_proof_carries_a_companion_falsified_at_nan():
    assert_row(sqrt_plain, "for x in [0, 1], f(x) >= 0", PROVEN,
               companion="falsified", companion_member="nan")


@stage(2)
def test_s3_a_listed_none_is_executed_and_raises():
    assert_row(sqrt_plain, "for x in {0.25, None}, f(x) >= 0", FALSIFIED,
               member="None", raised="TypeError")


@stage(2)
def test_s4_a_listed_nan_is_a_hole_against_an_ordering():
    assert_row(sqrt_plain, "for x in {0.25, nan}, f(x) >= 0", FALSIFIED,
               member="nan")


@stage(3)
def test_s5_a_guarded_float_companion_raises_at_nan():
    assert_row(sqrt_guarded, "for x in [0, 1], f(x) >= 0", PROVEN,
               companion="falsified", companion_member="nan")


def test_s6_a_listed_none_raising_valueerror_is_the_witness():
    assert_row(sqrt_guarded, "for x in {0.25, None}, f(x) >= 0", FALSIFIED,
               member="None", raised="ValueError")


@stage(2)
def test_s7_an_optional_float_companion_fails_at_a_missing_point():
    probe, companions = assert_row(double_or_missing, "for x in [0, 1], f(x) >= 0",
                                   PROVEN, companion="falsified")
    assert any("None" in witness(c) or "nan" in witness(c) for c in companions)


@stage(2)
def test_s8_absence_against_a_number_is_not_true():
    assert_row(double_or_missing, "for x in {0.25, None}, f(x) >= 0", FALSIFIED,
               member="None")


@stage(3)
def test_s9_a_replaced_hole_holds_on_both_halves():
    probe, companions = assert_row(zero_if_missing, "for x in [0, 1], f(x) >= 0",
                                   PROVEN)
    assert companions and all(c.verdict in PROVEN_OR_HOLDS for c in companions)


def test_s10_a_replaced_absence_is_proven():
    assert_row(zero_if_missing, "for x in {0.25, None}, f(x) >= 0", PROVEN)


def test_s11_propagation_agrees_with_itself():
    probe, companions = assert_row(ident, "for x in [0, 1], f(x) == x", PROVEN)
    assert all(c.verdict in PROVEN_OR_HOLDS for c in companions)


def test_s12_absence_agrees_with_itself():
    assert_row(ident, "for x in {0.25, None}, f(x) == x", PROVEN)


def test_s13_a_hole_agrees_with_itself():
    assert_row(ident, "for x in {0.25, nan}, f(x) == x", PROVEN)


@stage(2)
def test_s16_absence_at_the_second_parameter_raises():
    assert_row(add, "for x in [0, 1], y in {0.5, None}, f(x, y) >= 0", FALSIFIED,
               member="None", raised="TypeError")


def test_p1_a_policy_that_does_not_raise_at_nan_is_falsified():
    assert_row(sqrt_plain, "for x in {missing}, raises(f(x))", FALSIFIED,
               member="nan")


def test_p2_every_member_raises_the_stated_exception():
    assert_row(sqrt_guarded, "for x in {missing}, raises(f(x), ValueError)", PROVEN)


def test_p3_a_replacement_policy_is_proven():
    assert_row(zero_if_missing, "for x in {missing}, f(x) == 0", PROVEN)


@stage(2)
def test_p4_membership_by_class_is_proven():
    assert_row(double_or_missing, "for x in {missing}, f(x) in {missing}", PROVEN)


@stage(5)
def test_m1_nan_propagating_through_a_float_is_missing_safe():
    assert_row(sqrt_plain, "is_missing_safe(f)", PROVEN)


@stage(5)
def test_m3_a_guard_is_read_as_missing_raises():
    assert_row(sqrt_guarded, "is_missing_safe(f)", PROVEN)


def test_m4_an_optional_float_is_missing_safe():
    assert_row(double_or_missing, "is_missing_safe(f)", PROVEN)


def test_m5_a_replacing_function_is_missing_safe():
    assert_row(zero_if_missing, "is_missing_safe(f)", PROVEN)


def test_m6_an_unannotated_identity_is_missing_safe():
    assert_row(ident, "is_missing_safe(f)", PROVEN)


@stage(5)
def test_l1_the_ladder_hands_missing_points_to_the_policy():
    probe, companions = assert_row(
        sqrt_guarded, "assuming is_missing_safe(f), for x in [0, 1], f(x) >= 0",
        PROVEN)
    assert all(c.verdict in PROVEN_OR_HOLDS for c in companions)
