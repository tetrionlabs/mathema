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
def test_an_executed_failure_of_the_positive_proves_the_negation(route):
    # by_text overflows to -inf at x = -1.8e308: f has no value there
    (p,) = check_conjectures(by_text, [claim("not is_defined(f)", route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.counterexample is None
    assert "-1.7976931348623157e+308" in (p.sketch or ""), p.sketch


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_negated_predicate_over_the_whole_function_is_inverted(route):
    # x / y raises at y = 0, so the function is not pole safe
    (p,) = check_conjectures(ratio, [claim("not is_pole_safe(f)", route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.statement.startswith("not "), p.statement
