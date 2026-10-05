# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_numerically_stable` asks one thing: is the float64 result
accurate? At every point it tries in the working domain it compares the
float result with the exact value of the function's mathematics, within
the claim tolerance (1e-9 plus 1e-7 times the magnitude by default). A
raise or a non-finite result is another family's question (definedness,
overflow) and is no trial here. The claim states it with the helper
`mathema.f.accurate`, so what is executed is what the claim says."""
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def shifted_back(x: float) -> float:
    return (x + 1e16) - 1e16


def doubled(x: float) -> float:
    return 2.0 * x


def reciprocal(x: float) -> float:
    return 1.0 / x


def _stable(fn, domain_text):
    (p,) = check_conjectures(fn, [claim(
        f"let g = mathema.f.accurate, for x in {domain_text}, g(f, x) == 1",
        name="is_numerically_stable")])
    return p


def test_cancellation_falsifies_with_the_exact_and_float_values():
    p = _stable(shifted_back, "[0.1, 0.9]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "exact" in p.counterexample and "float" in p.counterexample, \
        p.counterexample


def test_an_accurate_computation_holds():
    p = _stable(doubled, "[-10, 10]")
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_a_pole_is_not_an_accuracy_failure():
    p = _stable(reciprocal, "[-1, 1]")
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_the_suggestion_states_accuracy():
    (stable,) = [c for c in suggest_claims(doubled)
                 if c.name == "is_numerically_stable"]
    assert stable.funcs.get("g") == "mathema.f.accurate"


def test_the_finiteness_statement_is_judged_as_written():
    (p,) = check_conjectures(reciprocal, [claim(
        "let g = mathema.f.finite_no_error, for x in [-1, 1], g(f, x) == 1",
        name="is_numerically_stable")])
    assert p.verdict == "falsified", (p.verdict, p.note)
