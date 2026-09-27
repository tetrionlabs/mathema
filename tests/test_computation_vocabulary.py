# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The executed side of a claim is called the computation (P11).

A derive `proven` is the mathematics; what runs the real code in
float64 is the computation of the claim, and the record says so in
those words: the `[float]` companion's note and sketch, the detail of a
failing point, the chained companion, the extremity probe and the
acceptance plan for a companion. "implementation" stays only in the
public vocabulary (`blame: implementation`, the `implementation:*`
causes). The bracket after a companion's name is a computation
descriptor, parsed by `gates.companion_descriptor` (P12).
"""
import math

import mathema
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim


def _check(fn, law, **kw):
    kw.setdefault("route", "derive")
    rec = mathema.check(fn, claims=[claim(law, name="law", **kw)])
    return {p.name: p for p in rec.probes}


def _text(probe) -> str:
    return " ".join(str(v) for v in (probe.note, probe.sketch,
                                          probe.counterexample) if v)


def doubled(x: float) -> float:
    return 2.0 * x


def plus_one_minus(x: float) -> float:
    return (x + 1.0) - x


def power_two(x: float) -> float:
    return x ** 2


def all_nan(x: float) -> float:
    return float("nan") * x


def exp_of(x: float) -> float:
    return math.exp(x)


def test_a_holding_companion_names_the_computation_in_float64():
    probes = _check(doubled, "for x in [0, 1], f(x) >= 0")
    comp = probes["law[float]"]
    assert comp.verdict == "holds"
    assert comp.note.startswith("the computation of law in float64, "
                                "executed at ")
    assert "implementation" not in comp.note


def test_a_falsified_companion_says_the_mathematics_is_proven():
    probes = _check(plus_one_minus, "for x in [0, 1e17], f(x) == 1")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert comp.sketch.startswith("law is mathematically proven, but its "
                                  "computation fails at x=")
    assert "fix the code" in comp.sketch
    assert "implementation" not in _text(comp)
    # the public stratum vocabulary is unchanged
    assert comp.stratum["blame"] == "implementation"
    assert comp.stratum["cause"] == "implementation:numerical-instability"


def test_a_raise_in_the_computation_is_named_as_such():
    probes = _check(power_two, "for x in [1e200, 1e300], f(x) >= 0")
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert "the computation raises OverflowError here" in comp.sketch


def test_a_nan_from_the_computation_is_named_as_such():
    probes = _check(all_nan, "for x in [1, 2], f(x) * 0 == 0")
    comp = probes.get("law[float]")
    assert comp is not None and comp.verdict == "falsified"
    assert "implementation" not in _text(comp)


def test_the_chained_companion_names_the_computation():
    probes = _check(plus_one_minus, "for x in [0, 1e300], 0.5 <= f(x) <= 1")
    comp = probes["law[float]"]
    assert comp.note.startswith("the computation of law in float64, "
                                "executed link by link; ")


def test_the_extremity_probe_names_the_computation():
    (probe,) = check_conjectures(exp_of, [claim("is_extremity_safe(x)",
                                                route="best")],
                                 domain={"x": (0.0, 1000.0)},
                                 facts=analyze_source(exp_of))
    assert probe.verdict == "falsified"
    assert "the computation leaves float range there" in _text(probe)
    assert "the implementation" not in _text(probe)


def test_the_companion_descriptor_parses_the_bracket():
    from mathema.gates import companion_descriptor, companion_name
    assert companion_descriptor(companion_name("law")) == ("float",)
    assert companion_descriptor("is_overflow_safe[x][float]") == ("float",)
    assert companion_descriptor("law[float, cpython3.12]") == (
        "float", "cpython3.12")
    assert companion_descriptor("law") == ()
