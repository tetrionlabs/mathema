# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The automatic nonnegative-gap / WLOG substitution rung: a claim
fully symmetric in same-bounded variables has the sorted order imposed
by substituting nonnegative gaps, turning an ordering hypothesis into
manifest nonnegativity, closing symmetric-inequality gaps sympy's
sign search leaves undecided, with no manual restatement. The rung runs
in the FAST derive pass (no extensive=True needed), gated by a
zero-sympy precheck so only undecided symmetric orderings pay for it."""
from mathema.conjecture import claim, check_conjectures


def _v(fn, law):
    # NO extensive: the rung is part of the fast pass now
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def _v_ext(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")], extensive=True)[0]


def schur(a, b, c):
    return a*(a-b)*(a-c) + b*(b-a)*(b-c) + c*(c-a)*(c-b)


def nesbitt(a, b, c):
    return a/(b+c) + b/(a+c) + c/(a+b)


def amgm2(a, b):
    return (a + b) / 2 - (a * b) ** 0.5


def test_schur_proves_via_gap_substitution_on_the_fast_pass():
    # the whole point: no extensive=True needed
    p = _v(schur, "for a in [0,10], b in [0,10], c in [0,10], f(a,b,c) >= 0")
    assert p.verdict == "proven"
    assert p.meta.get("mathema.derive_route") == "gap_substitution"
    assert "WLOG" in p.sketch


def test_nesbitt_proves_via_gap_substitution_on_the_fast_pass():
    p = _v(nesbitt,
           "for a in [0.1,10], b in [0.1,10], c in [0.1,10], f(a,b,c) >= 1.5")
    assert p.verdict == "proven"
    assert p.meta.get("mathema.derive_route") == "gap_substitution"


def test_gap_result_is_identical_with_or_without_extensive():
    # extensive must not change the gap verdict; it runs in the fast
    # pass before the ladder either way
    law = "for a in [0,10], b in [0,10], c in [0,10], f(a,b,c) >= 0"
    fast = _v(schur, law)
    ext = _v_ext(schur, law)
    assert fast.verdict == ext.verdict == "proven"
    assert (fast.meta.get("mathema.derive_route")
            == ext.meta.get("mathema.derive_route") == "gap_substitution")


def test_symmetric_two_var_still_proves_under_extensive():
    # amgm proves via the extensive substitution rung, not gap, guards
    # that removing the gap rung from the ladder left the ladder intact
    assert _v_ext(amgm2, "for a in [0,10], b in [0,10], f(a,b) >= 0").verdict \
        == "proven"


def test_gap_substitution_needs_full_symmetry_not_just_two_same_bounds():
    # f is NOT symmetric in a, b (the coefficients differ), so no WLOG
    # order may be imposed; the rung must decline, not misprove
    def skew(a, b):
        return 2 * a - b
    p = _v(skew, "for a in [0,5], b in [0,5], f(a,b) >= -5")
    # (true or not, it must never come back proven VIA gap_substitution)
    assert p.meta.get("mathema.derive_route") != "gap_substitution"
