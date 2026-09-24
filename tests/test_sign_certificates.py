# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Nonnegativity certificates for sign questions the interval hull
can't settle: the quadratic (positive-semidefinite form) certificate
and monotone endpoint pinning, each with every side condition verified
over the declared domain."""
import pytest
from mathema.conjecture import claim, check_conjectures


def portfolio_variance(w, s1, s2, rho):
    return w**2*s1**2 + (1-w)**2*s2**2 + 2*w*(1-w)*rho*s1*s2


def _verdict(fn, law):
    # an operational infinity keeps float overflow at huge |w| out of
    # the unbounded weight direction these certificates are about
    return check_conjectures(fn, [claim(law, route="derive",
                                        pseudo_infinity=1e100)])[0]


def test_second_derivative_positive_definite_form_proves():
    # 2*s1^2 + 2*s2^2 - 4*rho*s1*s2 with |rho| < 1: the raw hull
    # straddles zero (the dependency problem), but as a quadratic in s1
    # the discriminant 16*s2^2*(rho^2 - 1) is nonpositive over the box
    r = _verdict(portfolio_variance,
                 "for s1 in [0.05,0.5], s2 in [0.05,0.5], rho in [-0.9,0.9], "
                 "d(f(w,s1,s2,rho), w, w) >= 0")
    assert r.verdict == "proven"
    assert "quadratic" in r.sketch and "discriminant" in r.sketch


def test_semidefinite_boundary_rho_of_one_still_proves():
    r = _verdict(portfolio_variance,
                 "for s1 in [0.05,0.5], s2 in [0.05,0.5], rho in [-1,1], "
                 "d(f(w,s1,s2,rho), w, w) >= 0")
    assert r.verdict == "proven"


def test_indefinite_form_never_falsely_certifies():
    # rho reaching 1.5 makes the form indefinite (negative at
    # s1 = s2, rho = 1.5): the certificate's discriminant condition
    # fails and the claim must not prove
    r = _verdict(portfolio_variance,
                 "for s1 in [0.05,0.5], s2 in [0.05,0.5], rho in [-0.9,1.5], "
                 "d(f(w,s1,s2,rho), w, w) >= 0")
    assert r.verdict != "proven"


@pytest.mark.needs_full_proof_budget
def test_quadratic_in_an_unbounded_variable_with_recursive_side_condition():
    # the variance itself, as a quadratic in the UNBOUNDED w: the
    # leading coefficient s1^2 + s2^2 - 2*rho*s1*s2 is itself a form
    # only the certificate can settle; one level of recursion
    r = _verdict(portfolio_variance,
                 "for s1 in [0.05,0.5], s2 in [0.05,0.5], rho in [-0.9,0.9], "
                 "f(w,s1,s2,rho) >= 0")
    assert r.verdict == "proven"
    assert "quadratic in w" in r.sketch


def test_monotone_pinning_settles_a_non_quadratic_shape():
    # linear in rho (coefficient -x <= 0 over the box), so rho pins to
    # its top, where the -rho*x and +2*x terms cancel exactly and the
    # remaining y^3 hull decides. The raw hull straddles (it can't see
    # the cancellation), and the cubic keeps the quadratic certificate
    # out of reach, only the pinning route closes this.
    def coupled(x, y, rho):
        return y**3 - rho * x + 2 * x

    r = _verdict(coupled,
                 "for x in [0,1], y in [0,1], rho in [-2,2], f(x,y,rho) >= 0")
    assert r.verdict == "proven"
    assert "minimized by monotonicity" in r.sketch


def test_pole_inside_the_box_never_pins_to_an_endpoint():
    # regression (false proof caught in dev): 1/x on [-5, 5] has
    # -1/x^2 <= 0 at every point where it exists, but it is NOT
    # monotone over the punctured box and has no endpoint minimum,
    # the pole breaks the continuity the pinning inference needs.
    # This claim is genuinely false (f(-1) = -1) and must never prove.
    def reciprocal_guarded(x: float) -> float:
        return 0.0 if x == 0.0 else 1.0 / x

    r = _verdict(reciprocal_guarded, "for x in [-5, 5], f(x) >= 0")
    assert r.verdict != "proven"


def test_lower_bound_direction_via_the_same_certificate():
    # <= claims run through the same decider with the sign flipped
    r = _verdict(portfolio_variance,
                 "for s1 in [0.05,0.5], s2 in [0.05,0.5], rho in [-0.9,0.9], "
                 "-d(f(w,s1,s2,rho), w, w) <= 0")
    assert r.verdict == "proven"
