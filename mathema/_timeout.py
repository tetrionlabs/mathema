# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Wall-clock timeout helper (`_with_timeout`) and its two shared cap
constants. Stdlib-only, no dependency on anything else in the package;
this is what lets both `diagnostics.py` and `symbolic/_proof_support.py`
reach into it without creating an import cycle between them (diagnostics
imports the symbolic package; symbolic/_proof_support is documented as
leaf-level and must not import diagnostics back).
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import signal


def _seconds_from_env(name: str, default: int) -> int:
    """Intent:
        One budget constant, seeded from its environment variable the
        same way `MATHEMA_UNICODE` seeds the render mode: read once at
        import, whole seconds, floor 1. An unset or unreadable value
        keeps the default.
    """
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(float(raw))
    except ValueError:
        return default
    return max(1, value)


# Wall-clock caps for _with_timeout(), one place, reused by diagnostics.py,
# probing.py, and symbolic/_prove.py/_proof_support.py rather than each
# hardcoding its own number. MATHEMA_FAST_TIMEOUT and
# MATHEMA_EXTENSIVE_TIMEOUT (whole seconds) override the defaults for a
# whole process; the knob for a claim whose computation is long but
# finite.
FAST_TIMEOUT_SECONDS = _seconds_from_env("MATHEMA_FAST_TIMEOUT", 3)
EXTENSIVE_TIMEOUT_SECONDS = _seconds_from_env("MATHEMA_EXTENSIVE_TIMEOUT", 15)

_LOWERING_CAP: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_lowering_cap", default=None)


def lowering_cap() -> int:
    """The wall-clock cap for lowering-time sympy work (the limit and
    antiderivative evaluation inside law parsing): the active tier's
    budget when one is set, try_prove sets the extensive budget under
    `extensive=True`, so a limit that outruns the fast cap gets the
    extensive one before the claim reports unliftable, and the fast
    budget otherwise."""
    cap = _LOWERING_CAP.get()
    return FAST_TIMEOUT_SECONDS if cap is None else cap


@contextlib.contextmanager
def tier_budget(seconds: int):
    """Intent:
        Scope `lowering_cap()` to `seconds` for the enclosed work,
        how the proof entry point hands its tier's budget down to the
        lowering sites without threading a parameter through the
        recursive law parser.
    """
    token = _LOWERING_CAP.set(seconds)
    try:
        yield
    finally:
        _LOWERING_CAP.reset(token)


def _with_timeout(func, seconds: int = 5):
    """Intent:
        Run func with a wall-clock cap. POSIX only.

    Notes:
        A sympy.solve or .equals() call can hang on an equation with no
        closed-form answer. Falls back to no cap when SIGALRM is
        unavailable or this is not the main thread. The default is a
        fallback only; real call sites pass their own value.
    """
    if not hasattr(signal, "SIGALRM"):
        return func()

    def _handler(signum, frame):
        # a BaseException, deliberately: the alarm fires inside
        # arbitrary library code (sympy's solve internals carry their
        # own broad `except Exception` blocks), and an Exception-class
        # timeout raised there can be swallowed by the library and the
        # computation carries on unguarded; a live 35s+ hang under a
        # 15s cap traced to exactly that. BaseException passes through
        # `except Exception`; the boundary below converts it to the
        # TimeoutError every caller already handles.
        raise _WallClockExpired("exceeded the wall-clock cap")

    import sys
    import time

    try:
        previous = signal.signal(signal.SIGALRM, _handler)
    except ValueError:
        return func()
    # a nested cap must not silently cancel an enclosing one: the time
    # already standing on the outer alarm is remembered and restored
    # (minus what this call consumed) on the way out, so an inner
    # 3-second helper inside a 15-second guard leaves the guard armed
    outer_remaining = signal.getitimer(signal.ITIMER_REAL)[0]
    started = time.monotonic()
    # the inner cap never outlives the enclosing deadline
    effective = (min(float(seconds), outer_remaining)
                 if outer_remaining > 0 else float(seconds))

    # the alarm can land inside a finalizer (a GC-closed generator in
    # sympy's caches, typically), where the interpreter cannot
    # propagate an exception: the raise would be reported as
    # "Exception ignored in ..." with a full traceback, then dropped,
    # which both reads as a crash and silently LOSES the cap (the
    # guarded call runs on unbounded). The scoped hook swallows exactly
    # that report and re-arms the timer, so the cap fires again a
    # moment later, in code that can propagate it. Every other
    # unraisable still reaches whatever hook was already installed.
    prior_hook = sys.unraisablehook

    def _rearm_swallowed_alarm(unraisable):
        if isinstance(unraisable.exc_value, _WallClockExpired):
            signal.setitimer(signal.ITIMER_REAL, 0.05)
            return
        prior_hook(unraisable)

    sys.unraisablehook = _rearm_swallowed_alarm
    signal.setitimer(signal.ITIMER_REAL, effective)
    try:
        return func()
    except _WallClockExpired as e:
        raise TimeoutError(str(e)) from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        sys.unraisablehook = prior_hook
        signal.signal(signal.SIGALRM, previous)
        if outer_remaining > 0:
            left = outer_remaining - (time.monotonic() - started)
            # an outer deadline that already passed fires as soon as
            # its own handler is back in place
            signal.setitimer(signal.ITIMER_REAL, max(left, 0.001))


class _WallClockExpired(BaseException):
    """Intent:
        The alarm's own in-flight exception, BaseException so no
        library-internal `except Exception` can absorb it before it
        reaches `_with_timeout`'s boundary, where it becomes the
        public TimeoutError.
    """
