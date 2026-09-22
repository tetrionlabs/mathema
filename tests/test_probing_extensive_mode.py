# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""probing.py's extensive mode: the fast (default, direct-lift-only)
vs extensive (full fold/dot/sum chain, memoized, bigger timeout)
critical-point analysis behind probe()'s own sampling."""
import time

import mathema
from mathema import diagnostics
from mathema.analysis import analyze_source
from mathema.probing import _critical_hint, _points_for_probe


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


_EMA_SOURCE = ("def ema(x: list, alpha: float) -> float:\n"
              "    y = x[0]\n"
              "    for v in x[1:]:\n"
              "        y = alpha * v + (1 - alpha) * y\n"
              "    return y\n")

# fold-lifts to a Piecewise/Sum whose own denominator (k - 1) doesn't
# depend on the sum's own index, so it survives lifting with a genuine,
# findable pole at k=1, unlike ema, which fold-lifts to a shape with
# no critical points of any kind, real but not useful for testing that
# extensive mode's own full-chain search actually finds something.
_POLE_FOLD_SOURCE = ("def total_scaled(x: list, k: float) -> float:\n"
                     "    total = 0.0\n"
                     "    for v in x:\n"
                     "        total += v / (k - 1)\n"
                     "    return total\n")


def test_fast_mode_still_ignores_fold_shaped_functions_by_default(tmp_path):
    mod = _load(tmp_path, "extensive_fast_fixture", _EMA_SOURCE)
    facts = analyze_source(mod.ema)
    assert _critical_hint(mod.ema, facts, {}) == {}
    assert _critical_hint(mod.ema, facts, {}, extensive=False) == {}


def test_extensive_mode_finds_a_fold_lifted_critical_point(tmp_path):
    diagnostics._critical_points_cache_clear()
    mod = _load(tmp_path, "extensive_true_fixture", _POLE_FOLD_SOURCE)
    facts = analyze_source(mod.total_scaled)
    fast_hints = _critical_hint(mod.total_scaled, facts, {})
    assert fast_hints == {}   # fold-shaped, never even attempted in fast mode
    hints = _critical_hint(mod.total_scaled, facts, {}, extensive=True)
    assert hints.get("k") == [1.0]


def test_extensive_mode_uses_the_cache(tmp_path, monkeypatch):
    diagnostics._critical_points_cache_clear()
    mod = _load(tmp_path, "extensive_cache_fixture", _EMA_SOURCE)
    facts = analyze_source(mod.ema)

    calls = []
    real = diagnostics.critical_points

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(diagnostics, "critical_points", counting)
    _points_for_probe(mod.ema, facts, {}, extensive=True)
    _points_for_probe(mod.ema, facts, {}, extensive=True)
    assert len(calls) == 1


def test_extensive_mode_bounded_on_the_real_ema_fixture(tmp_path):
    # confirms the exact ema (fold-lifted) shape that once made an
    # unrestricted critical-point search hang past 15s now completes
    # within a real wall-clock bound.
    mod = _load(tmp_path, "extensive_bounded_fixture", _EMA_SOURCE)
    t0 = time.monotonic()
    mathema.check(mod.ema, extensive=True)
    elapsed = time.monotonic() - t0
    assert elapsed < 20.0


def test_check_runs_under_the_default_mode_without_error(tmp_path):
    # named for what it actually asserts: the default-mode run
    # completes and produces adjudicated probes (mode-distinguishing
    # artifacts are covered by the wall-clock contrast test above)
    mod = _load(tmp_path, "extensive_default_fixture", _EMA_SOURCE)
    r = mathema.check(mod.ema)
    assert r.probes
    assert any(p.verdict in ("holds", "proven", "falsified") for p in r.probes)


def test_a_timed_out_search_is_recorded_so_it_is_never_redone():
    # the cache's whole reason for existing is that a search which
    # blows the wall-clock cap happens at most once per form. It did
    # not: the alarm raises _WallClockExpired (a BaseException, so
    # sympy's own `except Exception` cannot absorb it), and that only
    # becomes the public TimeoutError at _with_timeout's boundary;
    # which is ABOVE this frame. `except TimeoutError` here could
    # never fire, so every later call redid the doomed search.
    import time

    from mathema import _timeout as T
    from mathema.analysis import analyze_source

    src = ("def slow_ema(x: list, alpha: float) -> float:\n"
           "    y = x[0]\n"
           "    for v in x[1:]:\n"
           "        y = alpha * v + (1 - alpha) * y\n"
           "    return y\n")
    import pathlib
    import sys
    d = pathlib.Path(__file__).parent / "_timeout_cache_fixture.py"
    d.write_text(src)
    sys.path.insert(0, str(d.parent))
    try:
        import _timeout_cache_fixture as fixture
        facts = analyze_source(fixture.slow_ema)
        diagnostics._critical_points_cache_clear()
        calls = []
        real = diagnostics.critical_points

        def slow(*a, **k):
            calls.append(1)
            time.sleep(2)
            return real(*a, **k)

        diagnostics.critical_points = slow
        orig = T.EXTENSIVE_TIMEOUT_SECONDS
        T.EXTENSIVE_TIMEOUT_SECONDS = 1
        try:
            for _ in range(2):
                _points_for_probe(fixture.slow_ema, facts, {}, extensive=True)
            assert len(calls) == 1, "the doomed search ran twice"
            assert facts.form in diagnostics._critical_points_cache
        finally:
            diagnostics.critical_points = real
            T.EXTENSIVE_TIMEOUT_SECONDS = orig
            diagnostics._critical_points_cache_clear()
    finally:
        sys.path.remove(str(d.parent))
        sys.modules.pop("_timeout_cache_fixture", None)
        d.unlink(missing_ok=True)
