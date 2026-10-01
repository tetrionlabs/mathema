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


def test_a_bound_just_past_the_domain_end_is_not_disproven_by_derive():
    # 0.3 < 0.30000000000000000001, so the mathematics is true; the
    # computation reads the double 0.3 and is left to the probe
    p = _derive("for x in [0, 0.3], f(x) < 0.30000000000000000001")
    assert p.route != "derive"
    assert "derive: undecided (0.30000000000000000001 has more digits" in p.note


def test_a_literal_a_double_reads_exactly_is_unaffected():
    assert _derive("for x in [0, 0.3], f(x) <= 0.3").verdict == "proven"
    assert _derive("for x in [0, 0.30], f(x) <= 0.300").verdict == "proven"
