# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The mathematics reads a number exactly as written. A literal with
more digits than a double carries (`0.30000000000000000001`) is read by
the parser as the nearest double, 0.3, which is a different number; a
proof or a disproof built on that rounding is about another claim, so
the derive route decides neither. The computation still reads the
double, as it always does."""
from mathema.conjecture import check_conjectures, claim


def ident(x: float) -> float:
    return x


def _derive(law):
    (p,) = check_conjectures(ident, [claim(law, route="derive")])
    return p


def test_a_domain_end_past_the_bound_is_not_proven():
    # x reaches 0.30000000000000000001 > 0.3, so the claim is false
    p = _derive("for x in [0, 0.30000000000000000001], f(x) <= 0.3")
    assert p.verdict != "proven"
    assert "derive: undecided (0.30000000000000000001 has more digits" in p.note


def test_a_bound_just_past_the_domain_end_is_proven_from_the_exact_literal():
    # 0.3 < 0.30000000000000000001, so the mathematics is true
    p = _derive("for x in [0, 0.3], f(x) < 0.30000000000000000001")
    assert p.verdict == "proven"


def test_a_literal_a_double_reads_exactly_is_unaffected():
    assert _derive("for x in [0, 0.3], f(x) <= 0.3").verdict == "proven"
    assert _derive("for x in [0, 0.30], f(x) <= 0.300").verdict == "proven"


def test_a_long_literal_in_the_law_is_read_exactly_by_the_proof():
    # 0.99999999999999999999 < 1 = f(1), so the claim is false at x = 1
    p = _derive("for x in [0, 1], f(x) <= 0.99999999999999999999")
    assert p.verdict != "proven"
    assert "99999999999999999999/100000000000000000000" in p.note
    # 1 < 1.0000000000000000001 everywhere on [0, 1]: the mathematics is
    # proven; the computation reads the double 1.0 and fails at x = 1
    q = _derive("for x in [0, 1], f(x) < 1.0000000000000000001")
    assert q.verdict == "proven"


def test_a_long_literal_in_the_domain_is_not_read_by_the_proof():
    for law in ("for x in [-1e-400, 1], f(x) >= 0",
                "for x in [0, 0.99999999999999999999], f(x) < 1",
                "for x in [0, 1.00000000000000000001], f(x) <= 1"):
        p = _derive(law)
        assert p.verdict != "proven", law
        assert "has more digits than a double carries" in p.note, law
