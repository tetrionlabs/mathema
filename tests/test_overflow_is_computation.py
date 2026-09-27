# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Overflow is a fact about the computation, never about the mathematics.

`math.exp(u)` raises OverflowError once `u` exceeds log of the largest
double (709.782712893384), and `x ** 3` raises it once `|x|` passes the
cube root of that double. Neither changes what the function is over the
reals, so the derive route proves the logistic function's symmetry over
the whole line, and `x ** 3` odd, with infinity as infinity (P1). The
executed side reports the overflow: the proof's `[float]` companion runs
the real code at the domain's corners and is falsified there with a
witness that raises (P5). A declared operational infinity bounds only
that executed side (P6), so it never changes a proof, only how far out
the companion runs."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def grow(x: float) -> float:
    return math.exp(x)


def _pair(fn, law, **kw):
    probes = check_conjectures(fn, [claim(law, name="law", **kw)],
                               float_companions=True)
    by_name = {p.name: p for p in probes}
    return by_name["law"], by_name.get("law[float]")


def _raises_overflow(fn, witness: str) -> bool:
    x = float(witness.split("=", 1)[1])
    try:
        fn(x)
    except OverflowError:
        return True
    return False


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn,law", [
    (logistic, "f(-x) == 1 - f(x)"),
    (logistic, "for x in [-1000, 0], f(x) >= 0"),
    (grow, "for x in [0, 1000], f(x) >= 1"),
])
def test_an_overflowing_exp_is_proven_and_its_computation_falsified(fn, law):
    for route in ("derive", "best"):
        proof, companion = _pair(fn, law, route=route)
        assert proof.verdict == "proven", (route, proof.verdict, proof.note)
        assert proof.route == "derive", proof.route
        assert companion.verdict == "falsified", (route, companion.note)
        assert "raises OverflowError" in companion.sketch, companion.sketch
        assert _raises_overflow(fn, companion.counterexample), \
            companion.counterexample


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn,law", [
    (logistic, "for x in [-700, 700], f(-x) == 1 - f(x)"),
    (grow, "for x in [0, 709], f(x) >= 1"),
])
def test_inside_the_representable_range_the_computation_holds(fn, law):
    proof, companion = _pair(fn, law, route="derive")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion.verdict == "holds", (companion.verdict, companion.note)


@pytest.mark.needs_full_proof_budget
def test_the_computation_fails_just_past_the_last_representable_exponent():
    t = 709.782712893384
    past = math.nextafter(t, math.inf)
    assert math.exp(t) > 0
    with pytest.raises(OverflowError):
        math.exp(past)
    proof, companion = _pair(grow, f"for x in [0, {t!r}], f(x) >= 1",
                             route="derive")
    assert (proof.verdict, companion.verdict) == ("proven", "holds"), \
        companion.note
    proof, companion = _pair(grow, f"for x in [0, {past!r}], f(x) >= 1",
                             route="derive")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion.verdict == "falsified", companion.note
    assert float(companion.counterexample.split("=", 1)[1]) > t, \
        companion.counterexample


def cubed(x: float) -> float:
    return x ** 3


def cubed_int(n: int) -> int:
    return n ** 3


@pytest.mark.needs_full_proof_budget
def test_a_float_power_overflow_is_a_computation_failure():
    for law in ("f(-x) == -f(x)", "f(x) == x * x * x"):
        proof, companion = _pair(cubed, law, route="derive")
        assert proof.verdict == "proven", (law, proof.verdict, proof.note)
        assert proof.condition == "∀ x ∈ ℝ", proof.condition
        assert companion.verdict == "falsified", (law, companion.note)
        assert companion.counterexample in ("x=-1.79769e+308", "x=1.79769e+308"), \
            companion.counterexample
        assert "raises OverflowError" in companion.sketch, companion.sketch
    proof, companion = _pair(cubed, "for x in [-1e100, 1e100], f(-x) == -f(x)",
                             route="derive")
    assert (proof.verdict, companion.verdict) == ("proven", "holds")


def test_an_integer_power_never_overflows():
    (p,) = check_conjectures(cubed_int, [claim("for n in [-10**6, 10**6] ⊂ Z, f(-n) == -f(n)",
                                               route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def squared(x: float) -> float:
    return x ** 2


@pytest.mark.needs_full_proof_budget
def test_an_operational_infinity_bounds_only_the_computation():
    # no operational infinity: the proof is over R and the companion
    # runs the unbounded direction to the float64 maximum, where x**2 raises
    proof, companion = _pair(squared, "f(x) >= 0", route="derive")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert proof.condition == "∀ x ∈ ℝ", proof.condition
    assert companion.verdict == "falsified", companion.note
    # declared at 1e100: the proof is the same proof over R, the
    # statement keeps the binding, and the companion stops at 1e100,
    # where x**2 is finite
    proof, companion = _pair(squared, "f(x) >= 0", route="derive",
                             pseudo_infinity=1e100)
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert proof.condition == "∀ x ∈ ℝ", proof.condition
    assert "let |inf| be 1e+100" in proof.statement, proof.statement
    assert companion.verdict == "holds", companion.note
    assert "run to let |inf| be 1e+100 (claim)" in companion.note, \
        companion.note
    # exp overflows at 709.78, well inside 1e100: the proof stands and
    # the companion is falsified at the declared bound
    proof, companion = _pair(grow, "f(x) >= 0", pseudo_infinity=1e100)
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert proof.condition == "∀ x ∈ ℝ", proof.condition
    assert companion.verdict == "falsified", companion.note
    assert companion.counterexample == "x=1e+100", companion.counterexample


@pytest.mark.needs_full_proof_budget
def test_an_overflow_witness_is_stated_as_a_readable_number():
    proof, companion = _pair(squared, "f(x) >= 0")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion.verdict == "falsified", companion.note
    assert len(companion.counterexample) < 40, companion.counterexample
    assert "e+308" in companion.counterexample, companion.counterexample
