# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated `complex` is read as a complex number on every
route. Python's real-only operations (`float()`, the `math` module, an
ordering comparison, `min`/`max`, `%` and `//`) raise TypeError on a
complex value, so derive never reads them as total over a complex
argument: it declines, and the probe meets the raise at a non-real
input. The `cmath` and numpy elementary functions and `abs` are defined
on the whole plane and still derive. A claim that binds no domain for
the parameter ranges over C, stated in the note, and its computation
companion runs in complex128."""
import cmath
import math

import pytest

from mathema.analysis import effective_facts
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic import lift

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def as_real(z: complex) -> float:
    return float(z)


def math_exp(z: complex) -> float:
    return math.exp(z)


def ordered(z: complex) -> float:
    return 1.0 if z < 1 else 2.0


def floored(z: complex) -> int:
    return math.floor(z)


def smaller(z: complex) -> float:
    return min(z, 1.0)


def remainder(z: complex) -> float:
    return z % 2


def cancelled(z: complex) -> float:
    return float(z - z)


def _real_helper(t: float) -> float:
    return float(t)


def through_a_real_helper(z: complex) -> float:
    return _real_helper(z)


def principal_root(z: complex) -> complex:
    return cmath.sqrt(z)


def magnitude(z: complex) -> float:
    return float(abs(z))


REAL_ONLY = [as_real, math_exp, ordered, floored, smaller, remainder,
             cancelled, through_a_real_helper]


def _non_real_witness(counterexample: str) -> bool:
    return "j" in counterexample.split(":")[0]


@pytest.mark.parametrize("fn", REAL_ONLY, ids=lambda fn: fn.__name__)
def test_a_real_only_operation_on_a_complex_parameter_does_not_lift(fn):
    assert lift(fn, effective_facts(fn)) is None


@pytest.mark.parametrize("fn", [as_real, floored, cancelled,
                                through_a_real_helper],
                         ids=lambda fn: fn.__name__)
def test_a_real_only_operation_is_not_defined_on_the_plane(fn):
    (p,) = check_conjectures(fn, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert "TypeError" in p.counterexample, p.counterexample
    assert _non_real_witness(p.counterexample), p.counterexample


@pytest.mark.parametrize("fn", REAL_ONLY, ids=lambda fn: fn.__name__)
def test_a_value_claim_over_a_real_only_operation_is_falsified(fn):
    rows = check_conjectures(fn, [claim("f(z) == f(z)")],
                             float_companions=True)
    assert rows[0].verdict == "falsified", [(p.name, p.verdict, p.route)
                                            for p in rows]
    assert "TypeError" in rows[0].counterexample, rows[0].counterexample
    assert _non_real_witness(rows[0].counterexample), rows[0].counterexample
    assert not any(p.verdict in ("proven", "holds") for p in rows), \
        [(p.name, p.verdict, p.route) for p in rows]


def test_a_complex_square_root_is_defined_on_the_plane():
    rows = check_conjectures(principal_root, [claim("f(z) == f(z)")],
                             float_companions=True)
    assert rows[0].verdict == "proven", (rows[0].verdict, rows[0].note,
                                         rows[0].counterexample)
    (p,) = check_conjectures(principal_root, [claim("is_defined(f)")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)


def test_the_magnitude_of_a_complex_parameter_still_derives():
    assert lift(magnitude, effective_facts(magnitude)) is not None
    (p, *_rest) = check_conjectures(magnitude, [claim("f(z) >= 0")])
    assert p.verdict == "proven", (p.verdict, p.route, p.note)


def test_an_unbound_complex_parameter_ranges_over_the_plane():
    (p, companion) = check_conjectures(magnitude, [claim("f(z) >= 0")],
                                       float_companions=True)
    assert "inferred z in C from its own complex annotation" in p.note, p.note
    assert companion.name == "f_z_ge_0[complex]", companion.name
    assert companion.verdict == "holds", (companion.verdict,
                                          companion.counterexample)


def squared(z: complex) -> complex:
    return z * z


def test_the_computation_companion_runs_in_complex128():
    rows = check_conjectures(squared, [claim("f(z) == z ** 2")],
                             float_companions=True)
    assert rows[0].verdict == "proven", (rows[0].verdict, rows[0].note)
    (companion,) = rows[1:]
    assert companion.name == "f_z_eq_z_2[complex]", companion.name
    assert "complex128" in companion.note, companion.note


def test_a_real_binding_keeps_the_float_companion():
    rows = check_conjectures(magnitude, [claim("for z in [0, 1], f(z) >= 0")],
                             float_companions=True)
    assert [p.name for p in rows] == ["f_z_ge_0", "f_z_ge_0[float]"], \
        [p.name for p in rows]


def test_an_ordering_false_off_the_real_line_is_not_proven():
    (p, *_rest) = check_conjectures(squared, [claim("f(z) >= 0")],
                                    float_companions=True)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert _non_real_witness(p.counterexample), p.counterexample
