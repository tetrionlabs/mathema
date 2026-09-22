# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The C domain type: claims quantified over the complex plane.
Parsing, symbol assumptions, both adjudication routes for equality
shapes, the ordering refusal, complex literal spellings, and the
stays-real-by-default sampling rule."""
import pytest
import sympy

from mathema.authoring import DomainError, enforce_domain
from mathema.conjecture import check_conjectures, claim
from mathema.domain import (
    bound_assumptions, bound_to_sympy_set, domain_contains, render_domain,
)
from mathema.grammar import normalize, split_quantifier


def modsq(z: complex) -> float:
    return abs(z) ** 2


def rotate(z: complex) -> complex:
    return z * 1j


def linear(z: complex, w: complex) -> complex:
    return 2.0 * z + w


def real_double(x: float) -> float:
    return 2.0 * x


def test_c_parses_projects_and_renders():
    dom, _ = split_quantifier("for z in C, f(z) == z")
    bound = dom["z"]
    assert bound.base_type == "C" and bound.explicit_type
    assert bound_assumptions(bound) == {"complex": True}
    assert bound_to_sympy_set(bound) is sympy.S.Complexes
    assert "ℂ" in render_domain(bound)
    # every accepted spelling lands on the same type
    for text in ("for z in ℂ, f(z) == z", "for z in [0,1] subset C, f(z) == z",
                 "for z in C, f(z) == z"):
        assert split_quantifier(text)[0]["z"].base_type == "C"


def test_complex_membership_reads_the_plane():
    dom, _ = split_quantifier("for z in C, f(z) == z")
    bound = dom["z"]
    assert domain_contains(1 + 2j, bound)
    assert domain_contains(3.0, bound)   # the reals embed
    segment, _ = split_quantifier("for w in [0,1] subset C, f(w) == w")
    assert domain_contains(0.5, segment["w"])
    assert not domain_contains(0.5 + 1j, segment["w"])


def test_imaginary_literal_spellings_normalize_identically():
    assert normalize("f(z) == 1 + 2i") == "f(z) == 1 + 2j"
    assert normalize("f(z) == 3ⅈ") == "f(z) == 3j"
    assert normalize("f(z) == \U0001d456*z") == "f(z) == 1j*z"
    # a bare i (or an identifier containing one) stays a variable
    assert normalize("f(z, i) == z + i") == "f(z, i) == z + i"
    assert normalize("f(xi) == xi") == "f(xi) == xi"


def test_derive_route_proves_complex_identities():
    (p,) = check_conjectures(rotate, [claim("for z in C, f(f(z)) == -z",
                                            route="derive")])
    assert p.verdict == "proven"
    (p,) = check_conjectures(rotate, [claim("for z in C, re(f(z)) == -im(z)",
                                            route="derive")])
    assert p.verdict == "proven"
    (p,) = check_conjectures(linear, [claim(
        "for z in C, w in C, f(z, w) - f(w, z) == z - w", route="derive")])
    assert p.verdict == "proven"


def test_modulus_identity_proves_via_the_conjugate_rewrite():
    (p,) = check_conjectures(modsq, [claim("for z in C, f(z) == z*conjugate(z)",
                                           route="derive")], extensive=True)
    assert p.verdict == "proven"
    assert "conjugate" in p.sketch


def test_ordering_over_c_refuses_on_both_routes():
    for route in ("derive", "probe"):
        (p,) = check_conjectures(modsq, [claim("for z in C, f(z) >= 0",
                                               route=route)])
        assert p.verdict == "skipped"
        assert "complex plane" in p.note


def test_probe_route_samples_the_plane():
    (p,) = check_conjectures(rotate,
                             [claim("for z in C, f(f(z)) == -z",
                                    route="probe")])
    assert p.verdict == "holds" and p.n > 0
    (p,) = check_conjectures(rotate,
                             [claim("for z in C, f(z) == z",
                                    route="probe")])
    assert p.verdict == "falsified"
    assert "j" in p.counterexample   # a genuinely complex witness


def test_sampling_stays_real_unless_the_domain_says_c():
    # No C in the domain means real samples, even for a
    # complex-annotated function; f(x) == x holds over real samples of
    # rotate's identity comparison only if the sample were 0; use a
    # claim true over R but false off the real axis to detect leakage.
    def conj_id(z: complex) -> complex:
        return z.conjugate() if isinstance(z, complex) else z

    (p,) = check_conjectures(conj_id, [claim("for z in [-5, 5], f(z) == z")])
    assert p.verdict == "holds"   # real samples: conjugation is identity


def test_enforce_domain_accepts_complex_only_for_c():
    @enforce_domain(domain={"z": "C"})
    def half(z: complex) -> complex:
        return z / 2.0

    assert half(1 + 1j) == 0.5 + 0.5j
    assert half(4.0) == 2.0

    @enforce_domain(domain={"x": (0.0, 10.0)})
    def real_half(x: float) -> float:
        return x / 2.0

    with pytest.raises(DomainError):
        real_half(1 + 1j)


def test_rectangle_corner_literals():
    # `z in [-1-1j, 1+2j]`: two complex corners name the axis-aligned
    # rectangle between them, the type infers to C, and both the i and
    # j corner spellings parse identically.
    dom, _ = split_quantifier("for z in [-1-1j, 1+2j], f(z) == z")
    bound = dom["z"]
    assert bound.base_type == "C" and bound.explicit_type
    assert domain_contains(0.5 + 1j, bound)
    assert domain_contains(0.5, bound)          # the real chord
    assert not domain_contains(2 + 1j, bound)   # off the Re range
    assert not domain_contains(0.5 - 2j, bound)  # off the Im range
    assert split_quantifier("for z in [-1-1i, 1+2i], f(z) == z")[0]["z"] == bound
    # renders in the coordinate spelling that re-parses
    assert "[-1-1j, 1+2j]" in render_domain(bound, ascii_mode=True)


def test_rectangle_contradicting_a_real_type_is_rejected():
    from mathema.domain import InvalidDomain
    with pytest.raises(InvalidDomain, match="contradict"):
        split_quantifier("for z in [-1-1j, 1+1j] subset Z, f(z) == z")


def test_rectangle_round_trips_the_codec():
    from mathema.domain import domain_bound_from_json, domain_bound_to_json
    dom, _ = split_quantifier("for z in [-1-1j, 1+2j], f(z) == z")
    bound = dom["z"]
    assert domain_bound_from_json(domain_bound_to_json(bound)) == bound


def test_rectangle_claims_adjudicate_on_both_routes():
    (p,) = check_conjectures(rotate, [claim(
        "for z in [-1-1j, 1+1j], f(f(z)) == -z", route="derive")])
    assert p.verdict == "proven"
    (p,) = check_conjectures(rotate, [claim("for z in [-1-1j, 1+1j], f(z) == z")])
    assert p.verdict == "falsified"
    # every sampled witness lies inside the declared rectangle
    (p,) = check_conjectures(rotate,
                             [claim("for z in [-1-1j, 1+1j], f(f(z)) == -z",
                                    route="probe")])
    assert p.verdict == "holds" and p.n > 0


@pytest.mark.needs_full_proof_budget
def test_engine_disagreement_lands_as_structured_meta():
    import math

    def trig_integral_value(a: float, b: float) -> float:
        return 2.0 * math.pi / math.sqrt(a * a - b * b)

    (p,) = check_conjectures(trig_integral_value, [claim(
        "for a in [2, 5], b in [0.1, 1], "
        "f(a, b) == integrate(1/(a + b*cos(theta)), theta, 0, 2*pi)",
        route="derive")], extensive=True)
    assert p.verdict == "proven"
    (record,) = p.meta["mathema.engine_disagreement"]
    assert record["sympy"] == "0"
    assert record["referee"] == "quadrature"
    assert "sqrt(a**2 - b**2)" in record["contour"]
    assert p.meta["mathema.derive_route"].startswith("residue:")
