# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derive disproof of a value claim is confirmed by evaluating the
claim exactly at derive's witness, a coordinate the witness leaves free
drawn from its domain: the function run on the point's exact values
when it gives exact results there, else the values it returned read as
the exact numbers they are. Confirmed, the mathematics is falsified
with that witness, however far below the float allowance the gap lies,
and the float computation holding within its allowance is recorded
beside it. Unconfirmed, the disproof stays unknown with the
engine-bug flag. A claim's name never changes its verdict: a claim
named after a built-in family is decided as its unnamed twin is."""
import pytest

from mathema.conjecture import check_conjectures, claim


def ema_offset(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y + 5e-10


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def drift(x: float) -> float:
    return x + 2e-9


def constant(x: float) -> float:
    return 5e-10


def below_float_resolution(x: float) -> float:
    return x + x / 100000000000000000


def fold_below_float_resolution(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y + y / 100000000000000000


#: a float read from outside the body: no exact reading
TINY = 1e-17


def nudged(x: float) -> float:
    return x + TINY


def nudged_by_a_literal(x: float) -> float:
    return x + 1e-17


def _check(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


@pytest.mark.parametrize("name", [None, "linear_fold"])
def test_an_offset_fold_is_falsified_whatever_the_claim_is_named(name):
    kw = {"name": name} if name else {}
    p = _check(ema_offset, "f(x, 1.0) == x[-1]", **kw)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.route == "derive", p.route
    assert p.counterexample, p.counterexample
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta
    assert p.meta["mathema.exact_witness"]["computation"] == \
        "holds within its allowance", p.meta


def test_a_family_name_gives_the_unnamed_verdict_and_witness():
    plain = _check(ema_offset, "f(x, 1.0) == x[-1]")
    named = _check(ema_offset, "f(x, 1.0) == x[-1]", name="linear_fold")
    assert (named.verdict, named.route, named.counterexample) == \
        (plain.verdict, plain.route, plain.counterexample)


@pytest.mark.parametrize("name", [None, "linear_fold"])
def test_a_correct_fold_is_still_proven(name):
    kw = {"name": name} if name else {}
    p = _check(ema, "f(x, 1.0) == x[-1]", **kw)
    assert p.verdict == "proven", (p.verdict, p.route, p.note)


def test_a_constant_difference_with_no_witness_is_falsified_at_a_drawn_point():
    p = _check(drift, "for x in {1, 2}, f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.route == "derive", p.route
    assert p.counterexample.split(":")[0] in ("x = 1", "x = 2"), \
        p.counterexample


def test_a_ground_claim_derive_disproves_is_falsified():
    p = _check(constant, "f(0) == 0")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.counterexample, p.counterexample


def test_a_difference_below_float_resolution_is_falsified_exactly():
    # f run on exact values is exact: the mathematics decides, though
    # the float result equals x
    p = _check(below_float_resolution, "for x in [1, 2], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta
    assert p.counterexample, p.counterexample


def test_a_fold_below_float_resolution_is_falsified_on_the_mathematics():
    # derive's witness leaves x free: x is drawn, the floats agree there,
    # and the fold run on x's exact values does not
    p = _check(fold_below_float_resolution, "f(x, 1.0) == x[-1]")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness
    assert witness["computation"] == "holds within its allowance", witness
    assert "false here in exact arithmetic" in p.counterexample, \
        p.counterexample


def test_a_disproof_no_exact_evaluation_confirms_stays_uncorroborated():
    # a float read from outside the body leaves no exact value, and the
    # floats agree
    p = _check(nudged, "for x in [1, 2], f(x) == x")
    assert p.verdict != "falsified", (p.verdict, p.route, p.note)
    assert p.meta.get("mathema.corroboration") == "uncorroborated", p.meta


def test_a_literal_in_the_body_is_read_as_written_at_the_witness():
    # 1e-17 is 1/10^17 as written: the body read exactly makes the claim
    # false at the drawn point, while the floats agree
    p = _check(nudged_by_a_literal, "for x in [1, 2], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness
    assert witness["computation"] == "holds within its allowance", witness
