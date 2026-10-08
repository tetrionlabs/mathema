# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A draw where the claim's own side raises (an overflow in the claim's
own arithmetic, not in f) is never silently dropped: the side is read
exactly when it can be, and otherwise the claim is unknown, naming the
draw and the reason (ruling of 2026-10-01: a point that cannot be
decided is never counted toward holds)."""

import pytest

pytest.importorskip("numpy")

from mathema.conjecture import check_conjectures, claim  # noqa: E402


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


import numpy as np  # noqa: E402


def norm_by_numpy(x: np.ndarray) -> float:
    return float(np.linalg.norm(x))


def test_an_overflow_on_both_float_sides_is_not_agreement():
    # at x near 1e300 the code's norm overflows to inf and so does the
    # claim's float side, while the claim read exactly is finite: the
    # code gave no value there, and two infinities do not agree
    import mathema
    from mathema.conjecture import check_conjectures, claim
    nrm = norm_by_numpy
    law = "for x in [1e300, 2e300]^3, f(x) == sqrt(sum(x**2))"
    rows = {p.name: p for p in mathema.check(nrm, claims=[
        mathema.claim(law, name="c")]).probes}
    (float_row,) = [p for n, p in rows.items() if n.startswith("c[float")]
    assert float_row.verdict == "falsified", float_row.note
    (p,) = check_conjectures(nrm, [claim(law, route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def scaled_returns(returns: np.ndarray, c: float) -> np.ndarray:
    return returns * c


def test_a_claim_side_beyond_float_range_stays_exact():
    # at returns = [1e300, -1e300, ...] norm(returns)**2 is past the
    # float limit; read exactly it is the sum of squares, and the code's
    # own values agree with it there
    from mathema._exact_side import exact_sides
    from mathema.conjecture import _validate
    code_l, _ = _validate("dot(f(returns, c), returns)", {"returns", "c"}, set())
    code_r, _ = _validate("c * norm(returns)**2", {"returns", "c"}, set())
    from mathema._linalg_eval import FUNCTIONS
    env = {**FUNCTIONS, "returns": np.array([1e300, -1e300, 3.0]), "c": 2.0}
    sides = exact_sides(code_l, code_r, env, {"f": scaled_returns})
    assert sides is not None
    from fractions import Fraction
    # f's float products are exact here (scaling by 2), so both sides are
    # the exact 2 * (2e600 + 9), far past the float limit
    left, right = sides
    expected = 2 * (2 * Fraction(1e300) ** 2 + 9)
    assert left == expected
    assert abs(Fraction(right) - expected) <= expected / 10**50
