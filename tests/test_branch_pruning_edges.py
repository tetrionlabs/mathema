# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Branch-pruning edge cases reported from field use: guard shapes a
working mathematician writes without thinking (a chained comparison, an
abs() guard, an integer-domain guard, a param-vs-param comparison, a
negative literal, `math.log10`) that each used to need tribal knowledge
to spell in a provable way. Every function here is a claim over a
declared domain that fully clears (or fully lands in) the guard, so the
branch pruner plus the interval pass should prove it outright."""
import math

from mathema.conjecture import check_conjectures, claim


def chained(x: float) -> float:
    if 0 < x < 1:
        return x
    return 0.0


def neg_literal(x: float) -> float:
    if x > -1:
        return x + 1.0
    return 0.0


def abs_guard(x: float) -> float:
    if abs(x) > 3:
        return 0.0
    return x + 5.0


def log10_body(x: float) -> float:
    return math.log10(x)


def log2_body(x: float) -> float:
    return math.log2(x)


def int_guard(n: float) -> float:
    if n > 5:
        return n
    return 5.0


def param_vs_param(p: float, q: float) -> float:
    if p > q:
        return p - q
    return 0.0


def combine(a: float, b: float) -> float:
    return a * 2.0 + b


def _prove(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    return p


def test_chained_comparison_guard_prunes():
    # `0 < x < 1` is one ast.Compare with two ops; it must read as the
    # conjunction of its pairwise comparisons, not fall to "unsupported
    # condition shape".
    _prove(chained, "for x in [0.2, 0.8], f(x) == x")


def test_negative_literal_guard_prunes():
    _prove(neg_literal, "for x in [0, 10], f(x) == x + 1")


def test_abs_guard_prunes_via_interval():
    # |x| on [0, 1] never exceeds 3, so only the fallthrough branch is
    # live, decided by interval evaluation of the guard, since abs is
    # not affine.
    _prove(abs_guard, "for x in [0, 1], f(x) == x + 5")


def test_integer_domain_guard_prunes():
    # a `subset Z` domain carries Domain-typed bounds; the guard
    # comparison must still resolve against them.
    _prove(int_guard, "for n in [6, 100] subset Z, f(n) == n")


def test_param_vs_param_guard_prunes():
    # the guard compares two parameters; disjoint declared boxes decide
    # it.
    _prove(param_vs_param, "for p in [5, 9], q in [0, 1], f(p, q) == p - q")


def test_log10_and_log2_lift_and_prove():
    # math.log10/log2 must lift to sympy's base-carrying log form, and
    # the resulting log(x)/log(10) sign question is decided by the
    # interval pass (sympy's own ask() crashes internally on this
    # shape; that crash must surface as undecided, never an error).
    p = _prove(log10_body, "for x in [10, 1000], f(x) >= 1")
    assert "interval evaluation" in p.sketch
    # the knife edge: at x = 2 the bound is attained exactly
    # (log2(2) == 1). Endpoint arithmetic must stay exact, rationalized
    # bounds make log(2)/log(2) - 1 collapse to a true zero, because
    # float noise here would leave the sign undecidable.
    _prove(log2_body, "for x in [2, 64], f(x) >= 1")


def test_aliased_arguments_prove_with_real_parameter_names():
    # passing the same variable twice is fine as long as the quantifier
    # binds a real parameter name (or aliases one via `let`).
    _prove(combine, "for a in [0, 5], f(a, a) == 3*a")
    _prove(combine, "let x = a, for a in [0, 5], f(x, x) == 3*x")


def test_open_endpoint_decides_a_strict_guard():
    # the knife edge for `x > -1`: on `(-1, 10]` the guard is always
    # true precisely because the endpoint is open, treating the
    # Interval as a closed tuple loses exactly this.
    _prove(neg_literal, "for x in (-1, 10], f(x) == x + 1")


def test_fully_open_domain_decides_a_chained_guard():
    _prove(chained, "for x in (0, 1), f(x) == x")


def test_straddling_guard_proves_by_domain_split():
    # n = 5 takes the else branch (f = 5), everything above takes the
    # guard branch (f = n): no single branch covers [5, 100], so the
    # domain must split at the guard boundary and each piece prove
    # separately.
    p = _prove(int_guard, "for n in [5, 100] subset Z, f(n) >= 5")
    assert "split" in p.sketch


def test_chained_guard_straddling_both_ends_splits_into_pieces():
    # [0, 1] against `0 < x < 1`: both endpoints land outside the open
    # guard interval, so the split yields point pieces at 0 and 1 plus
    # the open interior, each proven on its own live branch.
    p = _prove(chained, "for x in [0, 1], f(x) >= 0")
    assert "split" in p.sketch


def test_domain_split_falsifies_on_the_failing_piece():
    # f(0) = 0 < 0.1: the claim fails exactly on the {0} piece, and the
    # counterexample must name that sub-domain rather than reporting an
    # undecided guard.
    (p,) = check_conjectures(
        chained, [claim("for x in [0, 1], f(x) >= 0.1", route="derive")])
    assert p.verdict == "falsified"
    assert "sub-domain" in p.sketch


def test_attained_bound_at_the_endpoint_proves_exactly():
    # cos(0)/2 == 0.5 exactly: the interval's upper endpoint is
    # attained, so `<= 0.5` is provable only if endpoint arithmetic is
    # exact rather than float-noisy.
    def half_cos(theta: float) -> float:
        return math.cos(theta) / 2.0

    _prove(half_cos, "for theta in [-0.1, 0.1], f(theta) <= 0.5")


def test_guard_boundary_attained_but_strict_still_prunes():
    # |x| reaches exactly 3 at the endpoints, but `abs(x) > 3` is still
    # never true on [-3, 3], the strict comparison against the
    # attained hull maximum must decide, not straddle.
    _prove(abs_guard, "for x in [-3, 3], f(x) == x + 5")


def test_aliased_arguments_with_fresh_name_skip_and_say_why():
    # a fresh name with no `let` alias has no real parameter to bind:
    # the claim must skip with a note naming the real parameters, not
    # guess.
    (p,) = check_conjectures(
        combine, [claim("for x in [0, 5], f(x, x) == 3*x", route="derive")])
    assert p.verdict == "skipped"
    assert "real parameter" in p.note
