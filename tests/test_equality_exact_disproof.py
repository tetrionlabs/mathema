# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An equality `==` with no declared tolerance gets the same exact
recheck as a closed ordering. When derive shows the two sides differ in
exact arithmetic but by less than the probe's default allowance, the
real code is executed at derive's witness and compared exactly: if the
executed values differ, the claim is falsified with that witness. If
floating-point rounding makes the executed values exactly equal, the
claim is not falsified. `~=` asks for approximate equality, so it keeps
the allowance, and a declared tolerance is part of the claim."""
from mathema.conjecture import check_conjectures, claim


def just_above(x: float) -> float:
    return x + 1e-10


def rounded_away(x: float) -> float:
    return x + 1e-20


def scaled_by_a_hair(x: float) -> float:
    return x * (1 + 1e-12)


def _v(fn, law, route, **kw):
    (p,) = check_conjectures(fn, [claim(law, route=route, **kw)])
    return p


def test_an_exact_equality_disproof_inside_the_allowance_is_falsified():
    # the witness, run again, differs from x (ruling of 2026-10-06: the
    # allowance is relative to the result, so near 0 the 1e-10 is a
    # plain miss and needs no exact re-check)
    import re
    for route in ("derive", "best"):
        p = _v(just_above, "for x in [0, 1], f(x) == x", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample
        assert p.meta.get("mathema.corroboration") == "reproduced"
        assert "mathema bug" not in (p.note or "")
        x = float(re.search(r"x = ([-+0-9.e]+)", p.counterexample).group(1))
        assert just_above(x) != x, p.counterexample


def test_the_unbounded_equality_falsifies():
    p = _v(just_above, "f(x) == x", "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_difference_that_varies_with_x_is_rechecked_too():
    p = _v(scaled_by_a_hair, "for x in [1, 2], f(x) == x", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "reproduced"


def test_rounding_that_makes_the_code_exactly_equal_does_not_falsify():
    p = _v(rounded_away, "for x in [1, 2], f(x) == x", "derive")
    assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_approximate_equality_keeps_its_allowance():
    # `~=` is abs(f(x) - x) <= ε, decided exactly: 1e-10 is within the
    # 1e-9 default, for every x
    p = _v(just_above, "for x in [0, 1], f(x) ~= x", "best")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "mathema bug" not in (p.note or "")


def test_a_declared_tolerance_on_equality_stays_part_of_the_claim():
    p = _v(just_above, "for x in [0, 1], f(x) == x", "best", tolerance=1e-9)
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "mathema bug" not in (p.note or "")
    assert p.meta.get("mathema.corroboration") is None


def test_rounding_to_exact_equality_is_labelled_exact_arithmetic_only():
    for route in ("derive", "best"):
        p = _v(rounded_away, "for x in [1, 2], f(x) == x", route)
        assert p.meta.get("mathema.corroboration") == "uncorroborated"
        assert p.meta.get("mathema.corroboration_reason") == \
            "exact arithmetic only", (route, p.meta)
        assert "mathema bug" not in (p.note or ""), (route, p.note)
        assert "floating point does not reproduce" in (p.note or "")
