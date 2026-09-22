# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Guarded folds and domain sugar: leading raise guards strip before
fold recognition and gate on the claim's domain; bound endpoints
accept constant arithmetic; `name != value` folds to a point
exclusion; atan2/gcd/floor-division join the vocabulary; diagnostics
honor a supplied domain and holds-rescued derive gaps carry their
reason code."""
import math

from mathema.analysis import analyze_source
from mathema.claims import check_conjectures, claim
from mathema.symbolic._fold import lift_fold, try_prove_fold


def _v(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def guarded_ema(x: list, alpha: float) -> float:
    if alpha < 0:
        raise ValueError("negative weight")
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def test_leading_raise_guard_no_longer_refuses_the_fold():
    facts = analyze_source(guarded_ema)
    fold = lift_fold(guarded_ema, facts)
    assert fold is not None
    assert len(fold.raise_guards) == 1


def test_guard_avoided_by_the_domain_lets_the_fold_prove():
    p = _v(guarded_ema, "for alpha in [0, 1], f(x, 1.0) == x[-1]")
    assert p.verdict == "proven"


def test_reachable_guard_blocks_the_closed_form_with_guidance():
    facts = analyze_source(guarded_ema)
    r = try_prove_fold(guarded_ema, facts, "f(x, 1.0)", "x[-1]", "==",
                       domain={"alpha": (-1.0, 1.0)})
    assert r.status == "undecided"
    assert "raise guard" in r.sketch and "raises(...)" in r.sketch


def test_constant_arithmetic_bounds_parse():
    def sq(x):
        return x * x
    p = _v(sq, "for x in [1, 10**3], f(x) >= 1")
    assert p.verdict == "proven"
    p = _v(sq, "for x in [0, 2*pi], f(x) >= 0")
    assert p.verdict == "proven"


def test_ne_domain_segment_folds_into_a_point_exclusion():
    def recip_gap(x):
        return 1.0 / (x - 2.0)
    # x != 2 between bindings is the same set as [0,4] \ {2}
    p = _v(recip_gap, "for x in [0, 4], x != 2, f(x) != 0")
    assert p.verdict in ("proven", "holds")


def test_atan2_and_gcd_join_the_vocabulary():
    def polar_angle(y, x):
        return math.atan2(y, x)
    assert _v(polar_angle,
              "for y in [1,5], x in [1,5], f(y,x) >= 0").verdict == "proven"

    def common(a: int, b: int) -> int:
        return math.gcd(a, b)
    assert _v(common, "for a in [1, 50] subset Z, b in [1, 50] subset Z, "
                      "f(a,b) >= 1").verdict == "proven"


def test_floor_division_lifts():
    def half(n: int) -> int:
        return n // 2
    p = _v(half, "for n in [0, 100] subset Z, f(n) <= n")
    # lifts to floor(n/2); the sign question may stay empirical, but
    # the vocabulary gap (an unliftable body) is closed
    assert p.verdict in ("proven", "holds")
    assert "vocabulary doesn't cover" not in (p.note or "")


def test_holds_rescued_derive_gap_carries_a_reason_code():
    from mathema.reason_codes import ClaimReasonCode, claim_reason_code

    def tri(a, b):
        return abs(a) + abs(b) - abs(a + b)
    (p,) = check_conjectures(tri, [claim(
        "for a in [-50,50], b in [-50,50], f(a,b) >= 0", route="derive")])
    assert p.verdict == "holds"
    assert claim_reason_code(p) == ClaimReasonCode.DERIVE_GAP_EMPIRICAL

    def dbl(x):
        return 2 * x
    (q,) = check_conjectures(dbl, [claim("for x in [0,5], f(x) >= x",
                                         route="derive")])
    assert q.verdict == "proven" and claim_reason_code(q) is None


def test_liftable_diagnostic_honors_a_supplied_domain():
    from mathema.diagnostics import diagnostic_report

    def guarded(x, lam):
        if lam <= 0:
            raise ValueError("rate")
        return math.exp(-lam * x)
    facts = analyze_source(guarded)
    bare = diagnostic_report(guarded, facts)
    assert bare["liftable"] is False
    assert "liftable_note" in bare   # honest about the domain-free read
    conditioned = diagnostic_report(guarded, facts,
                                     declared_domain={"lam": (0.1, 5.0)})
    assert conditioned["liftable"] is True
