# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The corroboration gate: no derive `falsified` survives unless a
concrete in-domain counterexample reproduces the failure against the
real function. A proven-exact claim whose implementation is
numerically unstable stays proven; its `[float]` companion is what the
instability falsifies."""
import math

from mathema.conjecture import claim, check_conjectures


def _v(fn, law, **kw):
    return check_conjectures(fn, [claim(law, route="derive", **kw)])[0]


def _pair(fn, law, **kw):
    kw.setdefault("route", "derive")
    probes = check_conjectures(fn, [claim(law, name="law", **kw)],
                               float_companions=True)
    by_name = {p.name: p for p in probes}
    return by_name["law"], by_name.get("law[float]")


def test_a_genuine_disproof_reproduces_and_stays_falsified():
    def neg(x):
        return -x
    p = _v(neg, "for x in [1, 5], f(x) >= 0")
    assert p.verdict == "falsified"
    assert p.meta.get("mathema.corroboration") == "reproduced"
    assert p.counterexample


def test_a_disproof_reproduced_via_the_seed_is_semi_analytical():
    # the witness seed guides the reproduction here (the failure region
    # around x=0 is what derive's witness points at), so the route is
    # exactly probe:semi_analytical, pinned, not a permissive set
    def sqm1(x):
        return x * x - 1.0
    p = _v(sqm1, "for x in [-2, 2], f(x) >= 0")
    assert p.verdict == "falsified"
    assert p.route == "probe:semi_analytical"


def test_uncorroborated_disproof_downgrades_and_probe_supersedes(monkeypatch):
    # the soundness centerpiece, exercised directly: a decider that
    # LIES (a forged disproven for a claim that is true everywhere) is
    # downgraded to unknown, never asserted as falsified, and, per
    # route supersession, the claim falls through to the probe stage,
    # whose real empirical evidence wins. The engine-bug signal
    # survives onto the winner: the uncorroborated meta and a note
    # naming the probable bug, whichever route adjudicated
    from mathema.symbolic import _proof_support as ps

    def forged_disproof(lhs, rhs, diff, relation, domain, bound_context, params,
                        tolerance=1e-9):
        return ps.ProofResult("disproven", sketch="forged sign error",
                              witness={"x": 3.0}, disproof_hint=None)

    monkeypatch.setitem(ps._RELATION_DECIDERS, ">=", forged_disproof)

    def sq(x):
        return x * x
    p = _v(sq, "for x in [-5, 5], f(x) >= 0")   # true everywhere
    assert p.verdict == "holds"    # empirical truth supersedes the unknown
    assert p.counterexample is None
    assert p.meta.get("mathema.corroboration") == "uncorroborated"
    assert "UNCORROBORATED" in p.note and "engine bug" in p.note


def test_an_unbounded_exp_claim_is_falsified_by_its_overflow():
    # exact in real arithmetic, but math.exp raises OverflowError past
    # x = 709.78, which lies inside the unbounded domain, so the claim
    # is false there; on a range inside the representable region it
    # is proven
    def grow(x):
        return math.exp(x)
    p = _v(grow, "f(x) == exp(x)")
    assert p.verdict == "falsified"
    assert p.counterexample
    assert _v(grow, "for x in [-700, 700], f(x) == exp(x)").verdict == "proven"


def test_an_unbounded_uncapped_proof_stands_and_its_companion_reaches_far():
    # exact in real arithmetic, and the float implementation collapses
    # to 0 past 2^53; with no operational infinity declared the
    # companion runs the unbounded direction to a large magnitude, so
    # the collapse falsifies the companion and the proof stands
    def plus_one_minus(x):
        return (x + 1.0) - x
    proof, companion = _pair(plus_one_minus, "f(x) == 1")
    assert proof.verdict == "proven"
    assert companion.verdict == "falsified"


def test_operational_infinity_bounds_the_companion():
    def plus_one_minus(x):
        return (x + 1.0) - x
    # bound comfortably inside exact float addition -> the companion holds
    proof, companion = _pair(plus_one_minus, "f(x) == 1", pseudo_infinity=100.0)
    assert proof.verdict == "proven"
    assert companion.verdict == "holds"
    # bound past 2^53: the author DECLARED 1e17 as operational
    # infinity, so the companion visits it and the collapse to 0 there
    # is a real finding, about the implementation only
    proof, companion = _pair(plus_one_minus, "f(x) == 1", pseudo_infinity=1e17)
    assert proof.verdict == "proven"
    assert companion.verdict == "falsified"
    assert "fails it at" in companion.sketch


def test_the_companion_catches_in_domain_fragility():
    # the claim proves exactly in real arithmetic, and the declared
    # (finite) domain contains a point where the float implementation
    # breaks, (x + 1) - x collapses to 0 past 2^53
    def plus_one_minus(x: float) -> float:
        return (x + 1.0) - x
    proof, companion = _pair(plus_one_minus, "for x in [0, 1e16], f(x) == 1")
    assert proof.verdict == "proven"
    assert companion.verdict == "falsified"
    assert "x=1e+16" in companion.counterexample


def test_bounded_domain_proof_is_stable():
    def dbl(x):
        return 2 * x
    proof, companion = _pair(dbl, "for x in [1, 5], f(x) >= x")
    assert proof.verdict == "proven"
    assert companion.verdict == "holds"


def test_math_only_leaves_the_proof_without_a_companion():
    def plus_one_minus(x):
        return (x + 1.0) - x
    proof, companion = _pair(plus_one_minus, "f(x) == 1", pseudo_infinity=1e17,
                             route="derive:math_only")
    assert proof.verdict == "proven"
    assert companion is None


def test_integer_kind_parameter_is_swept_at_integer_points():
    # a loop count is integer-kind (`int` annotation / `range(t)`); the
    # companion must feed it an int, not a float corner endpoint, or
    # `range(0.0)` raises a TypeError that is a type mismatch, not
    # numerical instability; the claim is exact and the code agrees
    def scale_loop(a0: float, r: float, t: int) -> float:
        a = a0
        for _ in range(t):
            a *= r
        return a
    proof, companion = _pair(
        scale_loop,
        "for a0 in [0.1,10], r in [1,2], t in [0,20], f(a0,r,t) == a0*r**t")
    assert proof.verdict == "proven"
    assert companion.verdict == "holds", companion.sketch
