# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The wall-clock cap on a thread other than the main one: an MCP
server, a web handler or a thread pool runs mathema off the main
thread, where no signal can be delivered, and the cap must still bound
the guarded work there with the same contract as on the main thread
(TimeoutError at the boundary, `_WallClockExpired` visible inside)."""
import gc
import json
import os
import sys
import threading
import time

import pytest

from mathema._timeout import _WallClockExpired, _with_timeout

DATA = os.path.join(os.path.dirname(__file__), "data")


def _on_a_worker(fn):
    """Run fn on a fresh thread and return (outcome, elapsed), where
    outcome is fn's value or the exception it raised."""
    box = {}

    def run():
        t0 = time.monotonic()
        try:
            box["outcome"] = fn()
        except BaseException as e:   # noqa: BLE001, the test inspects it
            box["outcome"] = e
        box["elapsed"] = time.monotonic() - t0

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(60)
    assert not worker.is_alive(), "the worker never finished"
    return box["outcome"], box["elapsed"]


def _busy(seconds):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        pass
    return "ran past the cap"


def test_a_busy_loop_on_a_worker_thread_times_out():
    outcome, elapsed = _on_a_worker(
        lambda: _with_timeout(lambda: _busy(20), seconds=1))
    assert isinstance(outcome, TimeoutError), outcome
    assert elapsed < 3, f"cap fired late ({elapsed:.1f}s)"


def test_long_sympy_work_on_a_worker_thread_times_out():
    import sympy

    x, y = sympy.symbols("x y")

    def expanding():
        t0 = time.monotonic()
        n = 10
        while time.monotonic() - t0 < 20:
            sympy.expand((x + y + 1) ** n)
            n += 1
        return "ran past the cap"

    outcome, elapsed = _on_a_worker(lambda: _with_timeout(expanding, 1))
    assert isinstance(outcome, TimeoutError), outcome
    assert elapsed < 4, f"cap fired late ({elapsed:.1f}s)"


def test_a_worker_cap_passes_through_a_library_except_exception():
    def swallowing():
        t0 = time.monotonic()
        while time.monotonic() - t0 < 20:
            try:
                sum(range(200000))
            except Exception:
                pass
        return "never"

    outcome, elapsed = _on_a_worker(lambda: _with_timeout(swallowing, 1))
    assert isinstance(outcome, TimeoutError), outcome
    assert elapsed < 3


def test_guarded_code_on_a_worker_can_catch_the_in_flight_expiry():
    def acting():
        try:
            _busy(20)
        except _WallClockExpired:
            return "degraded"
        return "ran past the cap"

    outcome, elapsed = _on_a_worker(lambda: _with_timeout(acting, 1))
    assert outcome == "degraded"
    assert elapsed < 3


def test_a_finished_worker_guard_leaves_nothing_behind():
    # a call that returns well inside its cap, many times over, must
    # leave no expiry pending to land in the code that runs after it
    def many_then_busy():
        for _ in range(200):
            assert _with_timeout(lambda: sum(range(100)), 1) == 4950
        _busy(1.5)
        return "clean"

    outcome, _ = _on_a_worker(many_then_busy)
    assert outcome == "clean", outcome


def test_an_inner_worker_cap_does_not_cancel_the_outer_one():
    def inner_then_long():
        try:
            _with_timeout(lambda: _busy(20), 1)
        except TimeoutError:
            pass
        return _busy(20)

    outcome, elapsed = _on_a_worker(
        lambda: _with_timeout(inner_then_long, 2))
    assert isinstance(outcome, TimeoutError), outcome
    assert elapsed < 4, f"outer cap fired late ({elapsed:.1f}s)"


def test_an_inner_worker_cap_never_outlives_the_outer_deadline():
    # the outer deadline lands inside the inner guard, whose handler
    # swallows the TimeoutError; the outer cap must still fire after
    def swallow_inner_then_long():
        try:
            _with_timeout(lambda: _busy(20), 10)
        except TimeoutError:
            pass
        return _busy(20)

    outcome, elapsed = _on_a_worker(
        lambda: _with_timeout(swallow_inner_then_long, 1))
    assert isinstance(outcome, TimeoutError), outcome
    assert elapsed < 3, f"outer cap fired late ({elapsed:.1f}s)"


def test_a_worker_expiry_landing_in_finalization_still_caps():
    def hungry_finalizer():
        try:
            yield 1
        finally:
            _busy(1.5)

    def guarded():
        g = hungry_finalizer()
        next(g)
        del g
        gc.collect()        # close() runs; the 1s cap expires inside it
        return _busy(4.0)   # where a re-delivered expiry must land

    leaked = []
    prior = sys.unraisablehook
    sys.unraisablehook = lambda u: leaked.append(u.exc_value)
    try:
        outcome, elapsed = _on_a_worker(lambda: _with_timeout(guarded, 1))
    finally:
        sys.unraisablehook = prior
    assert isinstance(outcome, TimeoutError), \
        f"the cap was lost in finalization ({elapsed:.1f}s, {outcome!r})"
    assert elapsed < 4.0, f"cap fired late ({elapsed:.1f}s)"
    assert not any(isinstance(e, _WallClockExpired) for e in leaked), \
        "the guard's own expiry leaked as an unraisable report"


def test_a_worker_guard_restores_the_unraisable_hook():
    before = sys.unraisablehook
    outcome, _ = _on_a_worker(lambda: _with_timeout(lambda: 1, 1))
    assert outcome == 1
    assert sys.unraisablehook is before


def test_concurrent_worker_guards_cap_only_their_own_thread():
    # two threads, one capped at 1s and one at 10s doing 2s of work:
    # the short cap must not land in the other thread
    results = {}

    def short():
        results["short"] = _on_a_worker(
            lambda: _with_timeout(lambda: _busy(20), 1))

    def long_enough():
        results["long"] = _on_a_worker(
            lambda: _with_timeout(lambda: _busy(2) and "finished", 10))

    threads = [threading.Thread(target=short),
               threading.Thread(target=long_enough)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert isinstance(results["short"][0], TimeoutError)
    assert results["long"][0] == "finished"


def test_a_long_mcp_tool_call_returns_instead_of_hanging(monkeypatch):
    # the MCP server runs a tool on a worker thread; a derive stage
    # that would run for 20s per attempt must be cut at the cap and
    # the claim settled by the remaining evidence
    pytest.importorskip("mcp")
    import anyio

    from mathema.interfaces.mcp.server import build_server
    from mathema.symbolic import _proof_support

    entered = []

    def slow_decision(*args, **kwargs):
        entered.append(threading.current_thread() is threading.main_thread())
        _busy(20)
        return _proof_support.ProofResult("proven")

    monkeypatch.setattr(_proof_support, "_decide_relation", slow_decision)
    monkeypatch.setattr(_proof_support, "FAST_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(_proof_support, "EXTENSIVE_TIMEOUT_SECONDS", 1)

    server = build_server()

    async def call():
        return await server.call_tool("adjudicate_target", {
            "target": "relpkg.geometry:doubled",
            "claims": ["for x in [-10, 10], f(x) == 2*x"],
            "root": DATA})

    t0 = time.monotonic()
    result = anyio.run(call)
    elapsed = time.monotonic() - t0

    assert entered and not any(entered), "the stage ran on the main thread"
    assert elapsed < 15, f"the tool call ran {elapsed:.0f}s"
    payload = json.loads(result.content[0].text)
    row = next(c for c in payload["claims"]
               if c["claim"] == "f_x_eq_2_x")
    assert row["route"] == "probe", row
    assert row["reason"] == "derive-gap-empirical", row
