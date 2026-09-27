# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A keyword-only parameter is passed by keyword wherever mathema builds
a call from a function's parameter list (the built-in battery's
`callable` row, and the safety families' trials), so a signature with a
bare `*` is callable like any other."""
import mathema


def scaled(x: float, *, k: float = 2.0) -> float:
    return x * k


def scaled_root(x: float, *, k: float = 2.0) -> float:
    import math
    return math.sqrt(x) * k


def test_the_battery_calls_a_keyword_only_parameter_by_keyword():
    rec = mathema.check(scaled)
    skipped = [p for p in rec.probes
               if p.name == "callable" and p.verdict == "skipped"]
    assert not skipped, [p.note for p in skipped]


def test_a_safety_family_trial_calls_a_keyword_only_parameter_by_keyword():
    (p,) = [p for p in mathema.check(
        scaled_root, claims=["for x in [-1, 1], is_builtin_safe(x)"]).probes
        if p.meta.get("mathema.surface") == "declared"]
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "TypeError" not in (p.counterexample or "")
