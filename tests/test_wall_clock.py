# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Wall-clock integrity on the FAST path: work sympy can run unbounded
on, a limit over an integral it cannot close, lift-time cosmetic
simplification of a pathological unroll, must return promptly with
an honest undecided/unliftable, never hang. The corpus recorded a
4.5-hour .equals() hang and >90-second fast-path hangs against an
older pin; these pin the capped behavior."""
import time

from mathema.claims import check_conjectures, claim


def test_hostile_lim_over_an_unclosable_integral_is_capped():
    # the lowering-time integral evaluation and the limit computation
    # each run under the fast cap now; a shape sympy cannot close
    # comes back unknown within a small multiple of the cap
    def carrier(a):
        return a
    t0 = time.time()
    (r,) = check_conjectures(carrier, [claim(
        "lim(integrate(exp(-x**2/a**2)*cos(x**3+x)/(1+x**4), x, 0, 50)/a, "
        "a, oo) >= 0", route="derive")])
    elapsed = time.time() - t0
    assert r.verdict in ("unknown", "skipped")
    assert elapsed < 30.0, f"fast path took {elapsed:.1f}s"


def test_symbolic_bound_sum_over_an_unliftable_body_returns_promptly():
    # corpus shape that hung the fast attempt >90s at an older pin
    def binom_pmf(n, k, p):
        from math import comb
        return comb(int(n), int(k)) * p ** k * (1 - p) ** (n - k)
    t0 = time.time()
    (r,) = check_conjectures(binom_pmf, [claim(
        "for n in [1,20] subset Z, p in [0.1,0.9], "
        "Sum(f(n,k,p), k, 0, n) == 1", route="derive")])
    elapsed = time.time() - t0
    assert r.verdict in ("unknown", "skipped")
    assert elapsed < 30.0, f"fast path took {elapsed:.1f}s"


def test_budget_env_vars_seed_the_caps(tmp_path):
    # the MATHEMA_FAST_TIMEOUT / MATHEMA_EXTENSIVE_TIMEOUT knobs, read
    # once at import (the MATHEMA_UNICODE pattern)
    import os
    import subprocess
    import sys
    env = dict(os.environ, MATHEMA_FAST_TIMEOUT="9",
               MATHEMA_EXTENSIVE_TIMEOUT="44",
               PYTHONPATH=os.path.dirname(os.path.dirname(
                   os.path.abspath(__file__))))
    r = subprocess.run(
        [sys.executable, "-c",
         "from mathema._timeout import FAST_TIMEOUT_SECONDS, "
         "EXTENSIVE_TIMEOUT_SECONDS; "
         "print(FAST_TIMEOUT_SECONDS, EXTENSIVE_TIMEOUT_SECONDS)"],
        capture_output=True, text=True, env=env)
    assert r.stdout.split() == ["9", "44"], r.stdout + r.stderr


def test_extensive_reaches_the_lowering_cap():
    # try_prove's lowering (limit/antiderivative evaluation inside law
    # parsing) runs under the tier's own budget, not always the fast
    # one, the seam the Catalan asymptotic limit needed
    from mathema._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                                  FAST_TIMEOUT_SECONDS, lowering_cap,
                                  tier_budget)
    assert lowering_cap() == FAST_TIMEOUT_SECONDS
    with tier_budget(EXTENSIVE_TIMEOUT_SECONDS):
        assert lowering_cap() == EXTENSIVE_TIMEOUT_SECONDS
    assert lowering_cap() == FAST_TIMEOUT_SECONDS


def test_multi_radical_claim_completes_promptly():
    # the corpus's live 40s+ hang family: a sum of radicals whose
    # derivative sends solve() into big-integer polynomial gcd;
    # C-level arithmetic no alarm can interrupt. The critical-point
    # hint pass must skip the family (hints are best-effort), and the
    # whole claim must complete on a real budget.
    import time

    def minkowski_p3_margin(a, b, c, d):
        lhs = (a**3 + b**3) ** (1.0/3.0) + (c**3 + d**3) ** (1.0/3.0)
        rhs = ((a + c)**3 + (b + d)**3) ** (1.0/3.0)
        return lhs - rhs

    from mathema.conjecture import check_conjectures, claim
    t0 = time.time()
    (p,) = check_conjectures(minkowski_p3_margin, [claim(
        "for a in [0.1,10], b in [0.1,10], c in [0.1,10], d in [0.1,10], "
        "f(a,b,c,d) >= 0", route="derive")], extensive=True)
    elapsed = time.time() - t0
    assert elapsed < 90, f"took {elapsed:.0f}s"
    assert p.verdict in ("holds", "proven", "unknown"), (p.verdict, p.note)


def test_alarm_survives_library_exception_swallowing():
    # the alarm's in-flight exception is a BaseException: a library's
    # own broad `except Exception` between the handler and our
    # boundary must not absorb it
    import time

    from mathema._timeout import _with_timeout

    def swallowing():
        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                sum(range(200000))
            except Exception:
                pass
        return "never"

    t0 = time.time()
    try:
        _with_timeout(swallowing, 1)
        raise AssertionError("cap never fired")
    except TimeoutError:
        pass
    assert time.time() - t0 < 5


def test_alarm_landing_in_generator_finalization_still_caps():
    # the alarm's raise can land inside a generator's GC finalization
    # (sympy's caches close generators constantly), where the
    # interpreter cannot propagate it: it would be reported as
    # "Exception ignored in ..." and dropped, losing the cap and
    # printing what reads as a crash. The guard must swallow exactly
    # that report and re-arm, so the cap still fires in code that can
    # propagate it and nothing leaks to the surrounding hook.
    import gc
    import sys

    from mathema._timeout import _WallClockExpired, _with_timeout

    def hungry_finalizer():
        try:
            yield 1
        finally:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.5:
                pass

    def guarded():
        g = hungry_finalizer()
        next(g)
        del g
        gc.collect()        # close() runs; the 1s alarm fires inside it
        t0 = time.monotonic()
        while time.monotonic() - t0 < 4.0:
            pass            # where a re-armed cap must land
        return "ran past the cap"

    leaked = []
    prior = sys.unraisablehook
    sys.unraisablehook = lambda u: leaked.append(u.exc_value)
    try:
        t0 = time.monotonic()
        try:
            result = _with_timeout(guarded, seconds=1)
        except TimeoutError:
            result = "timed out"
        elapsed = time.monotonic() - t0
    finally:
        sys.unraisablehook = prior
    assert result == "timed out", \
        f"the cap was lost in finalization ({elapsed:.1f}s, {result!r})"
    assert elapsed < 4.0, f"cap fired late ({elapsed:.1f}s)"
    assert not any(isinstance(e, _WallClockExpired) for e in leaked), \
        "the guard's own alarm leaked as an unraisable report"


def test_other_unraisables_delegate_to_the_surrounding_hook():
    import gc
    import sys

    from mathema._timeout import _with_timeout

    seen = []
    prior = sys.unraisablehook
    sys.unraisablehook = lambda u: seen.append(str(u.exc_value))
    try:
        def noisy():
            class Boom:
                def __del__(self):
                    raise ValueError("boom")
            b = Boom()
            del b
            gc.collect()
            return "done"
        assert _with_timeout(noisy, seconds=5) == "done"
    finally:
        sys.unraisablehook = prior
    assert any("boom" in s for s in seen)


def test_unraisable_hook_is_scoped_to_the_guard():
    import sys

    from mathema._timeout import _with_timeout

    before = sys.unraisablehook
    assert _with_timeout(lambda: 1, seconds=1) == 1
    assert sys.unraisablehook is before
