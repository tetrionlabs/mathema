# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function's own guard conditions are pinned points. `if denom ==
0.0:` changes the result only on a set random sampling never lands on,
so the probe route tries the solutions of each guard inside the domain
before it samples, the way it tries the domain's corners. A derive
disproof that lives only on such a set is corroborated there too, so
it falsifies with a witness executed against the real code."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim


def ratio(x, y):
    denom = x * y
    if denom == 0.0:
        return 0.0
    return x / denom


def shifted_guard(x: float) -> float:
    if x - 0.25 == 0.0:
        return -1.0
    return abs(x)


LAW = "for x in [-1, 2], y in [1, 3], f(x, y) == 1/y"


def test_a_guard_solution_inside_the_domain_falsifies():
    (p,) = check_conjectures(ratio, [claim(LAW, route="probe")])
    assert p.verdict == "falsified", p
    assert p.counterexample.startswith("(0, "), p.counterexample


@pytest.mark.needs_full_proof_budget
def test_the_derive_disproof_is_corroborated_at_the_guard():
    (p,) = check_conjectures(ratio, [claim(LAW)])
    assert p.verdict == "falsified", (p.note, p.meta)
    # derive's case split names x*y = 0; the real code, executed there,
    # returns 0.0 where the claim says 1/y
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta
    assert p.counterexample.startswith("x=0, "), p.counterexample
    assert ratio(0.0, 2.0) == 0.0


def test_a_one_parameter_guard_is_pinned_at_its_own_solution():
    (p,) = check_conjectures(shifted_guard, [claim(
        "for x in [0, 1], f(x) >= 0", route="probe")])
    assert p.verdict == "falsified", p
    assert "0.25" in p.counterexample, p.counterexample


def test_a_guard_solution_outside_the_domain_is_never_tried():
    (p,) = check_conjectures(shifted_guard, [claim(
        "for x in [0.5, 1], f(x) >= 0", route="probe")])
    assert p.verdict == "holds", p.counterexample


def test_a_case_split_disproof_is_corroborated_on_its_guard():
    from mathema.symbolic._proof_support import _corroborate_disproof

    x, y = sympy.symbols("x y", real=True)
    diff = sympy.Piecewise((-1 / y, sympy.Eq(x * y, 0)), (0, True))
    point = _corroborate_disproof(
        diff, {"x": (-1.0, 2.0), "y": (1.0, 3.0)}, {"x": x, "y": y})
    assert point is not None
    assert point[x] == 0
    assert 1.0 <= point[y] <= 3.0
