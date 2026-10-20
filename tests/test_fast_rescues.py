# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The fast-pass rescue rungs beyond gap substitution: the squaring
rewrite for radical comparisons (both isolated sides provably
nonnegative, so squaring preserves the relation) and loggamma
canonicalization (rewrite to log(gamma), combine, expand the
functional equation). Each is gated by a near-free structural check
and runs in the ordinary fast derive pass, no extensive=True."""
import math

from mathema.claims import check_conjectures, claim


def _v(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def qm_am(a, b):
    return math.sqrt((a * a + b * b) / 2) - (a + b) / 2


def gm_hm(a, b):
    return math.sqrt(a * b) - 2 * a * b / (a + b)


def test_qm_am_proves_via_squaring():
    p = _v(qm_am, "for a in [0,10], b in [0,10], f(a,b) >= 0")
    assert p.verdict == "proven"
    assert p.meta.get("mathema.derive_route") == "squared_comparison"
    assert "squaring preserves the relation" in p.sketch


def test_gm_hm_proves_via_squaring():
    p = _v(gm_hm, "for a in [0.1,10], b in [0.1,10], f(a,b) >= 0")
    assert p.verdict == "proven"
    assert p.meta.get("mathema.derive_route") == "squared_comparison"


def test_squaring_declines_when_a_side_is_not_provably_nonnegative():
    # sqrt(x) - x on [0, 4]: the negated side is x (nonneg), the claim
    # is genuinely false past x=1, and squaring must never misprove it
    def root_minus_x(x):
        return math.sqrt(x) - x
    p = _v(root_minus_x, "for x in [0, 4], f(x) >= 0")
    assert p.verdict == "falsified"


def test_loggamma_recurrence_proves_via_canonicalization():
    def lgm(x):
        return math.lgamma(x + 1) - math.lgamma(x)
    p = _v(lgm, "for x in [1,10], f(x) == log(x)")
    assert p.verdict == "proven"
    assert p.meta.get("mathema.derive_route") == "loggamma_canonicalization"
    assert "log(gamma)" in p.sketch


def test_loggamma_stays_untouched_off_the_positive_axis():
    # domain reaches negative territory: loggamma(x) != log(gamma(x))
    # there, so the rewrite must not fire and misprove; any honest
    # verdict but a canonicalization-route proof is acceptable
    def lgm(x):
        return math.lgamma(x + 1) - math.lgamma(x)
    p = _v(lgm, "for x in [-10, 10], f(x) == log(x)")
    assert p.meta.get("mathema.derive_route") != "loggamma_canonicalization"
