# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `[float]` line a derive proof spawns, and a ground claim's call
on the probe route, state the largest gap a pass fell within and the
tolerance, for `==` as for `<=` and `>=`; the verdict does not change,
and a bit-exact pass carries no gap."""
import mathema


def lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def lerp_weighted(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b


def _companion(fn, text, **kwargs):
    rec = mathema.check(fn, claims=[mathema.claim(text, name="point",
                                                  **kwargs)])
    main = next(p for p in rec.probes if p.name == "point")
    line = next(p for p in rec.probes if p.name == "point[float]")
    return rec, main, line


def test_lerp_at_its_own_call_states_the_absorbed_gap():
    rec, main, line = _companion(lerp, "f(-0.1, 0.3, 1) == 0.3")
    assert main.verdict == "proven" and line.verdict == "holds"
    assert "differs by 5.55e-17, within the default tolerance (" \
        in line.note, line.note
    printed = next(ln for ln in str(rec).splitlines()
                   if "computation" in ln)
    assert "differs by " in printed, str(rec)


def test_a_sampled_companion_names_the_point_of_its_largest_gap():
    _rec, _main, line = _companion(
        lerp, "for b in [0.29, 0.31], f(-0.1, b, 1) == b")
    assert line.verdict == "holds", line
    clause = next(c for c in line.note.split("; ")
                  if c.startswith("differs by"))
    assert " at b = " in clause, clause


def test_a_bit_exact_companion_carries_no_gap():
    _rec, _main, line = _companion(lerp_weighted, "f(-0.1, 0.3, 1) == 0.3")
    assert line.verdict == "holds", line
    assert "differs by" not in line.note, line.note


def test_the_ground_call_on_the_probe_route_states_its_gap():
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(lerp, [claim("f(-0.1, 0.3, 1) == 0.3",
                                          name="point", route="probe")])
    assert p.verdict == "holds", p
    assert "evaluated once" in p.note, p.note
    assert "differs by 5.55e-17, within the default tolerance (" in p.note, \
        p.note


def test_a_bit_exact_ground_call_carries_no_gap():
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(lerp_weighted, [claim(
        "f(-0.1, 0.3, 1) == 0.3", name="point", route="probe")])
    assert p.verdict == "holds", p
    assert "differs by" not in p.note, p.note
