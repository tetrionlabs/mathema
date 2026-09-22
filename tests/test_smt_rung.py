# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The nlsat rung (mathema[smt]): polynomial sign questions the rest of
the ladder cannot settle decided exactly by z3's nonlinear real
arithmetic, proof by unsat with the oracle named, disproof only after
exact sympy re-confirmation of the model, transcendentals declining to
the later rungs, and the ladder running unchanged when the extra is
absent."""
import pytest
import sympy

z3 = pytest.importorskip("z3")

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.symbolic._extensive import extensive_ladder  # noqa: E402
from mathema.symbolic._smt import nlsat_decide  # noqa: E402


def _abc():
    return [sympy.Symbol(n, nonnegative=True) for n in "abc"]


def _schur(a, b, c):
    return a*(a-b)*(a-c) + b*(b-a)*(b-c) + c*(c-a)*(c-b)


def test_schur_inequality_proves_via_the_rung():
    # attained zeros along a=b=c defeat interval refinement forever;
    # nlsat decides the whole box exactly
    a, b, c = _abc()
    box = {"a": (0.0, 10.0), "b": (0.0, 10.0), "c": (0.0, 10.0)}
    result, attempted = extensive_ladder(
        _schur(a, b, c), sympy.S.Zero, ">=", box, None,
        {"a": a, "b": b, "c": c})
    assert result is not None and result.status == "proven", attempted
    assert result.meta.get("mathema.derive_route") == "smt_nlsat"
    assert "nlsat" in result.sketch and "z3" in result.sketch


def test_false_tightening_disproves_with_an_exact_witness():
    a, b, c = _abc()
    box = {"a": (0.0, 10.0), "b": (0.0, 10.0), "c": (0.0, 10.0)}
    result, _ = extensive_ladder(
        _schur(a, b, c) - sympy.Rational(1, 100), sympy.S.Zero, ">=",
        box, None, {"a": a, "b": b, "c": c})
    assert result is not None and result.status == "disproven"
    assert result.counterexample
    # the witness was re-established by exact sympy arithmetic before
    # being reported (the sketch says so)
    assert "exact arithmetic" in result.sketch


def test_transcendentals_decline_to_later_rungs():
    x = sympy.Symbol("x", real=True)
    assert nlsat_decide(sympy.exp(x) - x, ">=", {"x": (-5.0, 5.0)},
                        {"x": x}) is None


def test_radicals_encode_through_auxiliary_variables():
    # sqrt(x) <= (x + 1)/2 (AM-GM with 1): equality attained at x = 1,
    # so refinement cannot close it; the auxiliary y^2 = x encoding can
    x = sympy.Symbol("x", nonnegative=True)
    result = nlsat_decide((x + 1)/2 - sympy.sqrt(x), ">=",
                          {"x": (0.0, 100.0)}, {"x": x})
    assert result is not None and result.status == "proven"


def test_assumed_context_constrains_the_query():
    # constrained AM-GM: under a + b == 2, ab <= 1, the equality
    # surface is the bound context, not the box
    a = sympy.Symbol("a", nonnegative=True)
    b = sympy.Symbol("b", nonnegative=True)
    result = nlsat_decide(
        sympy.Integer(1) - a*b, ">=",
        {"a": (0.0, 2.0), "b": (0.0, 2.0)}, {"a": a, "b": b},
        bound_context=sympy.Eq(a + b, 2))
    assert result is not None and result.status == "proven"


def test_claim_level_schur_proves_under_extensive():
    # at claim level the WLOG gap-substitution rescue happens to win
    # Schur before the ladder runs, proven either way; the mechanism
    # pin lives on the Motzkin case below, which no earlier machinery
    # settles
    def schur_expression(a: float, b: float, c: float) -> float:
        return (a*(a-b)*(a-c) + b*(b-a)*(b-c) + c*(c-a)*(c-b))

    (p,) = check_conjectures(schur_expression, [claim(
        "for a in [0,10], b in [0,10], c in [0,10], f(a,b,c) >= 0",
        route="derive")], extensive=True)
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_claim_level_motzkin_proves_via_nlsat():
    # the Motzkin polynomial: nonnegative everywhere yet famously NOT a
    # sum of squares, with attained zeros at |x| = |y| = 1, beyond
    # the fast rescues, gap substitution, and interval refinement alike
    def motzkin(x: float, y: float) -> float:
        return x**4 * y**2 + x**2 * y**4 - 3 * x**2 * y**2 + 1

    (p,) = check_conjectures(motzkin, [claim(
        "for x in [-10,10], y in [-10,10], f(x,y) >= 0",
        route="derive")], extensive=True)
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "nlsat" in (p.sketch or "")


def test_ladder_runs_unchanged_without_the_extra(monkeypatch):
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    a, b, c = _abc()
    result, attempted = extensive_ladder(
        _schur(a, b, c), sympy.S.Zero, ">=",
        {"a": (0.0, 10.0), "b": (0.0, 10.0), "c": (0.0, 10.0)}, None,
        {"a": a, "b": b, "c": c})
    assert "nlsat quantifier elimination" not in attempted


def test_root_sum_hang_shapes_decline_promptly():
    # multi-term root-sum shapes can run z3's algebraic-number kernel
    # far past the wall-clock timeout (it is not polled there); the
    # deterministic rlimit cap must turn them into a prompt decline.
    # IMO 2001 Problem 2's shape: a/sqrt(a^2+8bc) + ... >= 1
    import time
    a, b, c = [sympy.Symbol(n, positive=True) for n in "abc"]
    expr = (a / sympy.sqrt(a**2 + 8*b*c)
            + b / sympy.sqrt(b**2 + 8*c*a)
            + c / sympy.sqrt(c**2 + 8*a*b) - 1)
    t0 = time.time()
    result = nlsat_decide(expr, ">=", {n: (0.1, 10.0) for n in "abc"},
                          {"a": a, "b": b, "c": c})
    elapsed = time.time() - t0
    assert elapsed < 10, f"took {elapsed:.1f}s, the rlimit cap failed"
    assert result is None or result.status in ("proven", "disproven")
