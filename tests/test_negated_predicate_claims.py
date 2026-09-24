# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A negated predicate claim keeps its negation all the way to the
Record: it is its own row, never merged with the built-in positive row
of the same predicate, and its verdict is the negation's verdict."""
import mathema
from mathema.conjecture import claim


def total(x: float) -> float:
    return 2.0 * x + 1.0


def test_a_negated_predicate_gets_its_own_name():
    assert claim("is_defined(f)").name != claim("not is_defined(f)").name


def test_check_reports_the_negation_not_the_positive_claim():
    rec = mathema.check(total, claims=["not is_defined(f)"])
    negated = [p for p in rec.probes if p.name == claim("not is_defined(f)").name]
    assert len(negated) == 1
    assert negated[0].verdict != "proven"


def test_a_declared_negation_round_trips():
    from mathema.spec import declare, entry_claims
    (back,) = entry_claims({"claims": [declare(claim("not is_defined(f)"))]})
    assert back.negated and back.relation == "is_defined"
