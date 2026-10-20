# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A pole inside the domain that no float lands on (sqrt(2) for
1/(x*x - 2), pi/2 for tan) is still a pole: the mathematics has no
value there. `is_pole_safe` reaches the same exact witness `is_defined`
does, certified by interval arithmetic independently of the solver
that found it, while the call at the nearest float returns a large
finite number."""
import math

from mathema.conjecture import check_conjectures, claim


def reciprocal_irrational_pole(x: float) -> float:
    return 1 / (x * x - 2)


def tangent(x: float) -> float:
    return math.tan(x)


def _pole_safe(fn, bound: str, route: str = "best"):
    (p,) = check_conjectures(fn, [claim(f"for x in {bound}, is_pole_safe(x)",
                                        name="is_pole_safe[x]", route=route)])
    return p


def test_an_irrational_pole_falsifies_with_its_exact_witness():
    for route in ("derive", "best"):
        p = _pole_safe(reciprocal_irrational_pole, "[0, 10]", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert "x = sqrt(2)" in p.counterexample, p.counterexample
        assert "certified by interval arithmetic" in p.sketch, p.sketch


def test_the_float_beside_the_pole_returns_a_finite_value():
    nearest = math.sqrt(2)
    assert math.isfinite(reciprocal_irrational_pole(nearest))


def test_is_pole_safe_and_is_defined_agree_on_the_same_pole():
    p = _pole_safe(reciprocal_irrational_pole, "[0, 10]")
    (q,) = check_conjectures(reciprocal_irrational_pole,
                             [claim("for x in [0, 10], is_defined(f)")])
    assert (p.verdict, q.verdict) == ("falsified", "falsified")
    assert p.counterexample.split(":")[0].split(" (")[0] == \
        q.counterexample.split(":")[0]


def test_a_pole_of_a_library_call_no_float_reaches_falsifies():
    p = _pole_safe(tangent, "[0, 2]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "pi/2" in p.counterexample, p.counterexample


def capped_pole(x: float) -> float:
    if x > 5:
        return 0.0
    return 1 / (x * x - 2)


def test_a_pole_reached_on_one_branch_is_found_exactly():
    p = _pole_safe(capped_pole, "[0, 10]", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "x = sqrt(2)" in p.counterexample, p.counterexample


def test_a_domain_that_excludes_the_pole_is_still_proven():
    p = _pole_safe(reciprocal_irrational_pole, "[2, 10]", "derive")
    assert p.verdict == "proven", (p.verdict, p.note)
