# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function `@enforce_domain()` guards is checked over the domain the
guard admits: the guard declares its domain to every row, the way
`@enforce_dimensions()` declares its shapes, so the engine never draws a
value the guard rejects and no row is falsified by the guard's own
`DomainError`."""
from mathema import check, claims_decorator, enforce_domain
from mathema.types import domain_from_signature


@enforce_domain()
@claims_decorator("for alpha in [0, 1], f(x, alpha) <= max(x, 1)")
def blend(x: float, alpha: float) -> float:
    return alpha * x + (1 - alpha) * 1.0


def _by_name(record):
    return {p.name: p for p in record.probes}


def test_the_guarded_domain_is_the_parent_domain():
    parent = domain_from_signature(blend)
    assert set(parent) == {"alpha"}
    assert domain_from_signature(blend, guards=False) == {}


def test_no_row_is_falsified_by_the_guard_itself():
    rows = check(blend).probes
    raised = [p.name for p in rows
              if "DomainError" in (p.note or "")
              or "DomainError" in str(p.counterexample or "")]
    assert raised == []


def test_the_standard_rows_hold_inside_the_guarded_domain():
    rows = _by_name(check(blend))
    assert rows["is_numerically_stable"].verdict == "holds"
    assert rows["is_representation_safe[alpha]"].verdict == "holds"
    assert rows["is_representation_safe[x]"].verdict == "holds"


def test_the_exclusion_row_is_still_proven_by_construction():
    rows = _by_name(check(blend))
    assert rows["excluded_outside_domain[alpha]"].verdict == "proven"


@enforce_domain()
@claims_decorator("for x in [0, 1], f(x) >= 1")
def reciprocal(x: float) -> float:
    return 1.0 / x


def test_a_failure_inside_the_guarded_domain_still_falsifies():
    # zero is inside the guarded domain and the body divides by it: the
    # guard admits the draw, so the row reports the function's own raise
    row = _by_name(check(reciprocal))["is_numerically_stable"]
    assert row.verdict == "falsified"
    assert str(row.counterexample) == "x = 0 raised ZeroDivisionError"


@enforce_domain(domain={"weights": (0, 1)})
def mean_weight(weights: list) -> float:
    """The mean of portfolio weights, each guarded to [0, 1]."""
    return sum(weights) / len(weights)


def test_a_sample_whose_transformed_argument_leaves_the_domain_is_outside_the_claim():
    # scale_equivariant calls f at c * weights and translation_equivariant
    # at weights + c; a sample that takes the argument out of [0, 1] is
    # outside the claim, skipped, and the guard's DomainError there is
    # not a counterexample; the samples that stay inside decide
    rows = _by_name(check(mean_weight))
    for name in ("scale_equivariant", "translation_equivariant"):
        row = rows[name]
        assert row.verdict == "holds", (name, row.verdict, row.counterexample)


@enforce_domain()
@claims_decorator("for x in [0, 1], f(x) >= 0")
def unit_root(x: float) -> float:
    import math
    return math.sqrt(x)


def test_a_claim_whose_every_sample_leaves_the_domain_is_skipped_with_the_reason():
    from mathema.conjecture import claim
    p = _by_name(check(unit_root, claims=[claim(
        "for x in [0, 1], f(x + 2) >= 0", name="shifted", route="probe")]))[
        "shifted"]
    assert p.verdict == "skipped", (p.verdict, p.counterexample)
    assert "left the declared domain" in (p.note or ""), p.note


@enforce_domain()
@claims_decorator("for x in [0, 1], f(x) >= 0")
def half_capped(x: float) -> float:
    if x > 0.4:
        raise ValueError("above the cap")
    return x


def test_a_raise_at_a_transformed_argument_inside_the_domain_still_falsifies():
    from mathema.conjecture import claim
    p = _by_name(check(half_capped, claims=[claim(
        "for x in [0, 0.25], f(2 * x) >= 0", name="doubled", route="probe")]))[
        "doubled"]
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ValueError" in str(p.counterexample), p.counterexample
