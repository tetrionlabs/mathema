# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A negated predicate (`not is_defined(f)`) states that the positive
fails somewhere. A point the code is run at where the positive fails is
a witness for the negation, which is then proven; a positive that holds
at every sampled point says nothing about whether it fails elsewhere,
so the negation stays unknown; a proven positive falsifies the
negation, the proof its witness. This holds on every route, and for a
predicate over the whole function as for one over a parameter."""
import pytest

from mathema.conjecture import check_conjectures, claim


def by_text(x: float) -> float:
    # defined at every x in [0, 1]; no symbolic or exact reading
    return float(str(x)) * 2.0


def total(x: float) -> float:
    return 2.0 * x + 1.0


def recip(x: float) -> float:
    return 1.0 / x


def ratio(x: float, y: float) -> float:
    return x / y


@pytest.mark.parametrize("route", ["probe", "best", "derive"])
@pytest.mark.parametrize("fn, text", [
    (by_text, "for x in [0, 1], not is_defined(f)"),
    (total, "for x in [0, 1], not is_finite(f(x))"),
])
def test_a_sampled_pass_of_the_positive_leaves_the_negation_open(fn, text,
                                                                 route):
    # f has a value, and a finite one, at every x in [0, 1], so each
    # negation is false; sampling cannot show that, and never holds it
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    assert p.verdict == "unknown", (route, p.verdict, p.route, p.note)


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_failure_of_the_positive_proves_the_negation(route):
    # 1/x has no value at x = 0, which [-1, 1] contains
    (p,) = check_conjectures(recip, [claim("for x in [-1, 1], not is_defined(f)",
                                           route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.counterexample is None
    assert "x = 0" in (p.sketch or ""), p.sketch


@pytest.mark.parametrize("route", ["probe", "best", "derive"])
def test_an_overflow_is_no_failure_of_definedness(route):
    # 2x has a value at every real x; the float run of float(str(x)) * 2.0
    # overflows to -inf at x = -1.8e308, a fact about the computation
    # (is_computation_safe), not a point where f has no value: the
    # positive is never falsified there, and the negation stays open
    (p,) = check_conjectures(by_text, [claim("is_defined(f)", route=route)])
    assert p.verdict != "falsified", (route, p.verdict, p.counterexample)
    assert "overflow" in (p.note or ""), p.note
    (q,) = check_conjectures(by_text, [claim("not is_defined(f)", route=route)])
    assert q.verdict == "unknown", (route, q.verdict, q.sketch, q.note)
    assert "overflow" in (q.note or ""), q.note


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_negated_predicate_over_the_whole_function_is_inverted(route):
    # x / y raises at y = 0, so the function is not pole safe
    (p,) = check_conjectures(ratio, [claim("not is_pole_safe(f)", route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.statement.startswith("not "), p.statement
