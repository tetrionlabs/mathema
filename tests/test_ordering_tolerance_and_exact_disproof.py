# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A closed ordering (`<=`, `>=`) with no declared tolerance gets the
default allowance of 1e-9 on the probe route. A probe `holds` that the
allowance absorbed says so in its note. When the derive route
disproves the claim, the real code is executed at derive's witness and
compared exactly: a violation there, however small, falsifies the
claim with that witness. A disproof that holds only in exact
arithmetic, where rounding makes the executed code satisfy the relation
exactly, is `unknown` with the reason "exact arithmetic only"; a
declared tolerance absorbs it outright."""
from mathema.conjecture import check_conjectures, claim


def just_above(x: float) -> float:
    return x + 1e-10


def exact(x: float) -> float:
    return x


def far_above(x: float) -> float:
    return x + 1.0


def _v(fn, law, route, **kw):
    (p,) = check_conjectures(fn, [claim(law, route=route, **kw)])
    return p


def test_an_exact_derive_disproof_inside_the_allowance_is_falsified():
    for route in ("derive", "best"):
        p = _v(just_above, "for x in [0, 1], f(x) <= x", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample
        assert p.meta.get("mathema.corroboration") == "reproduced"
        assert "engine bug" not in (p.note or "")
        assert "exactly" in (p.note or "")


def test_the_greater_or_equal_side_is_exact_too():
    def just_below(x: float) -> float:
        return x - 1e-10
    p = _v(just_below, "for x in [0, 1], f(x) >= x", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_unbounded_example_falsifies():
    p = _v(just_above, "f(x) <= x", "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_probe_keeps_its_allowance_and_says_what_it_absorbed():
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "probe")
    assert p.verdict == "holds"
    assert "within the default tolerance" in (p.note or "")
    assert "fails by 1e-10" in (p.note or "")


def test_a_probe_holds_with_nothing_absorbed_carries_no_tolerance_note():
    p = _v(exact, "for x in [0, 1], f(x) <= x", "probe")
    assert p.verdict == "holds"
    assert "within the default tolerance" not in (p.note or "")


def test_a_declared_tolerance_is_part_of_the_claim_and_stays():
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "best",
           tolerance=1e-9)
    assert p.verdict != "falsified", (p.verdict, p.note)
    assert "within the default tolerance" not in (p.note or "")


def test_a_gross_violation_still_falsifies_as_before():
    p = _v(far_above, "for x in [0, 1], f(x) <= x", "derive")
    assert p.verdict == "falsified"


def rounded_away(x: float) -> float:
    return x + 1e-20


def rounded_away_below(x: float) -> float:
    return x - 1e-20


def test_rounding_the_ordering_violation_away_is_exact_arithmetic_only():
    for fn, law in ((rounded_away, "for x in [1, 2], f(x) <= x"),
                    (rounded_away_below, "for x in [1, 2], f(x) >= x")):
        for route in ("derive", "best"):
            p = _v(fn, law, route)
            assert p.verdict != "falsified", (law, route, p.verdict)
            assert p.meta.get("mathema.corroboration") == "uncorroborated"
            assert p.meta.get("mathema.corroboration_reason") == \
                "exact arithmetic only", (law, route, p.meta)
            assert "engine bug" not in (p.note or ""), (law, route, p.note)
            assert "floating point does not reproduce" in (p.note or "")


def test_a_violation_the_code_reproduces_below_the_allowance_still_falsifies():
    p = _v(just_above, "for x in [1, 2], f(x) <= x", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample
    assert p.meta.get("mathema.corroboration") == "reproduced"
    assert p.meta.get("mathema.corroboration_reason") is None


def test_a_gross_violation_falsifies_with_a_witness_and_no_rounding_label():
    for route in ("derive", "best"):
        p = _v(far_above, "for x in [1, 2], f(x) <= x", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample
        assert p.meta.get("mathema.corroboration") == "reproduced"
        assert p.meta.get("mathema.corroboration_reason") is None
        assert "floating point does not reproduce" not in (p.note or "")


def test_a_violation_inside_a_declared_tolerance_is_not_an_engine_bug():
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "best",
           tolerance=1e-9)
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "engine bug" not in (p.note or "")
    assert p.meta.get("mathema.corroboration") is None
