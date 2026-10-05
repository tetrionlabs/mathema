# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A draw where the claim's own side raises (an overflow in the claim's
own arithmetic, not in f) is never silently dropped: the side is read
exactly when it can be, and otherwise the claim is unknown, naming the
draw and the reason (ruling of 2026-10-01: a point that cannot be
decided is never counted toward holds)."""
from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


def test_an_unevaluable_claim_side_makes_the_claim_unknown():
    (p,) = check_conjectures(ident, [claim(
        "for x in [1, 1000], f(x) <= exp(x) + x", route="probe")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "the claim's own side raised OverflowError" in p.note


def test_a_claim_side_read_exactly_still_decides():
    (p,) = check_conjectures(ident, [claim(
        "for x in [1, 1000], f(x) == (x * 10**400) / 10**400",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_claim_side_read_exactly_still_falsifies():
    (p,) = check_conjectures(ident, [claim(
        "for x in [1, 1000], f(x) == (x * 10**400 + 1) / 10**400",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_float_line_is_unknown_where_its_claim_side_has_no_value():
    import mathema
    rows = {p.name: p for p in mathema.check(ident, claims=[
        mathema.claim("for x in [1, 1000], f(x) <= exp(x) + x",
                      name="below")]).probes}
    assert rows["below"].verdict == "proven"
    assert rows["below[float]"].verdict == "unknown", rows["below[float]"].note
    assert "OverflowError" in rows["below[float]"].note


def square(x: float) -> float:
    return x * x


def test_the_code_overflowing_falsifies_even_where_the_claim_side_raises():
    # x * x is inf at x = 1e160, a finite exact value: a carrier failure
    # of the code, which falsifies the computation line whatever the
    # claim's own float side does there
    import mathema
    rows = {p.name: p for p in mathema.check(square, claims=[mathema.claim(
        "for x in [1e150, 1e160], f(x) == x**2", name="c")]).probes}
    assert rows["c"].verdict == "proven"
    assert rows["c[float]"].verdict == "falsified", rows["c[float]"].note
    assert "inf" in rows["c[float]"].counterexample + (rows["c[float]"].sketch or "")
