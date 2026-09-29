# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A proof is over the reals: its condition names the real region
(`∀ x ∈ [0.0, 1.0] ⊂ ℝ`), a guard for a missing value is false for a real
number (`x is None`, `x != x`), and the missing points the domain
admits are the companion's to execute. A finite set's own listed
sentinels belong to the claim and are executed by it; a proof by
executing every point of a finite set spawns no companion; a claim about
holes is never settled over slots with nothing missing."""
import math
from typing import Optional

from mathema.conjecture import check_conjectures, claim


def sqrt_guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing")
    return math.sqrt(x)


def double_or_missing(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return 2 * x


def zero_if_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        return 0.0
    return float(x)


def square(x: float) -> float:
    return x * x


def rows(fn, text: str):
    return check_conjectures(fn, [claim(text, name="c")])


def main(fn, text: str):
    return next(p for p in rows(fn, text) if p.name == "c")


def test_the_condition_is_the_real_region():
    p = main(square, "for x in [0, 1], f(x) >= 0")
    assert p.verdict == "proven"
    assert p.condition == "∀ x ∈ [0.0, 1.0] ⊂ ℝ"
    assert "nan" not in (p.sketch or "")


def test_a_missing_value_guard_is_false_over_the_reals():
    for fn in (sqrt_guarded, double_or_missing, zero_if_missing):
        p = main(fn, "for x in [0, 1], f(x) >= 0")
        assert p.verdict == "proven", (fn.__name__, p.verdict, p.note)


def test_an_optional_parameter_has_its_absence_executed_by_the_companion():
    found = check_conjectures(double_or_missing,
                              [claim("for x in [0, 1], f(x) >= 0", name="c")],
                              float_companions=True)
    companion = next(p for p in found if p.name.startswith("c["))
    assert companion.meta["mathema.missing"]["executed"]["x"] == {
        "None": "propagates (None)", "nan": "propagates (nan)"}


def test_a_listed_sentinel_is_executed_by_the_claim_itself():
    p = main(square, "for x in {0.25, None}, f(x) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.meta["mathema.missing"]["executed"] == {"x": {"None": "raised TypeError"}}


def test_a_proof_by_executing_a_finite_set_spawns_no_companion():
    found = rows(zero_if_missing, "for x in {0.25, None}, f(x) >= 0")
    assert [p.name for p in found if p.name.startswith("c")] == ["c"]
    assert found[0].route == "derive:brute_force"


def test_a_claim_about_holes_is_decided_by_execution():
    p = main(double_or_missing, "for x in [0, 1], f(x) in {missing}")
    assert p.route != "derive" and p.verdict == "falsified"
