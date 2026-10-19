# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line's miss is inherent to float64 only where no float64
computation could have done better: the computed value is the exact
result correctly rounded (no float64 is closer to it), or the miss is
within what the conditioning explains at a point where the problem
itself amplifies rounding (κ above `AMPLIFYING_KAPPA`). A miss beyond
half an ulp at a well-conditioned point is the code's: its note says a
different arrangement of the formula may lose less, never that no
float64 computation can deliver the result, and the computation line is
not accepted alone as a discovery."""
import math
from fractions import Fraction

import pytest

import mathema
from mathema import _conditioning
from mathema._allowance import STABILITY_FACTOR, UNIT_ROUNDOFF
from mathema.acceptance import AcceptanceError, plan_acceptance
from mathema.cli import main


def lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def lerp_weighted(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b


_ENDS = mathema.claim(
    "for a in [-1e6, 1e6], b in [-1e6, 1e6], f(a, b, 1) == b",
    name="ends_at_b", tolerance=0)


def _row(fn, name):
    rec = mathema.check(fn, claims=[_ENDS])
    return rec, next(p for p in rec.probes if p.name == name)


def test_lerp_ending_at_b_loses_what_a_rearrangement_may_not():
    rec, line = _row(lerp, "ends_at_b[float]")
    assert line.verdict == "falsified", line
    found = line.meta["mathema.conditioning"]
    assert set(found) >= {"kappa", "how", "scale", "error", "inherent",
                          "words", "narrow"}, found
    assert found["kappa"] is not None and found["kappa"] < 10, found
    assert found["inherent"] is False, found
    assert "a different arrangement of the formula may lose less" \
        in found["words"], found
    assert "no float64 computation can deliver" not in found["words"]
    text = str(rec)
    assert "a different arrangement of the formula may lose less" in text
    assert "no float64 computation can deliver" not in text, text
    # the loss is the code's, so accepting the line alone is not offered
    assert '"ends_at_b[float]" --as discovery' not in text, text
    assert "fix the code" in text, text


def test_the_weighted_lerp_returns_b_and_carries_no_note():
    rec, line = _row(lerp_weighted, "ends_at_b[float]")
    assert line.verdict == "holds", line
    assert "mathema.conditioning" not in (line.meta or {}), line.meta
    assert "different arrangement" not in str(rec)


def _thirds(point):
    x = Fraction(point["x"])
    return x / 3, x / 3


def test_a_correctly_rounded_result_is_inherent_at_kappa_one():
    # x / 3 rounded once is the float64 nearest the exact third: no
    # float64 is closer, whatever κ is
    computed = 1.0 / 3
    gap = float(abs(Fraction(computed) - Fraction(1, 3)))
    found = _conditioning.at_miss(None, None, {"x": 1.0}, gap, computed,
                                  exact_at=_thirds)
    assert found["how"] == "mathematics" and found["kappa"] == 1.0, found
    assert found["inherent"] is True, found
    assert "no float64 computation can deliver" in found["words"], found
    assert "different arrangement" not in found["words"], found


def test_one_ulp_off_at_kappa_one_is_the_codes():
    computed = math.nextafter(1.0 / 3, 1.0)
    gap = float(abs(Fraction(computed) - Fraction(1, 3)))
    found = _conditioning.at_miss(None, None, {"x": 1.0}, gap, computed,
                                  exact_at=_thirds)
    assert found["inherent"] is False, found
    assert "a different arrangement of the formula may lose less" \
        in found["words"], found
    assert "no float64 computation can deliver" not in found["words"]
    assert found["narrow"] is None, found


def test_a_representable_result_missed_by_any_gap_is_not_rounded():
    def exact(point):
        return Fraction(1), Fraction(1)
    below = math.nextafter(1.0, 0.0)
    found = _conditioning.at_miss(None, None, {"x": 1.0}, 1.0 - below, 1.0,
                                  exact_at=exact)
    assert _conditioning.correctly_rounded(
        exact({"x": 1.0}), 1.0 - below) is False
    assert found["inherent"] is not True, found


def test_inherent_follows_the_two_cases():
    u = UNIT_ROUNDOFF
    threshold = _conditioning.AMPLIFYING_KAPPA
    assert threshold == 10
    # (1) correctly rounded: inherent at any κ, known or not
    assert _conditioning.inherent(1.0, 5 * u, rounded=True) is True
    assert _conditioning.inherent(None, 5 * u, rounded=True) is True
    # (2) within κ·u where κ exceeds the threshold
    assert _conditioning.inherent(1e3, 2 * u) is True
    assert _conditioning.inherent(math.inf, 1.0) is True
    # within κ·u at a small κ: the code's
    assert _conditioning.inherent(1.0, 2 * u) is False
    assert _conditioning.inherent(threshold, 2 * u) is False
    # beyond the stability bound at any κ: the code's
    assert _conditioning.inherent(
        1e3, 2 * STABILITY_FACTOR * 1e3 * u) is False
    assert _conditioning.inherent(None, 2 * u) is None


_LERP_SOURCE = ("def lerp(a: float, b: float, t: float) -> float:\n"
                "    return a + t * (b - a)\n")
_LERP_CLAIMS = ("lerpmod.lerp:\n  claims:\n    - name: ends_at_b\n"
                "      statement: \"for a in [-1e6, 1e6], b in [-1e6, 1e6], "
                "f(a, b, 1) == b\"\n      tolerance: 0\n")


def test_the_lerp_line_is_not_accepted_alone(tmp_path, monkeypatch):
    (tmp_path / "lerpmod.py").write_text(_LERP_SOURCE)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "lerpmod.claims.yaml").write_text(_LERP_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert main(["verify", "--root", str(tmp_path)]) == 1
    with pytest.raises(AcceptanceError) as refused:
        plan_acceptance(str(tmp_path), "lerpmod.lerp", "ends_at_b[float]",
                        "discovery")
    text = str(refused.value)
    assert "a different arrangement of the formula may lose less" in text
    assert "this loss is the code's" in text, text
