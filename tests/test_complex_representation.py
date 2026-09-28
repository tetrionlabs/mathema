# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claims over the complex plane, computed in complex128: the companion
of a claim over C runs in the complex128 number representation and is named
`<claim>[complex]`; equality and closeness adjudicate over C on the
probe route (`~=` as `abs(a - b)` within the tolerance), while ordering
stays refused; a NaN or an infinity in either component is no value."""
import math
import random

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def csqrt(z: complex) -> complex:
    return np.sqrt(z)


def rsq(x: float) -> float:
    return x * x


def _rows(fn, text, name="sq", **kw):
    import mathema
    rec = mathema.check(fn, claims=[claim(text, name=name, **kw)])
    return {p.name: p for p in rec.probes}


def test_the_complex128_number_representation():
    import sys

    from mathema.representations import (PY_COMPLEX128, PY_FLOAT64,
                                         PYTHON_PROFILES)
    assert PY_COMPLEX128.max_magnitude == sys.float_info.max
    assert PY_COMPLEX128.overflow == "inf"
    assert PY_COMPLEX128.tag != PY_FLOAT64.tag
    assert PYTHON_PROFILES["complex"] is PY_COMPLEX128


def test_a_claim_over_c_spawns_a_complex_companion():
    from mathema.gates import companion_descriptor
    rows = _rows(csqrt, "for z in C, f(z)*f(z) == z")
    assert rows["sq"].verdict == "proven"
    assert "sq[float]" not in rows
    comp = rows["sq[complex]"]
    assert companion_descriptor(comp.name) == ("complex",)
    assert comp.meta.get("mathema.companion_of") == "sq"
    assert "the computation of sq in complex128" in comp.note, comp.note
    assert comp.verdict == "holds", (comp.counterexample, comp.note)


def test_a_claim_over_r_keeps_the_float_companion():
    rows = _rows(rsq, "for x in [-3, 3], f(x) >= 0")
    assert "sq[float]" in rows and "sq[complex]" not in rows
    assert "in float64" in rows["sq[float]"].note


def test_the_c_sampler_draws_both_components_far_as_well():
    from mathema.probing import _sample_bare_named_set
    rng = random.Random(7)
    draws = [_sample_bare_named_set(rng, "C") for _ in range(4000)]
    assert all(isinstance(z, complex) for z in draws)
    assert any(abs(z.real) > 1e100 for z in draws)
    assert any(abs(z.imag) > 1e100 for z in draws)
    everyday = [z for z in draws if abs(z.real) <= 10 and abs(z.imag) <= 10]
    assert len(everyday) > 0.7 * len(draws)


def test_no_value_reads_either_component():
    from mathema.probing import holds_inf, holds_nan, same_infinity
    inf, nan = math.inf, math.nan
    assert holds_nan(complex(1.0, nan)) and holds_nan(complex(nan, 0.0))
    assert holds_nan(np.complex128(complex(0.0, nan)))
    assert not holds_nan(1 + 2j)
    assert holds_inf(complex(1.0, -inf)) == -1
    assert holds_inf(np.complex128(complex(inf, 0.0))) == 1
    assert not holds_inf(3 - 4j)
    assert same_infinity(complex(inf, 0.0), complex(inf, 0.0))
    assert not same_infinity(complex(inf, 0.0), complex(inf, 1.0))
    assert not same_infinity(complex(inf, nan), complex(inf, nan))
    assert not same_infinity(1 + 1j, 1 + 1j)


def test_closeness_over_c_holds_on_the_probe_route():
    (p,) = check_conjectures(csqrt, [claim("for z in C, f(z)*f(z) ~= z",
                                           route="probe")])
    assert p.verdict == "holds", (p.note, p.counterexample)
    p = _rows(np.sqrt, "for x in C, f(x)*f(x) ~= x")["sq"]
    assert p.verdict == "holds", (p.note, p.counterexample)
    assert p.route.startswith("probe"), p.route


def test_exact_equality_over_c_compares_on_the_probe_route():
    def conj(z: complex) -> complex:
        return np.conj(z)

    (p,) = check_conjectures(conj, [claim("for z in C, f(f(z)) == z",
                                          route="probe")])
    assert p.verdict == "holds", (p.note, p.counterexample)
    (p,) = check_conjectures(conj, [claim("for z in C, f(z) == z",
                                          route="probe")])
    assert p.verdict == "falsified"


def test_ordering_over_c_stays_refused_and_says_ordering():
    (p,) = check_conjectures(csqrt, [claim("for z in C, f(z) < z",
                                           route="probe")])
    assert p.verdict == "skipped"
    assert "ordering" in p.note, p.note


def test_a_nan_component_is_no_value_on_the_probe_route():
    def half_nan(z: complex) -> complex:
        return complex(z.real, math.nan) if abs(z) > 0.5 else z

    (p,) = check_conjectures(half_nan, [claim("for z in C, f(z) ~= z",
                                              route="probe")])
    assert p.verdict == "falsified"


def test_scalar_relation_over_complex_numpy_values():
    from mathema.probing import relation_holds_elementwise
    a, b = np.complex128(1 + 1j), np.complex128(1 + 1j + 1e-12)
    assert relation_holds_elementwise(a, b, "~=", 1e-9) is True
    assert relation_holds_elementwise(a, np.complex128(2j), "==", 1e-9) \
        is False
    assert relation_holds_elementwise(a, b, "<", 1e-9) is None
    arr = np.array([1 + 1j, 2 - 1j])
    assert relation_holds_elementwise(arr, arr.copy(), "==", 1e-9) is True
    assert relation_holds_elementwise(arr, arr, "<=", 1e-9) is None
