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
    for route in ("derive", "best"):
        p = _v(just_above, "for x in [0, 1], f(x) == x", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample
        assert p.meta.get("mathema.corroboration") == "reproduced"
        assert "engine bug" not in (p.note or "")
        assert "exactly" in (p.note or "")


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
    p = _v(just_above, "for x in [0, 1], f(x) ~= x", "best")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "engine bug" not in (p.note or "")


def test_a_declared_tolerance_on_equality_stays_part_of_the_claim():
    p = _v(just_above, "for x in [0, 1], f(x) == x", "best", tolerance=1e-9)
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "engine bug" not in (p.note or "")
    assert p.meta.get("mathema.corroboration") is None
