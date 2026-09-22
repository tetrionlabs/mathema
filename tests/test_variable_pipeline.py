# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One variable pipeline: a `let`-declared free variable with a bound
gets exactly the treatment a real parameter gets (assumption-carrying
symbol, interval machinery membership), and a target that is a
nonnegative multiple of an assumed gap proves outright. The corpus's
minimal pairs; identical mathematics phrased as let-var vs parameter,
previously proved on one side only."""
from mathema.claims import check_conjectures, claim


def _v(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def test_let_bound_variable_proves_like_a_parameter():
    def take_one(wc):
        return wc
    p = _v(take_one, "let wa be [0,20], for wc in [0,20], f(wc) + wa >= 0")
    assert p.verdict == "proven"


def test_let_bound_variable_ranges_reach_the_interval_machinery():
    def scale(x):
        return 3 * x
    # k's declared range [2, 5] bounds the product away from zero
    p = _v(scale, "let k be [2,5], for x in [1,4], k * f(x) >= 6")
    assert p.verdict == "proven"


def test_scaled_assumed_gap_proves():
    # (b-a)/2 under `assuming a <= b` is half the assumed gap; the
    # subtree rewrite misses it (expansion destroys the literal gap),
    # the ratio check closes it
    def radius(a, b):
        return (b - a) / 2
    p = _v(radius, "assuming a <= b, for a in [0,10], b in [0,10], f(a,b) >= 0")
    assert p.verdict == "proven"
    assert "times the assumed-nonnegative gap" in p.sketch


def test_integer_multiple_of_an_assumed_gap_proves():
    # the corpus's Putnam 2004 A2 shape: -2x+2y+2z is twice y+z-x
    def twice_slack(x, y, z):
        return -2 * x + 2 * y + 2 * z
    p = _v(twice_slack, "assuming y + z >= x, for x in [0.5,50], "
                        "y in [0.5,50], z in [0.5,50], f(x,y,z) >= 0")
    assert p.verdict == "proven"


def test_false_scaled_gap_claim_still_falsifies():
    # a NEGATIVE multiple of the gap must never ride the ratio check
    def neg_radius(a, b):
        return (a - b) / 2
    p = _v(neg_radius,
           "assuming a <= b, for a in [0,10], b in [0,10], f(a,b) >= 0")
    assert p.verdict != "proven"
