# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Defensive hardening ahead of the complex-plane work: every site
that used to treat an unknown domain type or a complex value as
silently real must now refuse loudly. An unknown base type raises
`InvalidDomain` from every projection; a genuinely imaginary value is
a member of no R/Z/N domain; ordering over non-orderable values skips
with a clear note on both routes."""
import pytest
import sympy

from mathema.authoring import DomainError, enforce_domain
from mathema.conjecture import check_conjectures, claim
from mathema.domain import (
    Domain, InvalidDomain, Interval, bound_assumptions, bound_to_sympy_set,
    domain_contains,
)


def test_unknown_base_type_never_projects_as_real():
    stranger = Domain(base_type="Q", explicit_type=True)
    with pytest.raises(InvalidDomain, match="unknown domain base type"):
        bound_to_sympy_set(stranger)
    with pytest.raises(InvalidDomain, match="unknown domain base type"):
        bound_assumptions(stranger)
    with pytest.raises(InvalidDomain, match="unknown domain base type"):
        domain_contains(1.0, stranger)
    with pytest.raises(InvalidDomain, match="unknown domain base type"):
        bound_to_sympy_set("H")


def test_known_base_types_still_project():
    assert bound_to_sympy_set("Z") is sympy.S.Integers
    assert bound_to_sympy_set(Domain(base_type="R")) is sympy.S.Reals
    assert bound_assumptions("Z") == {"integer": True, "real": True}
    assert domain_contains(3, "Z")


def test_imaginary_values_belong_to_no_real_domain():
    assert not domain_contains(1 + 2j, (0.0, 10.0))
    assert not domain_contains(2j, "Z")
    assert not domain_contains(1j, Domain(base_type="R"))
    # a zero-imaginary complex is the real number it equals
    assert domain_contains(3 + 0j, (0.0, 10.0))
    assert not domain_contains(11 + 0j, (0.0, 10.0))


def test_unknown_domain_type_declines_the_proof_not_the_process():
    def double(x: float) -> float:
        return 2.0 * x

    stranger = Domain(base_type="Q", explicit_type=True)
    (p,) = check_conjectures(double, [claim("f(x) == 2*x", route="derive")],
                             domain={"x": stranger})
    assert p.verdict in ("unknown", "skipped")
    assert "not projectable" in (p.sketch or "") or "unknown domain base type" in (p.note or "")


def test_enforce_domain_flags_a_complex_argument():
    @enforce_domain(domain={"x": Interval(0.0, 10.0)})
    def half(x: float) -> float:
        return x / 2.0

    assert half(4.0) == 2.0
    assert half(4 + 0j) == 2 + 0j   # zero-imaginary reads as its real value
    with pytest.raises(DomainError):
        half(3 + 2j)


def test_probe_ordering_over_complex_returns_skips_cleanly():
    def rotate(x: float) -> complex:
        return x * 1j

    (p,) = check_conjectures(rotate, [claim("for x in [1, 5], f(x) <= 5")])
    # best-route cascade: derive declines (complex return), and the
    # probe's ordering-over-complex refusal is carried in the trail
    assert p.verdict in ("skipped", "unknown")
    assert "isn't meaningful" in p.note
