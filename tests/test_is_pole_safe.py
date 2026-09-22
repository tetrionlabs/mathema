# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_pole_safe[param] (probing.py's is_pole_safe ClaimFamily, formerly
probe()'s own hardcoded domain_safe[param] battery entry): proves (or
falsifies) whether a declared domain excludes every pole of the
function found among the same points _points_for_probe already
computes. Now suggested via suggest_claims() and adjudicated through
check_conjectures() like every other claim, rather than run
unconditionally inside probe()'s own battery, so it shows up in
mathema.check()'s default claims (claims=None -> suggest_claims())."""
import mathema
from mathema.grammar import Interval
from mathema.probing import _pole_safety


def _load(tmp_path, name, source):
    fixture = tmp_path / f"{name}.py"
    fixture.write_text(source)
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        mod = __import__(name)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


def test_is_pole_safe_reports_proven_when_domain_excludes_the_pole(tmp_path):
    mod = _load(tmp_path, "pole_safe_proven_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 5)\n")
    r = mathema.check(mod.f, domain={"x": (0.0, 1.0)})
    probe = next(p for p in r.probes if p.name == "is_pole_safe[x]")
    assert probe.verdict == "proven"
    assert probe.route == "examine"


def test_is_pole_safe_reports_falsified_when_domain_contains_the_pole(tmp_path):
    mod = _load(tmp_path, "pole_safe_falsified_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 5)\n")
    r = mathema.check(mod.f, domain={"x": (0.0, 10.0)})
    probe = next(p for p in r.probes if p.name == "is_pole_safe[x]")
    assert probe.verdict == "falsified"
    assert "x = 5" in probe.counterexample


def test_is_pole_safe_absent_when_no_pole_exists(tmp_path):
    mod = _load(tmp_path, "pole_safe_no_pole_fixture",
               "def f(x: float) -> float:\n"
               "    return x * x + 1.0\n")
    r = mathema.check(mod.f, domain={"x": (0.0, 10.0)})
    assert not [p for p in r.probes if p.name == "is_pole_safe[x]"]


def test_is_pole_safe_falsified_when_no_domain_declared_for_the_pole_variable(tmp_path):
    # an unstated domain asserts everywhere (declared-schema: a claim
    # field, not an unknown), so the pole at x = 5 is an admitted
    # point, and the empirical half witnesses the real call raising
    # there. Falsified with the concrete witness, not "unknown": the
    # structural derive half alone can't decide an undeclared bound,
    # but the family's pole-probe trials can, and a witnessed raise
    # at an admitted point is a complete counterexample.
    mod = _load(tmp_path, "pole_safe_no_domain_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 5)\n")
    r = mathema.check(mod.f)
    probe = next(p for p in r.probes if p.name == "is_pole_safe[x]")
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "x = 5" in probe.counterexample


def test_is_pole_safe_unsure_on_a_two_variable_coupled_pole(tmp_path):
    mod = _load(tmp_path, "pole_safe_coupled_fixture",
               "def f(x: float, y: float) -> float:\n"
               "    return 1 / (x - y)\n")
    r = mathema.check(mod.f, domain={"x": (0.0, 1.0)})
    probe = next(p for p in r.probes if p.name == "is_pole_safe[x]")
    assert probe.verdict == "unknown"


def test_pole_safety_directly_with_a_hand_built_points_list():
    points = [{"kind": "pole", "variable": "x", "at": "2", "expression": "x - 2",
              "file": "<test>"}]
    verdict, _ = _pole_safety(Interval(2.0, 5.0, closed_lo=False), points)
    assert verdict == "proven"   # pole exactly at the open (excluded) boundary

    verdict2, contained = _pole_safety(Interval(2.0, 5.0), points)
    assert verdict2 == "falsified"   # pole at the closed (included) boundary
    assert contained == ["2"]
