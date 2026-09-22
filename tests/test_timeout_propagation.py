# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A real hang, reported externally: a Black-Scholes call-price PDE
claim (math.erf recently landing in _SYMPY_FUNCS made this function
liftable for the first time) ran forever under
check_conjectures(..., extensive=False), CPU pinned, no output.

Two distinct bugs, both closed here:

1. `_prove_relation`'s plain `.equals()` proof attempt had no wall-clock
   cap at all, unlike `_try_case_split`'s own critical-point search,
   which already had one. See `_decide_relation` in
   symbolic/_proof_support.py.

2. The critical-point search's own cap (`_with_timeout` around
   `_critical_points_over_expr`) already existed but didn't actually
   work: `_pole_hazards`/`_stationary_and_inflection_points`/
   `_fractional_power_and_log_hazards` each loop over several
   sympy.solve() calls inside a bare `except Exception: continue`
   (a deliberate "degrade gracefully on any one root failing" design).
   `TimeoutError` is an `Exception`, so the alarm firing mid-loop was
   silently swallowed as an ordinary failed root search, the loop
   just moved on to the next variable with the alarm already spent and
   no cap left protecting the rest of the function. Confirmed directly
   against the real reported fixture: the very same expression that
   used to hang for 30+ seconds now returns in ~1-3s.
"""
import time

import sympy

from mathema import diagnostics
from mathema.diagnostics import (
    _fractional_power_and_log_hazards,
    _pole_hazards,
    _stationary_and_inflection_points,
)
from mathema.symbolic._proof_support import ProofResult, _prove_relation


def _raise_timeout(*args, **kwargs):
    raise TimeoutError("exceeded the wall-clock cap")


def test_pole_hazards_propagates_a_timeout_instead_of_swallowing_it(monkeypatch):
    monkeypatch.setattr(diagnostics.sympy, "solve", _raise_timeout)
    x = sympy.Symbol("x")
    expr = 1 / (x - 1)
    try:
        _pole_hazards(expr, "<test>")
        assert False, "TimeoutError should have propagated, not been swallowed"
    except TimeoutError:
        pass


def test_stationary_and_inflection_points_propagates_a_timeout(monkeypatch):
    monkeypatch.setattr(diagnostics.sympy, "solve", _raise_timeout)
    x = sympy.Symbol("x")
    expr = x ** 3
    try:
        _stationary_and_inflection_points(expr, "<test>")
        assert False, "TimeoutError should have propagated, not been swallowed"
    except TimeoutError:
        pass


def test_fractional_power_and_log_hazards_propagates_a_timeout(monkeypatch):
    monkeypatch.setattr(diagnostics.sympy, "solve", _raise_timeout)
    x = sympy.Symbol("x")
    expr = sympy.log(x)
    try:
        _fractional_power_and_log_hazards(expr, "<test>")
        assert False, "TimeoutError should have propagated, not been swallowed"
    except TimeoutError:
        pass


def test_prove_relation_caps_a_hanging_equals_call(monkeypatch):
    """_decide_relation's own simplify()/.equals() chain, not just the
    critical-point search, must respect the wall-clock cap; this is
    the exact gap the external report's stack dump pointed at."""
    def _slow_simplify(expr, *args, **kwargs):
        time.sleep(5)
        return expr

    monkeypatch.setattr(sympy, "simplify", _slow_simplify)
    x, y = sympy.symbols("x y")
    start = time.monotonic()
    result = _prove_relation(x, y, "==", {}, None, {"x": x, "y": y})
    elapsed = time.monotonic() - start
    assert isinstance(result, ProofResult)
    assert result.status == "undecided"
    assert elapsed < 5   # well under the 5s sleep; FAST_TIMEOUT_SECONDS is 3


def test_the_reported_black_scholes_erf_pde_claim_no_longer_hangs():
    """The exact real-world repro reported externally, run for real
    (no mocking): a claim that reaches _prove_relation's fallback chain
    on a genuinely hard expression must return, not hang."""
    import math

    import mathema
    from mathema.claims import claim, check_conjectures

    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        N1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        N2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        return S * N1 - K * math.exp(-r * T) * N2

    cj = claim("d(f(S, K, T, r, sigma), T) + 0.5 * sigma**2 * S**2 * "
              "d(f(S, K, T, r, sigma), S, S) + r * S * d(f(S, K, T, r, sigma), S) "
              "- r * f(S, K, T, r, sigma) == 0", name="pde", route="derive")
    facts = mathema.analyze(call_price)

    start = time.monotonic()
    probes = check_conjectures(call_price, [cj], facts=facts, extensive=False)
    elapsed = time.monotonic() - start
    assert elapsed < 15
    assert len(probes) == 1
