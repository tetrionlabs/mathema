# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The extensive strategy ladder: root isolation, interval refinement,
the rewrite gallery, and the substitution library, each engaged only
under `extensive=True` and each sound on its own terms. The base fast
path must be unchanged: everything here stays unknown without
extensive, and a false claim must falsify with a real witness, never
prove."""
import math

import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._extensive import (
    _refine_decide, _sturm_decide, _substituted_attempts,
)


def xsin(x: float) -> float:
    return x * math.sin(x)


def quartic(x: float) -> float:
    return x ** 4 - 2.0 * x ** 2 + 1.5


def logpoly(x: float) -> float:
    return math.log(x) ** 2 - 2.0 * math.log(x) + 1.5


def _one(fn, law, extensive=False):
    (p,) = check_conjectures(fn, [claim(law, route="derive")],
                             extensive=extensive)
    return p


def test_refinement_proves_what_a_single_hull_straddles():
    # x*sin(x) on [-1, 1]: one box straddles zero (the dependency
    # problem), two half-boxes certify. Fast path stays honest.
    fast = _one(xsin, "for x in [-1, 1], f(x) >= 0")
    assert fast.verdict == "holds"   # fast derive declines; probed instead
    assert fast.route == "probe"
    p = _one(xsin, "for x in [-1, 1], f(x) >= 0", extensive=True)
    assert p.verdict == "proven"
    assert p.route == "derive:extensive"
    assert "interval refinement" in p.sketch


def test_refinement_falsifies_with_a_witness_region():
    # f(0) = 0 < 0.5: refinement must find a cell wholly below zero and
    # name a point of it, even while other cells genuinely straddle.
    p = _one(xsin, "for x in [-1, 1], f(x) >= 0.5", extensive=True)
    assert p.verdict == "falsified"
    assert p.counterexample is not None


def test_root_isolation_settles_a_quartic_exactly():
    # min of x^4 - 2x^2 + 1.5 is 0.5 at x = +-1: >= 0 proven, >= 1
    # falsified with an exact witness, != 0 proven, all by exact
    # real-root analysis, no floating point anywhere.
    assert _one(quartic, "for x in [-3, 3], f(x) >= 0",
                extensive=True).verdict == "proven"
    p = _one(quartic, "for x in [-3, 3], f(x) >= 1", extensive=True)
    assert p.verdict == "falsified"
    assert p.counterexample is not None
    assert _one(quartic, "for x in [-3, 3], f(x) != 0",
                extensive=True).verdict == "proven"


def test_ladder_closes_a_logarithmic_polynomial():
    fast = _one(logpoly, "for x in [0.1, 100], f(x) >= 0")
    assert fast.verdict == "holds"   # fast derive declines; probed instead
    p = _one(logpoly, "for x in [0.1, 100], f(x) >= 0", extensive=True)
    assert p.verdict == "proven"
    assert p.route == "derive:extensive"


def test_substitution_rung_carries_domain_and_question_through():
    # driven directly so the test pins the substitution mechanism
    # itself, not whichever earlier rung happens to fire first: in
    # t = log(x) space the question is a rational-coefficient
    # polynomial, settled exactly.
    x = sympy.Symbol("x", real=True, positive=True)
    diff = sympy.log(x) ** 2 - 2 * sympy.log(x) + sympy.Rational(3, 2)
    attempted = []
    result = _substituted_attempts(diff, ">=", {"x": (0.1, 100.0)}, {"x": x},
                                   attempted)
    assert result is not None and result.status == "proven"
    assert "t = log(x)" in result.sketch
    assert any("t = log(x)" in a for a in attempted)


def test_sturm_never_reports_a_witness_outside_the_domain():
    # roots at x = +-1 sit outside [2, 3]; the region sampling must
    # still cover [2, 3] correctly and prove the positive sign there.
    x = sympy.Symbol("x", real=True)
    diff = x ** 2 - 1
    result = _sturm_decide(diff, ">=", {"x": (2.0, 3.0)}, {"x": x})
    assert result is not None and result.status == "proven"


def test_sturm_samples_every_sign_region_between_abutting_isolations():
    # the quartic's isolating intervals abut ((-2,-1),(-1,0),...): the
    # negative dip between the roots must still be sampled; this
    # exact shape once produced a false proof.
    x = sympy.Symbol("x", real=True)
    diff = x ** 4 - 2 * x ** 2 + sympy.Rational(1, 2)
    result = _sturm_decide(diff, ">=", {"x": (-3.0, 3.0)}, {"x": x})
    assert result is not None and result.status == "disproven"


def test_refinement_budget_exhaustion_never_proves():
    # the claim is true (x*sin(x) >= 0 on [-1, 1]) but one cell isn't
    # enough to certify it; an incomplete sweep must come back None,
    # never "proven".
    x = sympy.Symbol("x", real=True)
    result = _refine_decide(x * sympy.sin(x), ">=", {"x": (-1.0, 1.0)},
                            {"x": x}, max_cells=1)
    assert result is None


def test_refinement_disproves_a_real_oscillation_dip():
    # sin(1/x) is genuinely negative on part of [0.001, 1] (any x with
    # 1/x in (pi, 2*pi)); refinement must find such a region and name a
    # point inside it.
    x = sympy.Symbol("x", real=True)
    result = _refine_decide(sympy.sin(1 / x), ">=", {"x": (0.001, 1.0)},
                            {"x": x})
    assert result is not None and result.status == "disproven"
    witness = sympy.Rational(result.counterexample.split("=")[1].strip())
    assert sympy.sin(1 / witness).evalf() < 0


def test_undecided_extensive_run_names_what_it_tried():
    # a true claim over the whole line (x*sin(x) >= -x**2, equality
    # hit infinitely often) that no rung settles: the record must say
    # what was attempted rather than a bare unknown.
    p = _one(xsin, "f(x) >= -x^2", extensive=True)
    # every rung declines; the probe fallback then supplies empirical
    # support, with the attempted-rungs account preserved in the note
    assert p.verdict == "holds"
    assert "extensive attempts did not settle it" in p.note


def test_atan_compactification_falsifies_over_the_whole_line():
    # f(x) >= -2 is false far from the origin (x*sin(x) reaches every
    # depth); the t = atan(x) substitution compactifies the line and
    # refinement finds a violation cell, with the witness mapped back
    # through tan to a genuine original-variable counterexample.
    p = _one(xsin, "f(x) >= -2", extensive=True)
    assert p.verdict == "falsified"
    assert "atan" in p.sketch
    value_text = p.counterexample.split("=", 1)[1].split("(~")[0].strip()
    x_val = float(sympy.sympify(value_text))
    assert x_val * math.sin(x_val) < -2
