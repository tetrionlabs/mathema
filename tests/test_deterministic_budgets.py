# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Deterministic budgets around the decision machinery: a nested
wall-clock cap no longer cancels its enclosing deadline, the extensive
ladder has an aggregate budget, and the interval hull declines
oversized or Piecewise expressions instead of running unbounded. The
two corpus hang shapes (multi-term-radical interval refinement, and a
Sum wrapping a raise-guarded straight-line function) are pinned as
must-return-promptly fixtures."""
import os
import subprocess
import sys
import textwrap
import time


def test_nested_timeout_preserves_the_outer_deadline():
    from mathema._timeout import _with_timeout

    def outer():
        _with_timeout(lambda: 42, 1)      # inner cap comes and goes
        time.sleep(20)                    # outer cap must still fire
        return "never"

    t0 = time.monotonic()
    try:
        _with_timeout(outer, 2)
        raise AssertionError("outer deadline never fired")
    except TimeoutError:
        pass
    assert time.monotonic() - t0 < 6


def test_inner_cap_never_outlives_the_outer_deadline():
    from mathema._timeout import _with_timeout

    def outer():
        # the inner asks for far more than the outer has left
        _with_timeout(lambda: time.sleep(30), 25)
        return "never"

    t0 = time.monotonic()
    try:
        _with_timeout(outer, 2)
    except TimeoutError:
        pass
    assert time.monotonic() - t0 < 6


def test_interval_hull_declines_piecewise_and_oversized():
    import sympy

    from mathema.symbolic._proof_support import _interval_hull
    x = sympy.Symbol("x", real=True)
    box = {x: sympy.AccumBounds(0, 1)}
    pw = sympy.Piecewise((x, x > 0), (-x, True))
    assert _interval_hull(pw, box) is None
    big = sum((x + i) ** 3 for i in range(200))
    assert _interval_hull(big, box) is None
    assert _interval_hull(x + 1, box) is not None


def _run_snippet(tmp_path, body, driver, budget="3"):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    (tmp_path / "hangmod.py").write_text(textwrap.dedent(body))
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join([repo, str(tmp_path)]),
               MATHEMA_FAST_TIMEOUT="2", MATHEMA_EXTENSIVE_TIMEOUT=budget)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(driver)],
                          capture_output=True, text=True, env=env,
                          timeout=90)


def test_multi_term_radical_extensive_returns_within_budget(tmp_path):
    # the corpus's Minkowski p=3 shape: interval refinement used to
    # hang indefinitely on it (nlsat disabled or not); the per-rung
    # caps now hold across nesting and the ladder has an aggregate
    # budget, so the extensive attempt RETURNS, verdict free, hang
    # forbidden
    r = _run_snippet(tmp_path, """
        def minkowski_p3(a1: float, a2: float, b1: float, b2: float) -> float:
            lhs = (a1**3 + a2**3)**(1/3) + (b1**3 + b2**3)**(1/3)
            rhs = ((a1+b1)**3 + (a2+b2)**3)**(1/3)
            return lhs - rhs
        """, """
        from hangmod import minkowski_p3
        from mathema.conjecture import check_conjectures, claim
        (p,) = check_conjectures(minkowski_p3, [claim(
            "for a1 in [0,10], a2 in [0,10], b1 in [0,10], b2 in [0,10], "
            "f(a1,a2,b1,b2) >= 0", route="derive")], extensive=True)
        print("verdict:", p.verdict)
        """)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "verdict:" in r.stdout


def test_sum_over_raise_guarded_function_returns_promptly(tmp_path):
    # the corpus's other hang: Sum(...) wrapping a raise-guarded
    # straight-line function ran 150s+ even with the bound pinned to a
    # literal. Both the literal-bound proof and the symbolic-bound
    # attempt must return promptly (the latter may be undecided).
    r = _run_snippet(tmp_path, """
        import math

        def combinations_count(n: int, r: int) -> float:
            if n < 0:
                raise ValueError("n must be non-negative")
            if r < 0:
                raise ValueError("r must be non-negative")
            return math.factorial(n) / (math.factorial(r) * math.factorial(n - r))
        """, """
        from hangmod import combinations_count
        from mathema.conjecture import check_conjectures, claim
        (p,) = check_conjectures(combinations_count, [claim(
            "Sum(f(5,k), k, 0, 5) == 32", route="derive")])
        assert p.verdict == "proven", (p.verdict, p.note)
        (q,) = check_conjectures(combinations_count, [claim(
            "for n in [1,8] subset Z, Sum(f(n,k), k, 0, n) == 2**n",
            route="derive")])
        print("symbolic bound verdict:", q.verdict)
        """)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "symbolic bound verdict:" in r.stdout
