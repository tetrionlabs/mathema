# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise region counts wherever it sits in the body. Division by zero
or `sqrt` of a negative after a local import, an annotated, augmented or
tuple assignment, or an `assert` still makes a value claim over that
region false, so derive never proves it; the same claim on a region
where nothing raises is still proven."""
import pytest

from mathema.conjecture import check_conjectures, claim


def recip_after_import(x: float) -> float:
    import math  # noqa: F401
    return 1.0 / x


def sqrt_from_import(x: float) -> float:
    from math import sqrt
    return sqrt(x)


def recip_after_annassign(x: float) -> float:
    y: float = x
    return 1.0 / y


def recip_after_augassign(x: float) -> float:
    y = x
    y += 0.0
    return 1.0 / y


def recip_after_tuple(x: float) -> float:
    a, b = x, 1.0
    return b / a


def recip_after_assert(x: float) -> float:
    assert x > -10
    return 1.0 / x


def recip_after_with(x: float) -> float:
    import contextlib
    with contextlib.nullcontext():
        pass
    return 1.0 / x


_CASES = [
    (recip_after_import, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
    (sqrt_from_import, "f(x) <= 2", "[-4, 4]", "[0, 4]"),
    (recip_after_annassign, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
    (recip_after_augassign, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
    (recip_after_tuple, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
    (recip_after_assert, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
    (recip_after_with, "f(x) >= 1", "[0, 1]", "[0.5, 1]"),
]


@pytest.mark.parametrize("fn,rel,raising,safe", _CASES,
                         ids=[c[0].__name__ for c in _CASES])
def test_a_raise_region_after_any_statement_blocks_the_proof(fn, rel, raising, safe):
    (p,) = check_conjectures(fn, [claim(f"for x in {raising}, {rel}",
                                        route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)


_LIFTED = [c for c in _CASES if c[0] in (recip_after_import, sqrt_from_import,
                                          recip_after_tuple)]


@pytest.mark.parametrize("fn,rel,raising,safe", _LIFTED,
                         ids=[c[0].__name__ for c in _LIFTED])
def test_the_same_claim_away_from_the_raise_is_proven(fn, rel, raising, safe):
    (p,) = check_conjectures(fn, [claim(f"for x in {safe}, {rel}",
                                        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_an_assert_is_a_raise_region():
    (p,) = check_conjectures(recip_after_assert,
                             [claim("for x in [-20, -12], f(x) <= 0",
                                    route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    (q,) = check_conjectures(recip_after_assert,
                             [claim("for x in [-20, -12], f(x) <= 0")])
    assert q.verdict == "falsified", (q.verdict, q.note)


def ramp(amp: float, n: float) -> "list":
    import numpy as np
    t = np.linspace(0.0, 1.0, n)
    return amp * t


def test_linspace_with_a_non_integer_count_is_a_raise_region():
    (p,) = check_conjectures(ramp, [claim(
        "for amp in [0, 2], n in [2, 10], f(amp, n)[0] == 0", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    (q,) = check_conjectures(ramp, [claim(
        "for amp in [0, 2], n in [2, 10] ⊂ Z, f(amp, n)[0] == 0",
        route="derive")])
    assert q.verdict == "proven", (q.verdict, q.note)


def recip_in_ternary(x: float, s: str) -> float:
    return 1.0 / x if s == "a" else 0.0


def recip_of_opaque(x: float) -> float:
    y = sorted([x])[0]
    return 1.0 / y


@pytest.mark.parametrize("fn,law", [
    (recip_of_opaque, "for x in [0, 1], f(x) >= 1"),
])
def test_a_divisor_that_does_not_lift_blocks_the_proof(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)


def test_an_array_count_left_real_is_falsified_at_a_non_integer():
    from tests.test_symbolic import sine_wave
    (p,) = check_conjectures(sine_wave, [claim(
        "f(amp, freq, n)[0] == 0", route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample
