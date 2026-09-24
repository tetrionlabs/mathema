# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim family's derive disproof is only `falsified` once the real
code, executed at the point derive names, fails there. A pole inside
the declared domain (is_pole_safe, is_numerically_stable) or a raising
missing-value guard the domain contradicts (is_missing_safe) is a
structural finding; the executed call is the witness. When the call
at that point behaves, the disproof is uncorroborated: the verdict is
not `falsified`, and the record carries the engine-bug flag."""
from mathema import check_conjectures, claim


def reciprocal_shift(x: float) -> float:
    return 1 / (x - 5)


def reciprocal_irrational_pole(x: float) -> float:
    # the pole sqrt(2) has no float spelling: at the nearest float the
    # denominator is 4.4e-16, not zero, so the call returns a finite value
    return 1 / (x * x - 2)


def nan_guarded(x: float) -> float:
    if x != x:
        raise ValueError("x is missing")
    return x


def guard_that_never_fires_on_missing(x):
    if x is not None and x > 100:
        raise ValueError("x out of range")
    return x


def _stable_claim(route):
    return claim("for x in [0, 10], g(f, x) == 1",
                 name="is_numerically_stable", route=route,
                 funcs={"g": "mathema.f.finite_no_error"})


def test_pole_safe_disproof_carries_the_executed_raise():
    cj = claim("for x in [0, 10], is_pole_safe(x)", name="is_pole_safe[x]",
               route="derive")
    (p,) = check_conjectures(reciprocal_shift, [cj])
    assert p.verdict == "falsified"
    assert "x = 5" in p.counterexample
    assert "raised ZeroDivisionError" in p.counterexample
    assert p.meta.get("mathema.corroboration") == "reproduced"


def test_numerically_stable_disproof_carries_the_executed_raise():
    (p,) = check_conjectures(reciprocal_shift, [_stable_claim("derive")])
    assert p.verdict == "falsified"
    assert "raised ZeroDivisionError" in p.counterexample
    assert p.meta.get("mathema.corroboration") == "reproduced"


def test_pole_safe_disproof_the_code_does_not_reproduce_is_not_falsified():
    cj = claim("for x in [0, 10], is_pole_safe(x)", name="is_pole_safe[x]",
               route="derive")
    (p,) = check_conjectures(reciprocal_irrational_pole, [cj])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert p.meta.get("mathema.corroboration") == "uncorroborated"
    assert "UNCORROBORATED" in p.note


def test_numerically_stable_disproof_the_code_does_not_reproduce_is_not_falsified():
    (p,) = check_conjectures(reciprocal_irrational_pole,
                             [_stable_claim("derive")])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert p.meta.get("mathema.corroboration") == "uncorroborated"
    assert "UNCORROBORATED" in p.note


def test_missing_safe_disproof_carries_the_executed_raise():
    cj = claim("for x in [0, 10], is_missing_safe(x)",
               name="is_missing_safe[x]", route="derive")
    (p,) = check_conjectures(nan_guarded, [cj])
    assert p.verdict == "falsified"
    assert "x = nan raised ValueError" in p.counterexample
    assert p.meta.get("mathema.corroboration") == "reproduced"


def test_missing_safe_guard_that_does_not_raise_on_missing_is_not_falsified():
    cj = claim("for x in [0, 10], is_missing_safe(x)",
               name="is_missing_safe[x]", route="derive")
    (p,) = check_conjectures(guard_that_never_fires_on_missing, [cj])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert p.meta.get("mathema.corroboration") == "uncorroborated"
    assert "UNCORROBORATED" in p.note
