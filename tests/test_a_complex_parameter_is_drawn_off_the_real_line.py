# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated `complex` is drawn from the whole plane: its
real and imaginary parts from the everyday and far ranges a real
number is drawn from, with the plane's far points on both axes as its
corners. A function that only works on the real line is falsified at
a non-real input, on the `is_defined` region probe and on a value
claim alike."""
import pytest

from mathema.conjecture import check_conjectures, claim

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def as_real(z: complex) -> float:
    for part in (z,):
        return float(part)
    return 0.0


def _is_complex_witness(counterexample: str) -> bool:
    return "j" in counterexample.split(":")[0]


def test_is_defined_meets_a_non_real_input():
    (p,) = check_conjectures(as_real, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "TypeError" in p.counterexample, p.counterexample
    assert _is_complex_witness(p.counterexample), p.counterexample


def test_a_value_claim_meets_a_non_real_input():
    (p,) = check_conjectures(as_real, [claim("f(z) == f(z)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "TypeError" in p.counterexample, p.counterexample
    assert _is_complex_witness(p.counterexample), p.counterexample


def magnitude(z: complex) -> float:
    return abs(z)


def test_a_function_defined_on_the_whole_plane_still_holds():
    (p,) = check_conjectures(magnitude, [claim("f(z) >= 0")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


_SEEN: list = []


def recorded(z: complex) -> float:
    _SEEN.append(z)
    return 1.0


def _region_draws(fn) -> list:
    import random

    from mathema.analysis import analyze_source
    from mathema.claim_families import _region_probe
    from mathema.runtime_types import calling
    facts = analyze_source(fn)
    _SEEN.clear()
    _region_probe(calling(fn, facts), facts, claim("is_defined(f)"), {},
                  random.Random(0), 60, "is_defined")
    return list(_SEEN)


def _non_real(values) -> list:
    return [v for v in values if isinstance(v, complex) and v.imag != 0]


def test_the_region_probe_draws_off_the_real_line_and_at_the_far_axes():
    import sys
    seen = _region_draws(recorded)
    assert len(_non_real(seen)) >= 10, seen[:10]
    far = sys.float_info.max / 2
    assert any(isinstance(v, complex) and abs(v.imag) > far
               and v.real == 0 for v in seen), seen[:10]
    assert any(isinstance(v, complex) and abs(v.real) > far
               and v.imag == 0 for v in seen), seen[:10]


def test_a_value_claim_draws_off_the_real_line():
    _SEEN.clear()
    (p,) = check_conjectures(recorded, [claim("f(z) == 1")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)
    assert len(_non_real(_SEEN)) >= 10, _SEEN[:10]


def test_a_real_binding_on_a_complex_parameter_stays_on_the_real_line():
    _SEEN.clear()
    check_conjectures(recorded, [claim("for z in [0, 1], f(z) == 1")])
    assert _SEEN and not _non_real(_SEEN), _non_real(_SEEN)[:3]
