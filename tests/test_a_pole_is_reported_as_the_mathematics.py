# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise on the probe route whose nudged neighbours evaluate cleanly is
either a floating-point boundary or an isolated pole of the mathematics.
The record tells them apart by the exact mathematics at the witness: a
pole falsifies with the mathematics named as failing there and the
domain remedy, as the derive route reports it; a float boundary keeps
the clamp remedy and `mathematics sound`; and a point whose exact
mathematics cannot be read claims neither."""
import functools
import math
import operator

from mathema.conjecture import check_conjectures, claim

#: a float where sin(m)**2 + cos(m)**2 rounds to just above 1
EDGE = -0.40339759256967955


def inv(x: float) -> float:
    return 1 / (x - 0.5)


def acos_edge(m: float) -> float:
    return math.acos(math.sin(m) ** 2 + math.cos(m) ** 2)


def opaque_edge(m: float) -> float:
    return math.acos(functools.reduce(
        operator.add, [math.sin(m) ** 2, math.cos(m) ** 2]))


def test_an_exact_pole_is_the_mathematics_failing_on_the_probe_route():
    (p,) = check_conjectures(
        inv, [claim("for x in [0, 1], f(x) != 0", route="probe")])
    assert p.verdict == "falsified"
    assert p.meta["mathema.counterexample_args"] == [0.5]
    assert p.stratum["mathematics"] == "unsound"
    assert p.stratum["blame"] == "claim"
    assert p.stratum.get("cause") != "implementation:sub-epsilon-boundary"
    assert "floating-point boundary" not in p.counterexample
    assert "clamp" not in p.counterexample
    assert "narrow the claim's domain" in p.counterexample


def test_the_probe_and_derive_routes_agree_on_the_pole():
    (probed,) = check_conjectures(
        inv, [claim("for x in [0, 1], f(x) != 0", route="probe")])
    (default,) = check_conjectures(
        inv, [claim("for x in [0, 1], f(x) != 0")])
    assert default.verdict == probed.verdict == "falsified"
    assert "narrow the claim's domain" in default.sketch
    assert "narrow the claim's domain" in probed.counterexample


def test_a_float_boundary_keeps_the_clamp_remedy_and_sound_mathematics():
    (p,) = check_conjectures(
        acos_edge, [claim(f"for m in [{EDGE!r}, {EDGE!r}], f(m) == 0",
                          route="probe", tolerance=1e-6)])
    assert p.verdict == "falsified"
    assert "floating-point boundary" in p.counterexample
    assert "clamp" in p.counterexample
    assert p.stratum["mathematics"] == "sound"
    assert p.stratum["cause"] == "implementation:sub-epsilon-boundary"


def test_an_unreadable_point_never_claims_sound_mathematics():
    (p,) = check_conjectures(
        opaque_edge, [claim(f"for m in [{EDGE!r}, {EDGE!r}], f(m) == 0",
                            route="probe", tolerance=1e-6)])
    assert p.verdict == "falsified"
    assert "floating-point boundary" in p.counterexample
    assert "mathematics" not in p.stratum
    assert p.stratum["cause"] == "implementation:sub-epsilon-boundary"
