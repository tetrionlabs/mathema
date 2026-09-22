# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/diagnostics.py's domain_hazards() and operations_of_interest():
pole/singularity detection over a lifted expression's own denominators,
and a raw statistical bag-of-operation-kind count."""
import sympy

from mathema.diagnostics import domain_hazards, operations_of_interest

r, c1, x = sympy.symbols("r c1 x")


def _dummy_fn():
    """A real function with a real source file, for _source_file()."""


def test_domain_hazards_finds_a_pole_with_no_declared_domain():
    # 1/(1+r); the exact shape npv_two_period hit live in this
    # session's own stress-test batch (an implicit ZeroDivisionError
    # at r=-1, with no explicit guard).
    expr = c1 / (1 + r)
    hazards = domain_hazards(_dummy_fn, expr)
    assert len(hazards) == 1
    hazard = hazards[0]
    assert hazard["kind"] == "pole"
    assert hazard["variable"] == "r"
    assert hazard["at"] == "-1"
    assert hazard["domain"] == "assumed (-inf, inf), not declared"


def test_domain_hazards_labels_a_declared_domain_explicitly():
    expr = c1 / (1 + r)
    hazards = domain_hazards(_dummy_fn, expr, declared_domain={"r": "(-0.9, 0.9)"})
    assert hazards[0]["domain"] == "declared: (-0.9, 0.9)"


def test_domain_hazards_finds_none_for_an_expression_with_no_division():
    expr = r ** 2 + 2 * r + 1
    assert domain_hazards(_dummy_fn, expr) == []


def test_domain_hazards_deduplicates_the_same_denominator_appearing_twice():
    expr = 1 / (1 - r) + 2 / (1 - r)
    hazards = domain_hazards(_dummy_fn, expr)
    assert len(hazards) == 1
    assert hazards[0]["at"] == "1"


def test_domain_hazards_finds_multiple_distinct_poles():
    expr = 1 / (1 + r) + 1 / (1 - r)
    hazards = domain_hazards(_dummy_fn, expr)
    found = {h["at"] for h in hazards}
    assert found == {"-1", "1"}


def test_operations_of_interest_counts_each_kind():
    expr = sympy.log(x) + sympy.sin(x) + 1 / (x - 1) + sympy.Piecewise((x, x > 0), (0, True))
    counts = operations_of_interest(expr)
    assert counts["negative_or_fractional_powers"] == 1
    assert counts["log_or_exp"] == 1
    assert counts["trig"] == 1
    assert counts["comparisons"] == 1
    assert counts["piecewise_branches"] == 2


def test_operations_of_interest_all_zero_for_a_plain_polynomial():
    counts = operations_of_interest(x ** 2 + 2 * x + 1)
    assert all(v == 0 for v in counts.values())
