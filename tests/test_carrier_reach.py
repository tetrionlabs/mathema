# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""How far an unbounded direction is exercised comes from the carrier:
float64's maximum is `sys.float_info.max`, and Python's int has none.
Along an unbounded direction nine draws in ten stay at everyday
magnitudes and one goes toward the carrier's reach."""
import math
import pathlib
import random
import re
import sys

import mathema

_PACKAGE = pathlib.Path(mathema.__file__).parent


def test_the_carriers_state_their_maximum():
    from mathema.representations import PY_FLOAT64, PY_INT
    assert PY_FLOAT64.max_magnitude == sys.float_info.max
    assert PY_INT.max_magnitude is None


def test_the_sampling_reach_is_the_float64_maximum():
    from mathema._sampling import carrier_reach
    assert carrier_reach() == sys.float_info.max


def test_no_hard_coded_float_maximum_outside_the_representation_table():
    literal = re.compile(r"(?<![\w.])1(?:\.0)?e\+?308\b")
    found = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        if path.name == "representations.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if literal.search(line):
                found.append(f"{path.relative_to(_PACKAGE)}:{number}: {line.strip()}")
    assert found == []


def test_the_companion_runs_to_the_carriers_maximum():
    from mathema.conjecture import claim

    def plus_one_minus(x: float) -> float:
        return (x + 1.0) - x

    rec = mathema.check(plus_one_minus,
                        claims=[claim("f(x) == 1", name="law",
                                      route="derive")])
    comp = {p.name: p for p in rec.probes}["law[float]"]
    assert f"{sys.float_info.max:g}" in comp.note, comp.note


def _split(bounds, monkeypatch, draws=20000):
    import mathema._sampling as S
    real = S._far_draw
    calls = []

    def counted(*args):
        calls.append(1)
        return real(*args)

    monkeypatch.setattr(S, "_far_draw", counted)
    rng = random.Random(7)
    specials = S._SpecialCycle(rng)
    everyday = 0
    for _ in range(draws):
        before = len(calls)
        v = S._synth_scalar(rng, bounds, specials=specials)
        if len(calls) == before:
            assert abs(v) <= 1e6, v
            everyday += 1
    return len(calls) / draws, everyday / draws


def test_an_undeclared_direction_spends_a_tenth_of_its_draws_far(monkeypatch):
    from mathema.domain import operational_domain
    from mathema._sampling import carrier_reach
    reach = carrier_reach()
    bounds, _ = operational_domain({}, (-reach, reach), bare=("x",))
    far, everyday = _split(bounds["x"], monkeypatch)
    assert 0.095 < far < 0.105, far
    assert far + everyday == 1.0


def test_a_declared_unbounded_direction_spends_a_tenth_of_its_draws_far(monkeypatch):
    from mathema.domain import operational_domain
    from mathema._sampling import carrier_reach
    reach = carrier_reach()
    bounds, _ = operational_domain({"x": (0.0, math.inf)}, (-reach, reach))
    far, everyday = _split(bounds["x"], monkeypatch)
    assert 0.095 < far < 0.105, far
    assert far + everyday == 1.0
