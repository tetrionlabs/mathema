# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Canonical domain narrowing at resolve time: an integer-typed domain
whose one piece is the whole nonnegative ray IS the natural numbers,
so it resolves to N, same set, canonical name, with the collapse
rendered explicitly in the record's note, never silently. Bounded or
shifted ranges are already tight and stay as declared."""
from mathema.claims import check_conjectures, claim
from mathema.domain import Domain, canonical_bound, parse_binding, render_domain_bound


def double(n: int) -> int:
    return 2 * n


def test_nonnegative_integer_ray_collapses_to_n():
    _, bound = parse_binding("n in [0, oo]:int")
    canonical, declared = canonical_bound(bound)
    assert isinstance(canonical, Domain) and canonical.base_type == "N"
    assert canonical.pieces == ()
    assert declared is not None and "int" in declared


def test_bounded_and_shifted_ranges_stay_as_declared():
    for spec in ["[0, 10]:int", "[1, oo]:int", "[0, oo]", "[0.5, oo]:int"]:
        _, bound = parse_binding(f"n in {spec}")
        canonical, declared = canonical_bound(bound)
        assert declared is None, spec
        assert canonical is bound, spec


def test_collapse_is_rendered_explicitly_in_the_record():
    (p,) = check_conjectures(
        double, [claim("for n in [0, oo]:int, f(n) >= 0", route="derive")])
    assert p.verdict == "proven"
    assert "canonically N" in p.note
    assert "declared" in p.note
    assert "ℕ" in p.condition


def test_infinite_integer_bound_renders_without_crashing():
    # regression: render_domain_bound raised OverflowError ("cannot
    # convert float infinity to integer") on an int-typed infinite ray
    _, bound = parse_binding("n in [0, oo]:int")
    assert "int" in render_domain_bound(bound)
