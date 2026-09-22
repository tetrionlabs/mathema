# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The recurrence lifter on the derive route: a self-recursive linear
recurrence resolves to its exact closed form via rsolve, with the
soundness gates (integer domain, integer call arguments, interpreter
stack depth) refusing loudly where the closed form stops describing the
actual implementation."""
from mathema.conjecture import claim, check_conjectures


def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def fib_eq(n):
    if n == 0:
        return 0
    if n == 1:
        return 1
    return fib_eq(n - 1) + fib_eq(n - 2)


def doubling(n):
    if n <= 0:
        return 1
    return 2 * doubling(n - 1)


def triangular(n):
    if n <= 0:
        return 0
    return triangular(n - 1) + n


def _verdict(fn, law):
    return check_conjectures(fn, [claim(law, route="derive")])[0]


def test_fibonacci_recurrence_claim_proven():
    r = _verdict(fib, "for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)")
    assert r.verdict == "proven"
    assert r.meta.get("mathema.derive_route") == "recurrence:rsolve"


def test_equality_base_cases_also_close():
    r = _verdict(fib_eq, "for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)")
    assert r.verdict == "proven"


def test_first_order_recurrence_proves_its_closed_form():
    r = _verdict(doubling, "for n in [0, 20] subset Z, f(n) == 2^n")
    assert r.verdict == "proven"


def test_nonhomogeneous_recurrence_proves_its_closed_form():
    r = _verdict(triangular, "for n in [0, 50] subset Z, f(n) == n*(n+1)/2")
    assert r.verdict == "proven"


def test_wrong_closed_form_is_falsified():
    r = _verdict(doubling, "for n in [1, 20] subset Z, f(n) == 3^n")
    assert r.verdict == "falsified"


def test_real_domain_is_gated_with_the_subset_z_remedy():
    # the closed form is only exact at integers, so derive declines
    # with the subset-Z remedy; probing then confirms the (true, by
    # construction) recurrence identity empirically at real points, and
    # the remedy survives in the note
    r = _verdict(fib, "for n in [2, 30], f(n) == f(n-1) + f(n-2)")
    assert r.verdict == "holds"
    assert "subset Z" in r.note


def test_no_domain_is_gated_the_same_way():
    # derive declines (no integer domain); the unbounded probe then
    # finds the identity genuinely fails below the base region: the
    # `n <= 1: return n` clause makes f(0) = 0 while
    # f(-1) + f(-2) = -3, a real counterexample at n = 0
    r = _verdict(fib, "f(n) == f(n-1) + f(n-2)")
    assert r.verdict == "falsified"
    assert r.counterexample


def test_isolated_base_points_make_the_descent_region_a_raise():
    # fib_eq's bases are the isolated points {0, 1}: below them the
    # recursion descends forever, so n < 0 is a RecursionError region
    # and a value claim quantifying over it is false there
    r = _verdict(fib_eq, "for n in [-5, 30] subset Z, f(n) >= 0")
    assert r.verdict == "falsified"
    assert "RecursionError" in r.sketch
    assert "narrow the claim's domain" in r.sketch


def test_stack_depth_beyond_the_interpreter_limit_refuses_to_prove():
    # the closed form settles the mathematics, but fib(100000) raises
    # RecursionError long before returning: proving the claim over that
    # domain would call something proven that the implementation
    # falsifies
    r = _verdict(fib, "for n in [0, 100000] subset Z, f(n) == f(n-1) + f(n-2)")
    # the derive gate refuses to prove past the interpreter limit, and
    # the probe fallback then hits the limit for real: falsified with a
    # RecursionError witness, the machine agreeing with the gate
    assert r.verdict == "falsified"
    assert "recursion limit" in r.note
    assert "RecursionError" in (r.counterexample or "") + r.note


def test_nonlinear_recurrence_declines_to_the_ordinary_report():
    # regression: rsolve does not refuse a nonlinear recurrence, fed
    # `y(n-1)*y(n-2)` it returns a confidently wrong Binet-shaped
    # "solution" rather than raising, which once falsified this (true,
    # constant-1) claim. The lifter's own linearity check must decline
    # before rsolve is ever consulted.
    def product_chain(n):
        if n <= 1:
            return 1
        return product_chain(n - 1) * product_chain(n - 2)

    r = _verdict(product_chain, "for n in [2, 10] subset Z, f(n) == 1")
    # the claim is true, so the only outcome this regression forbids is
    # a falsification; and the nonlinear lifter must not be what
    # decided it, so a plain symbolic "derive" is equally wrong here.
    # (The nine integer points are settled by the brute-force sweep,
    # which is a different mechanism from the lifter entirely.)
    assert r.verdict != "falsified", (r.verdict, r.sketch)
    assert r.route != "derive", (r.route, r.sketch)


def test_disproof_corroboration_respects_an_integer_domain():
    # regression: the counterexample sampler once drew n = -8.77 for a
    # claim declared over [0, 20] subset Z, outside the domain and off
    # the lattice, and falsified a true claim with it. The claim here
    # is FALSE (2^n + 1 != 2^n), so a counterexample must be produced,
    # and it must be an on-lattice integer inside the declared domain
    r = _verdict(doubling, "for n in [0, 20] subset Z, f(n) == 2^n + 1")
    assert r.verdict == "falsified"
    assert r.counterexample
    import re
    nums = re.findall(r"-?\d+(?:\.\d+)?", r.counterexample)
    n_val = float(nums[0])
    assert n_val == int(n_val), r.counterexample     # on the lattice
    assert 0 <= n_val <= 20, r.counterexample        # inside the domain
