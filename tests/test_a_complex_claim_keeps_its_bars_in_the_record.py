# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A name that ranges over the complex numbers (a parameter annotated
`complex`, or one the claim binds to C) is read as a complex number when
the claim is rendered and fingerprinted, so `abs(z) ** 2` is recorded as
written: over C it is not `z ** 2`, and the two claims have different
texts and identities. A claim over real parameters renders and hashes
exactly as before."""
from mathema.conjecture import check_conjectures, claim
from mathema.sync import _identity


def magnitude_squared(z: complex) -> float:
    return abs(z) ** 2


def real_square(x: float) -> float:
    return x * x


def unannotated(z):
    return abs(z) ** 2


def _statement(fn, law):
    (p, *_rest) = check_conjectures(fn, [claim(law)])
    return p.statement


def test_the_bars_of_a_complex_parameter_stay_in_the_statement():
    assert _statement(magnitude_squared, "f(z) == abs(z) ** 2") == "f(z) = |z|^2"
    assert _statement(magnitude_squared, "f(z) == z ** 2") == "f(z) = z^2"


def test_a_complex_parameter_keeps_two_claims_apart():
    bars = _identity("f(z) == abs(z) ** 2", fn=magnitude_squared)
    square = _identity("f(z) == z ** 2", fn=magnitude_squared)
    assert bars != square


def test_a_binding_to_c_keeps_the_bars_without_an_annotation():
    bars = _identity("for z in C, f(z) == abs(z) ** 2", fn=unannotated)
    square = _identity("for z in C, f(z) == z ** 2", fn=unannotated)
    assert bars != square


def test_a_real_parameter_renders_as_before():
    assert _statement(real_square, "f(x) == abs(x) ** 2") == "f(x) = x^2"
    assert _identity("f(x) == abs(x) ** 2", fn=real_square) \
        == _identity("f(x) == x ** 2", fn=real_square)
