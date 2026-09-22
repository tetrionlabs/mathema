# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""diagnostics._cached_critical_points()/_critical_points_cache_clear():
memoization keyed by Facts.form."""
from mathema import diagnostics
from mathema.analysis import analyze_source


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


def test_cached_critical_points_computes_once(tmp_path, monkeypatch):
    diagnostics._critical_points_cache_clear()
    mod = _load(tmp_path, "cache_once_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 2)\n")
    facts = analyze_source(mod.f)

    calls = []
    real = diagnostics.critical_points

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(diagnostics, "critical_points", counting)
    diagnostics._cached_critical_points(mod.f, facts)
    diagnostics._cached_critical_points(mod.f, facts)
    assert len(calls) == 1


def test_cached_critical_points_keyed_by_form_not_identity(tmp_path):
    diagnostics._critical_points_cache_clear()
    mod_f = _load(tmp_path, "cache_form_f",
                 "def f(x: float) -> float:\n"
                 "    return 1 / (x - 2)\n")
    mod_g = _load(tmp_path, "cache_form_g",
                 "def g(x: float) -> float:\n"
                 "    return 1 / (x - 2)\n")
    facts_f = analyze_source(mod_f.f)
    facts_g = analyze_source(mod_g.g)
    assert facts_f.form == facts_g.form   # rename-invariant, confirmed directly

    diagnostics._cached_critical_points(mod_f.f, facts_f)
    diagnostics._cached_critical_points(mod_g.g, facts_g)
    assert len(diagnostics._critical_points_cache) == 1


def test_pole_domain_note_reflects_the_declared_domain():
    from mathema.grammar import Interval
    assert diagnostics._pole_domain_note("x", None) == "assumed (-inf, inf), not declared"
    note = diagnostics._pole_domain_note("x", {"x": Interval(0.0, 1.0)})
    assert note == "declared: [0.0, 1.0]"


def test_critical_points_cache_clear_resets_state(tmp_path):
    mod = _load(tmp_path, "cache_clear_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 3)\n")
    facts = analyze_source(mod.f)
    diagnostics._cached_critical_points(mod.f, facts)
    assert diagnostics._critical_points_cache
    diagnostics._critical_points_cache_clear()
    assert diagnostics._critical_points_cache == {}
