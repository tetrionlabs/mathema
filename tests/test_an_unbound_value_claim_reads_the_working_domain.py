# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim that binds no domain for a parameter is judged over
the function's working domain: what its annotations admit, minus what
its own guards refuse. A guard raising where x < 0 leaves x >= 0, and
the claim is proven there; the record says what the working domain is,
and the statement stays as written. A domain the claim states is never
narrowed: a raise inside it falsifies. A definedness falsification
found by executing f at a point its computed region suggests reports
that mechanism as its route."""
import math

from mathema.conjecture import check_conjectures, claim


def guarded_neg(x: float) -> float:
    if x < 0:
        raise ValueError("x is negative")
    return math.sqrt(x)


def _one(law):
    (p,) = check_conjectures(guarded_neg, [claim(law)])
    return p


def test_an_unbound_claim_is_proven_over_what_the_guard_leaves():
    for law in ("f(x) >= 0", "f(x) * f(x) == x"):
        p = _one(law)
        assert p.verdict == "proven", (law, p.verdict, p.sketch, p.note)
        assert "for x" not in p.statement, p.statement
        assert "the working domain is x in [0, oo)" in (p.note or ""), p.note
        assert (p.meta or {}).get("mathema.working_domain", {}).get("x") \
            == "[0, oo)", p.meta


def test_a_stated_domain_is_never_narrowed():
    p = _one("for x in [-2, -1], f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)


def arcsine(x: float) -> float:
    return math.asin(x)


def test_an_executed_definedness_witness_is_reported_by_its_mechanism():
    # the region is computed, the witness executed: the route says so
    # whatever the claim is named
    for name in (None, "c"):
        (p,) = check_conjectures(arcsine, [claim(
            "for x in [-2, 2], is_defined(f)", name=name)])
        assert p.verdict == "falsified", (name, p.verdict)
        assert p.route == "probe:semi_analytical", (name, p.route)
