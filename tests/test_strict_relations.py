# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Strict `<`/`>` relations, end to end: the claim grammar parses them,
the probe route samples them (with the tolerance buffer), and the
derive route decides them through the strict-positivity certificate;
proven only when the difference is certifiably bounded away from (or
excludes) zero, never rounded up from a weak ordering."""
import math

from mathema.conjecture import claim, check_conjectures


def sq_plus(x):
    return x * x + 1.0


def oscillator_amplitude(F0, k, m, w, c):
    return F0 / math.sqrt((k - m*w*w)**2 + (c*w)**2)


def _verdict(fn, law, route="derive"):
    return check_conjectures(fn, [claim(law, route=route)])[0]


def test_strict_claim_proves_via_the_hull():
    assert _verdict(sq_plus, "for x in [-5, 5], f(x) > 0").verdict == "proven"


def test_strict_claim_proves_via_the_sum_certificate_unbounded():
    # x^2 + 1 over the whole line: the hull is unbounded, but a sum of
    # a nonnegative term and a strictly positive constant certifies
    assert _verdict(sq_plus, "f(x) > 0").verdict == "proven"


def test_strict_claim_touching_its_bound_is_never_proven():
    # max of x^2 + 1 on [0, 1] is exactly 2: `> 2` holds nowhere
    p = _verdict(sq_plus, "for x in [0, 1], f(x) > 2")
    assert p.verdict == "falsified"


def test_strict_claim_on_the_probe_route():
    assert _verdict(sq_plus, "for x in [-5, 5], f(x) > 0",
                    route="probe").verdict == "holds"


def test_strict_certificate_excludes_an_equality_guard_without_assuming():
    # with c bounded away from 0 and w away from 0, (c*w)^2 is strictly
    # positive, so the denominator's Eq guard is provably empty and the
    # symmetry proves with no assuming clause at all
    p = _verdict(oscillator_amplitude,
                 "for F0 in [0.1,10], k in [0.1,100], m in [0.1,10], "
                 "w in [1,50], c in [0.1,5], f(F0,k,m,-w,c) == f(F0,k,m,w,c)")
    assert p.verdict == "proven"
