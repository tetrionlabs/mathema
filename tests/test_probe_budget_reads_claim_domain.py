# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route's trial budget reads the domain a claim binds, the
same way it reads `check(domain=...)`: an affine function over a claim
domain of R gets the wide-domain budget, not the reduced affine one,
and a claim's narrow binding replaces a wide check domain for the
parameter it binds."""
import mathema

INF = float("inf")


def affine(x: float) -> float:
    return 2.0 * x + 1.0


def _row(claim: str, domain=None):
    record = mathema.check(affine, claims=[mathema.claim(claim, route="probe")],
                           domain=domain)
    (row,) = [p for p in record.probes if p.name.startswith("f_x")]
    return row


def test_a_claim_bound_to_R_counts_as_a_wide_domain():
    row = _row("for x in R, f(x) == 2*x + 1")
    factors = row.meta["mathema.confidence"]["factors"]
    assert factors["wide_domain"] == 1
    assert factors["float_extremes"] == 1
    assert row.n > 64


def test_a_narrow_claim_binding_replaces_a_wide_check_domain():
    row = _row("for x in [0, 1], f(x) == 2*x + 1", domain={"x": (-INF, INF)})
    factors = row.meta["mathema.confidence"]["factors"]
    assert factors["wide_domain"] == 0
    assert factors["float_extremes"] == 0
    assert row.verdict == "holds"
    assert row.n < 64


def test_a_narrow_claim_binding_keeps_the_affine_budget():
    row = _row("for x in [0, 1], f(x) == 2*x + 1")
    assert row.verdict == "holds"
    assert row.n < 64


def test_a_complex_rectangle_is_not_read_as_a_real_span():
    from mathema.probing import _numeric_span
    assert _numeric_span((-1 - 1j, 1 + 1j)) is None
    assert _numeric_span((-1.0, 2.0)) == (-1.0, 2.0)
    assert _numeric_span((0, float("inf"))) == (0, float("inf"))


def test_a_complex_domain_is_not_read_as_a_real_span():
    from mathema.conjecture import claim
    from mathema.probing import _numeric_span
    bound = claim("for z in [-1-1j, 1+1j], f(z) == z").domain["z"]
    assert _numeric_span(bound) is None
    real = claim("for x in [-2, 3], f(x) == x").domain["x"]
    assert _numeric_span(real) == (-2, 3)
