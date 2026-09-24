# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim is adjudicated over its own domain. A function-level
parent domain comes from `Annotated` markers on the signature and the
`domain=` argument to `check`; a claim's own `for` binding overrides
the parent per parameter; no claim's quantifier reaches a sibling
claim. The record states the domain each claim was adjudicated over:
the claim's own bindings in `domain`/`condition`, and whatever the
parent supplied under `meta["mathema.parent_domain"]`."""
from typing import Annotated

import mathema
from mathema import claim
from mathema.types import Probability


def clipped(x: float) -> float:
    if x < -5.0:
        return -1.0
    return x + 0.0


def line(x: float) -> float:
    return 3.0 * x + 2.0


def _row(record, name):
    (row,) = [p for p in record.probes if p.name == name]
    return row


def test_a_quantified_claim_never_narrows_an_unquantified_sibling():
    rec = mathema.check(clipped, claims=[
        claim("for x in [0, 1e6], f(x) >= 0", name="nonneg_on_range"),
        claim("f(x) >= 0", name="nonneg_everywhere"),
    ])
    ranged = _row(rec, "nonneg_on_range")
    everywhere = _row(rec, "nonneg_everywhere")
    assert ranged.verdict in ("proven", "holds")
    # the unquantified claim says all x, and clipped(-1) = -1 < 0
    assert everywhere.verdict == "falsified", everywhere
    assert everywhere.counterexample
    # and its record carries no domain it never stated
    assert everywhere.domain is None
    assert "1000000" not in (everywhere.condition or "")
    assert "mathema.parent_domain" not in (everywhere.meta or {})


def test_the_verdict_alone_matches_the_verdict_beside_a_sibling():
    alone = _row(mathema.check(clipped, claims=[
        claim("f(x) >= 0", name="nonneg_everywhere")]), "nonneg_everywhere")
    beside = _row(mathema.check(clipped, claims=[
        claim("for x in [0, 1e6], f(x) >= 0", name="nonneg_on_range"),
        claim("f(x) >= 0", name="nonneg_everywhere")]), "nonneg_everywhere")
    assert alone.verdict == beside.verdict == "falsified"


def test_the_parent_domain_applies_and_is_stated_in_the_record():
    rec = mathema.check(clipped, claims=[claim("f(x) >= 0", name="c")],
                        domain={"x": (0.0, 10.0)})
    row = _row(rec, "c")
    assert row.verdict in ("proven", "holds")
    assert row.domain is None   # the claim itself states no binding
    stated = row.meta["mathema.parent_domain"]
    assert stated.startswith("for x in [0")
    assert "10" in stated


def test_a_claims_own_binding_overrides_the_parent_per_parameter():
    rec = mathema.check(clipped, claims=[
        claim("for x in [-10, -6], f(x) >= 0", name="c")],
        domain={"x": (0.0, 10.0)})
    row = _row(rec, "c")
    assert row.verdict == "falsified", row
    # x is the claim's own, so nothing of the parent applied
    assert "mathema.parent_domain" not in (row.meta or {})


def test_the_override_is_per_parameter_not_per_claim():
    def shifted(x: float, y: float) -> float:
        return x + y

    rec = mathema.check(shifted, claims=[
        claim("for x in [0, 1], f(x, y) >= 0", name="c")],
        domain={"x": (-5.0, -4.0), "y": (0.0, 1.0)})
    row = _row(rec, "c")
    # x from the claim, y from the parent: x + y >= 0 on [0,1] x [0,1]
    assert row.verdict in ("proven", "holds"), row
    stated = row.meta["mathema.parent_domain"]
    assert "y in" in stated and "x in" not in stated


def test_a_signature_marker_is_a_parent_domain():
    def scaled(p: Annotated[float, Probability]) -> float:
        return 2.0 * p

    row = _row(mathema.check(scaled, claims=[claim("f(p) <= 2", name="c")]),
               "c")
    assert row.verdict in ("proven", "holds")
    assert "p in" in row.meta["mathema.parent_domain"]


def test_excluding_reads_the_parent_domain_only():
    # no parent: a claim's quantifier is not a function-level domain,
    # so there is no outside to exclude
    rec = mathema.check(line, claims=["for x in [0, 1], f(x) >= 0",
                                      "excluding"])
    assert not [p for p in rec.probes
                if p.name.startswith("excluded_outside_domain")]
    # with a parent, the exclusion is generated and adjudicated there
    rec = mathema.check(line, claims=["excluding"],
                        domain={"x": (0.0, 1.0)})
    row = _row(rec, "excluded_outside_domain[x]")
    assert row.verdict == "falsified"
    assert "for x in [0" in row.meta["mathema.parent_domain"]
