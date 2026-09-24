# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A real claim reads its function as real-valued. A complex result is
then no value at all, the same as a raise: the claim is falsified,
with the executed point that returned it as the witness, on the probe
and the derive routes alike. A function annotated `complex`, or a
claim quantified over C, reads a complex result as an ordinary value."""
from mathema.conjecture import check_conjectures, claim


def half_power(x: float) -> float:
    return x ** 0.5


def untyped_half_power(x):
    return x ** 0.5


def rotate(x: float) -> complex:
    return x * 1j


def rotate_plane(z: complex) -> complex:
    return z * 1j


def _v(fn, law, route):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def test_a_complex_result_falsifies_an_ordering_on_every_route():
    for route in ("probe", "derive", "best"):
        p = _v(half_power, "for x in [-4, 4], f(x) >= 0", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert "complex" in (p.counterexample or ""), (route, p.counterexample)


def test_a_complex_result_falsifies_an_equality_that_compares_it_to_itself():
    p = _v(half_power, "for x in [-4, 4], f(x) == f(x)", "probe")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "complex" in p.counterexample


def test_an_unannotated_function_under_a_real_claim_counts_too():
    p = _v(untyped_half_power, "for x in [-4, 4], f(x) * f(x) == x", "best")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "complex" in p.counterexample


def test_the_nonnegative_region_still_proves():
    assert _v(half_power, "for x in [0, 4], f(x) >= 0", "best").verdict \
        == "proven"


def test_a_function_annotated_complex_is_unaffected():
    p = _v(rotate, "for x in [1, 5], f(x) == x * 1j", "probe")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_claim_over_the_complex_plane_is_unaffected():
    p = _v(rotate_plane, "for z in C, f(z) == z * 1j", "probe")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_derive_disproof_reproduces_on_a_complex_result(monkeypatch):
    from mathema.symbolic import _proof_support as ps

    def disproof_at_minus_four(lhs, rhs, diff, relation, domain,
                               bound_context, params, tolerance=1e-9):
        return ps.ProofResult("disproven", sketch="negative base",
                              witness={"x": -4.0}, disproof_hint=None)

    monkeypatch.setitem(ps._RELATION_DECIDERS, "==", disproof_at_minus_four)
    p = _v(half_power, "for x in [-4, 4], f(x) == f(x)", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "reproduced"
