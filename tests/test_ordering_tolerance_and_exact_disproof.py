# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A closed ordering (`<=`, `>=`) with no declared tolerance gets the
default allowance on the probe route. A draw that passes only within
it is decided in exact arithmetic: false there falsifies, and a probe
`holds` that the allowance absorbed says so in its note. When the derive route
disproves the claim, the real code is executed at derive's witness and
compared exactly: a violation there, however small, falsifies the
claim with that witness. Where rounding makes the executed code satisfy
the relation exactly, the body is read exactly at the witness: a
literal `1e-20` is 1/10^20 and the claim is falsified on the
mathematics, the computation holding within its allowance; a gap read
from outside the body has no exact reading, and the disproof is then
`unknown` with the reason "exact arithmetic only". A declared tolerance
binds the computation line only: the mathematics line still falsifies on
the exact gap."""
from mathema.conjecture import check_conjectures, claim

#: a float read from outside the body: no exact reading
HAIR = 1e-20


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
    # the witness, run again, violates the ordering (ruling of
    # 2026-10-06: the allowance is relative to the result, so near 0
    # the 1e-10 is a plain miss and needs no exact re-check)
    import re
    for route in ("derive", "best"):
        p = _v(just_above, "for x in [0, 1], f(x) <= x", route)
        assert p.verdict == "falsified", (route, p.verdict, p.note)
        assert p.counterexample
        assert p.meta.get("mathema.corroboration") == "reproduced"
        assert "mathema bug" not in (p.note or "")
        x = float(re.search(r"x = ([-+0-9.e]+)", p.counterexample).group(1))
        assert just_above(x) > x, p.counterexample


def test_the_greater_or_equal_side_is_exact_too():
    def just_below(x: float) -> float:
        return x - 1e-10
    p = _v(just_below, "for x in [0, 1], f(x) >= x", "derive")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_unbounded_example_falsifies():
    p = _v(just_above, "f(x) <= x", "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_probe_pass_within_the_allowance_is_decided_exactly():
    # over [1, 2] the allowance (relative to the result) admits the
    # 1e-10 at every draw, and exactly f(x) = x + 1/10**10 > x
    p = _v(just_above, "for x in [1, 2], f(x) <= x", "probe")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "false here in exact arithmetic" in p.counterexample, \
        p.counterexample


def rounds_above(x: float) -> float:
    # (0.1 + 0.2) / 0.3 is 1.0000000000000002 in float64 and exactly 1
    return x * (0.1 + 0.2) / 0.3


def test_the_probe_keeps_its_allowance_and_says_what_it_absorbed():
    # the float result exceeds x by a rounding at some draws, and
    # exactly f(x) = x
    p = _v(rounds_above, "for x in [1, 2], f(x) <= x", "probe")
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "within the default tolerance" in (p.note or "")
    assert "fails by 4.44e-16" in (p.note or "")


def test_a_probe_holds_with_nothing_absorbed_carries_no_tolerance_note():
    p = _v(exact, "for x in [0, 1], f(x) <= x", "probe")
    assert p.verdict == "holds"
    assert "within the default tolerance" not in (p.note or "")


def test_a_declared_tolerance_binds_only_the_computation_line():
    # exactly f(x) - x = 1/10**10 > 0, inside the declared 1e-9: the
    # mathematics line is exact and falsifies
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "best",
           tolerance=1e-9)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "within the default tolerance" not in (p.note or "")


def test_a_gross_violation_still_falsifies_as_before():
    p = _v(far_above, "for x in [0, 1], f(x) <= x", "derive")
    assert p.verdict == "falsified"


def rounded_away(x: float) -> float:
    return x + 1e-20


def rounded_away_below(x: float) -> float:
    return x - 1e-20


def rounded_away_by_a_global(x: float) -> float:
    return x + HAIR


def rounded_away_below_by_a_global(x: float) -> float:
    return x - HAIR


def test_rounding_the_ordering_violation_away_is_exact_arithmetic_only():
    # the gap comes from outside the body: nothing confirms it exactly
    for fn, law in ((rounded_away_by_a_global, "for x in [1, 2], f(x) <= x"),
                    (rounded_away_below_by_a_global,
                     "for x in [1, 2], f(x) >= x")):
        for route in ("derive", "best"):
            p = _v(fn, law, route)
            assert p.verdict != "falsified", (law, route, p.verdict)
            assert p.meta.get("mathema.corroboration") == "uncorroborated"
            assert p.meta.get("mathema.corroboration_reason") == \
                "exact arithmetic only", (law, route, p.meta)
            assert "mathema bug" not in (p.note or ""), (law, route, p.note)
            assert "floating point does not reproduce" in (p.note or "")


def test_a_literal_violation_rounding_hides_is_falsified_on_the_mathematics():
    for fn, law in ((rounded_away, "for x in [1, 2], f(x) <= x"),
                    (rounded_away_below, "for x in [1, 2], f(x) >= x")):
        for route in ("derive", "best"):
            p = _v(fn, law, route)
            assert p.verdict == "falsified", (law, route, p.verdict, p.note)
            assert p.meta.get("mathema.corroboration") == "reproduced"
            witness = p.meta["mathema.exact_witness"]
            assert witness["reading"] == "mathematics", (law, witness)
            assert witness["computation"] == "holds within its allowance", \
                (law, witness)
            assert "floating point does not reproduce" not in (p.note or "")


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
    # derive's exact disproof reproduces at its witness: an executed
    # witness, no engine-bug flag
    p = _v(just_above, "for x in [0, 1], f(x) <= x", "best",
           tolerance=1e-9)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "mathema bug" not in (p.note or "")
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta
