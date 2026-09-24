# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The corroboration gate: no derive `falsified` survives unless a
concrete in-domain counterexample reproduces the failure against the
real function; a proven-exact claim whose implementation is
numerically unstable is falsified with the reason (the stability sweep
is opt-in via set_numerical_stability_check; the disproof-reproduction
half is always live)."""
import math

import pytest

from mathema import conjecture
from mathema.conjecture import claim, check_conjectures


@pytest.fixture(autouse=True)
def _stability_on():
    # this file exercises the default-on numerical-stability sweep that
    # the suite-wide conftest fixture turns off
    conjecture.set_numerical_stability_check(True)
    yield
    conjecture.set_numerical_stability_check(False)


def _v(fn, law, **kw):
    return check_conjectures(fn, [claim(law, route="derive", **kw)])[0]


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


def test_scoped_sweep_leaves_an_unbounded_uncapped_proof_alone():
    # exact in real arithmetic, and the float implementation collapses
    # to 0 past 2^53, but with no operational infinity bound the scoped
    # sweep never visits an extreme: the unbounded direction is
    # is_extremity_safe's own job, so the proof stands
    def plus_one_minus(x):
        return (x + 1.0) - x
    p = _v(plus_one_minus, "f(x) == 1")
    assert p.verdict == "proven"


def test_operational_infinity_opts_the_sweep_into_extremes():
    def plus_one_minus(x):
        return (x + 1.0) - x
    # bound comfortably inside exact float addition -> proven
    p = _v(plus_one_minus, "f(x) == 1", pseudo_infinity=100.0)
    assert p.verdict == "proven"
    # bound past 2^53: the author DECLARED 1e17 as operational
    # infinity, so the sweep visits it and the collapse to 0 there is
    # a real finding
    p2 = _v(plus_one_minus, "f(x) == 1", pseudo_infinity=1e17)
    assert p2.verdict == "falsified"
    assert "numerically unstable" in p2.sketch
    assert p2.meta.get("mathema.numerically_unstable")


def test_scoped_sweep_still_catches_in_domain_fragility():
    # the sweep's whole reason to exist, intact under scoping: the
    # claim proves exactly in real arithmetic, and the declared
    # (finite) domain contains a point where the float implementation
    # breaks, (x + 1) - x collapses to 0 past 2^53
    def plus_one_minus(x: float) -> float:
        return (x + 1.0) - x
    p = _v(plus_one_minus, "for x in [0, 1e16], f(x) == 1")
    assert p.verdict == "falsified"
    assert "numerically unstable" in p.sketch
    assert "x=1e+16" in p.counterexample


def test_bounded_domain_proof_is_stable():
    def dbl(x):
        return 2 * x
    assert _v(dbl, "for x in [1, 5], f(x) >= x").verdict == "proven"


def test_stability_check_off_leaves_the_proof():
    conjecture.set_numerical_stability_check(False)
    def plus_one_minus(x):
        return (x + 1.0) - x
    assert _v(plus_one_minus, "f(x) == 1", pseudo_infinity=1e17).verdict \
        == "proven"


def test_integer_kind_parameter_is_swept_at_integer_points():
    # a loop count is integer-kind (`int` annotation / `range(t)`); the
    # stability sweep must feed it an int, not a float corner endpoint,
    # or `range(0.0)` raises a TypeError that is a type mismatch, not
    # numerical instability; the claim is exact and proves
    def scale_loop(a0: float, r: float, t: int) -> float:
        a = a0
        for _ in range(t):
            a *= r
        return a
    p = _v(scale_loop,
           "for a0 in [0.1,10], r in [1,2], t in [0,20], f(a0,r,t) == a0*r**t")
    assert p.verdict == "proven"
