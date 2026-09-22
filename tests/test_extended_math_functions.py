# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""_SYMPY_FUNCS (mathema/_math_vocab.py) gains sinh/cosh/tanh/factorial/
gamma/lgamma, both a function body calling math.sinh/etc. now lifts,
and claim text can reference these names directly.

factorial/gamma/sqrt/log/asin/acos also get a real is_builtin_safe[param]
claim (the is_builtin_safe ClaimFamily, probing.py), suggested
automatically by suggest_claims() for any parameter fed into one of
these: sympy's own symbolic generalization is often wider than the real
math function's own accepted domain (math.factorial only accepts a
non-negative int; math.sqrt/log/asin/acos raise outside their own real
ranges), so a plain equality claim proving true via the generalization
isn't automatically a fact about the real function too.

gamma/loggamma's own poles (every non-positive integer of their bare-
symbol argument) are covered by is_pole_safe[param] instead, a
diagnostics._integer_pole_hazards()-produced hazard class distinct from
_pole_hazards' ordinary finite-root-set poles, since there's no single
denominator-zero root to solve for."""
import math

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def sinh_fn(x: float) -> float:
    return math.sinh(x)


def fact(n: int) -> int:
    return math.factorial(n)


def sqrt_fn(x: float) -> float:
    return math.sqrt(x)


def log_fn(x: float) -> float:
    return math.log(x)


def asin_fn(x: float) -> float:
    return math.asin(x)


def gamma_fn(x: float) -> float:
    return math.gamma(x)


def test_sinh_lifts_and_proves_reflexively():
    results = check_conjectures(sinh_fn, [claim("f(x) == sinh(x)", route="derive")])
    assert results[0].verdict == "proven"


def test_sinh_derivative_is_cosh():
    results = check_conjectures(sinh_fn, [claim("d(f(x), x) == cosh(x)", route="derive")])
    assert results[0].verdict == "proven"


def test_tanh_is_sinh_over_cosh():
    def tanh_fn(x: float) -> float:
        return math.tanh(x)

    results = check_conjectures(
        tanh_fn, [claim("f(x) == sinh(x) / cosh(x)", route="derive")])
    assert results[0].verdict == "proven"


# --- is_builtin_safe[param]: the family, directly ------------------------

def test_factorial_numeric_safe_proven_over_a_declared_N_domain():
    results = check_conjectures(
        fact, [claim("is_builtin_safe(n)", name="is_builtin_safe[n]", route="derive"),
              claim("for n in N, f(n) == gamma(n + 1)", route="derive")],
        domain={"n": "N"})
    by_name = {r.name: r for r in results}
    assert by_name["is_builtin_safe[n]"].verdict == "proven"


def test_factorial_numeric_safe_falsified_over_a_plain_interval():
    # gamma(n+1) is sympy's own definition of factorial(n), true for
    # any real n, not just the non-negative integers math.factorial
    # itself accepts. The equality claim is correctly proven regardless
    # (it's a fact about the continuous extension); is_builtin_safe[n]
    # is the honest, separate signal that a real counterexample exists
    # in [0, 10] (e.g. 0.5) where math.factorial itself would raise.
    results = check_conjectures(
        fact, [claim("is_builtin_safe(n)", name="is_builtin_safe[n]", route="derive")],
        domain={"n": (0, 10)})
    assert results[0].verdict == "falsified"


def test_factorial_numeric_safe_falsified_over_an_entirely_negative_interval():
    results = check_conjectures(
        fact, [claim("is_builtin_safe(n)", name="is_builtin_safe[n]", route="derive")],
        domain={"n": (-10, -1)})
    assert results[0].verdict == "falsified"


def test_factorial_numeric_safe_falsified_with_no_domain_at_all():
    # an unstated domain asserts everywhere (declared-schema.md, "Domain
    # is a claim field"), "everywhere" includes a negative integer,
    # a real counterexample, so this is a real falsification, not
    # merely undecided.
    results = check_conjectures(
        fact, [claim("is_builtin_safe(n)", name="is_builtin_safe[n]", route="derive")])
    assert results[0].verdict == "falsified"


def test_sqrt_numeric_safe_proven_over_a_nonnegative_interval():
    results = check_conjectures(
        sqrt_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (0, 100)})
    assert results[0].verdict == "proven"


def test_sqrt_numeric_safe_falsified_over_a_straddling_interval():
    # not just "entirely negative", [-5, 5] contains a real
    # counterexample (-3) even though it isn't uniformly unsafe either.
    results = check_conjectures(
        sqrt_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (-5, 5)})
    assert results[0].verdict == "falsified"


def test_log_numeric_safe_proven_over_a_strictly_positive_interval():
    results = check_conjectures(
        log_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (0.1, 100)})
    assert results[0].verdict == "proven"


def test_log_numeric_safe_falsified_when_domain_includes_zero():
    results = check_conjectures(
        log_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (-5, 0)})
    assert results[0].verdict == "falsified"


def test_asin_numeric_safe_proven_within_minus_one_to_one():
    results = check_conjectures(
        asin_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (-0.5, 0.5)})
    assert results[0].verdict == "proven"


def test_asin_numeric_safe_falsified_entirely_outside_range():
    results = check_conjectures(
        asin_fn, [claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (2, 5)})
    assert results[0].verdict == "falsified"


# --- is_pole_safe[param]: gamma/loggamma's own infinite pole class -------

def test_gamma_pole_safe_proven_over_a_strictly_positive_interval():
    results = check_conjectures(
        gamma_fn, [claim("is_pole_safe(x)", name="is_pole_safe[x]", route="derive")],
        domain={"x": (0.5, 10.0)})
    assert results[0].verdict == "proven"


def test_gamma_pole_safe_falsified_when_domain_includes_a_pole():
    results = check_conjectures(
        gamma_fn, [claim("is_pole_safe(x)", name="is_pole_safe[x]", route="derive")],
        domain={"x": (-3.0, 3.0)})
    assert results[0].verdict == "falsified"
    assert "0" in results[0].counterexample


def test_gamma_pole_safe_unsure_with_an_offset_argument():
    # gamma(x + 1) (an offset, not a bare symbol) is a disclosed
    # scoping limit: _integer_pole_hazards only recognizes gamma(var)
    # directly, so this stays undecided (unknown) rather than a
    # guessed verdict.
    def gamma_offset(x: float) -> float:
        return math.gamma(x + 1)

    results = check_conjectures(
        gamma_offset, [claim("is_pole_safe(x)", name="is_pole_safe[x]", route="derive")],
        domain={"x": (-3.0, 3.0)})
    assert results[0].verdict == "unknown"


def test_no_ordinary_derive_route_for_is_pole_safe_or_is_builtin_safe():
    # confirms these two never fall through to try_prove()'s own
    # lhs/rhs machinery when the family declines, straight to an
    # honest skip, same route="derive" invariant every other family
    # honors.
    def plain(x: float) -> float:
        return x * 2.0

    results = check_conjectures(
        plain, [claim("is_pole_safe(x)", name="is_pole_safe[x]", route="derive"),
               claim("is_builtin_safe(x)", name="is_builtin_safe[x]", route="derive")],
        domain={"x": (0, 10)})
    assert all(r.verdict == "unknown" for r in results)


# --- suggest_claims() wiring ---------------------------------------------

def test_suggest_claims_includes_is_builtin_safe_for_a_factorial_call():
    facts = analyze_source(fact)
    claims = {c.name: c for c in suggest_claims(fact, facts=facts)}
    assert "is_builtin_safe[n]" in claims
    # route="best": the family registers a real empirical half (edge
    # trials), so the suggestion cascades derive -> probe
    assert claims["is_builtin_safe[n]"].route == "examine"


def test_suggest_claims_includes_is_pole_safe_for_a_gamma_call():
    facts = analyze_source(gamma_fn)
    claims = {c.name: c for c in suggest_claims(gamma_fn, facts=facts)}
    assert "is_pole_safe[x]" in claims
    # route="best": the family registers a real empirical half
    # (admitted-pole trials), so the suggestion cascades derive -> probe
    assert claims["is_pole_safe[x]"].route == "examine"


def test_suggest_claims_omits_both_when_nothing_restricted_is_called():
    def plain(x: float) -> float:
        return x * 2.0

    facts = analyze_source(plain)
    names = {c.name for c in suggest_claims(plain, facts=facts)}
    assert not any(n.startswith(("is_builtin_safe", "is_pole_safe")) for n in names)
