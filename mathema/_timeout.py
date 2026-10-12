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
import heapq
import itertools
import os
import signal
import sys
import threading
import time


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

_EXPIRED = "exceeded the wall-clock cap"

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
        Run func with a wall-clock cap of `seconds`.

    Raises:
        TimeoutError: func was still running when the cap expired.

    Notes:
        A sympy.solve or .equals() call can hang on an equation with no
        closed-form answer. Inside func the expiry is the
        BaseException `_WallClockExpired`; this boundary converts it to
        TimeoutError. On the main thread of a POSIX process the cap is
        a SIGALRM interval timer; on any other thread, or without
        SIGALRM, a watchdog thread raises the expiry in the guarded
        thread (see `_with_watchdog`). The default is a fallback only;
        real call sites pass their own value.
    """
    if (not hasattr(signal, "SIGALRM")
            or threading.current_thread() is not threading.main_thread()):
        return _with_watchdog(func, seconds)

    def _handler(signum, frame):
        # a BaseException, deliberately: the alarm fires inside
        # arbitrary library code (sympy's solve internals carry their
        # own broad `except Exception` blocks), and an Exception-class
        # timeout raised there can be swallowed by the library and the
        # computation carries on unguarded; a live 35s+ hang under a
        # 15s cap traced to exactly that. BaseException passes through
        # `except Exception`; the boundary below converts it to the
        # TimeoutError every caller already handles.
        raise _WallClockExpired(_EXPIRED)

    try:
        previous = signal.signal(signal.SIGALRM, _handler)
    except ValueError:
        return _with_watchdog(func, seconds)
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
        if (isinstance(unraisable.exc_value, _WallClockExpired)
                and threading.current_thread() is threading.main_thread()):
            signal.setitimer(signal.ITIMER_REAL, 0.05)
            return
        prior_hook(unraisable)

    sys.unraisablehook = _rearm_swallowed_alarm
    signal.setitimer(signal.ITIMER_REAL, effective)
    try:
        try:
            return func()
        finally:
            # an alarm already pending as the timer is disarmed is
            # delivered here, inside the boundary, so it too becomes
            # the TimeoutError below
            signal.setitimer(signal.ITIMER_REAL, 0)
    except _WallClockExpired as e:
        raise TimeoutError(str(e)) from None
    finally:
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


class _Guard:
    """Intent:
        One watchdog cap: the thread it guards, the monotonic deadline,
        whether it can still fire, whether an expiry has been raised
        in its thread, and whether its bookkeeping (stack entry, hook
        count) has been released.
    """
    __slots__ = ("thread_id", "deadline", "armed", "fired", "released")

    def __init__(self, thread_id: int, deadline: float):
        self.thread_id = thread_id
        self.deadline = deadline
        self.armed = True
        self.fired = False
        self.released = False


# Shared watchdog state, all of it guarded by _WATCH: the heap of
# (deadline, sequence, guard) entries the watchdog thread sleeps on,
# the per-thread stacks of nested guards, and the unraisable hook's
# install count.
_WATCH = threading.Condition()
_HEAP: list = []
_SEQUENCE = itertools.count()
_STACKS: dict = {}
_watchdog: threading.Thread | None = None
_hook_users = 0
_hook_prior = None


def _raise_in_thread(thread_id: int, exc) -> None:
    """Intent:
        Schedule `exc` (a class, or None to clear) to be raised in the
        thread `thread_id` at its next bytecode boundary, through
        CPython's PyThreadState_SetAsyncExc. Only one exception can be
        pending per thread; a new one replaces it.
    """
    import ctypes
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        None if exc is None else ctypes.py_object(exc))


def _watchdog_available() -> bool:
    """Intent:
        Whether this interpreter can raise an exception in another
        thread: CPython with ctypes.
    """
    if sys.implementation.name != "cpython":
        return False
    try:
        import ctypes
    except ImportError:
        return False
    return hasattr(ctypes, "pythonapi")


def _fire(guard: _Guard) -> None:
    """Intent:
        Raise the expiry in the guard's thread if the guard is still
        armed. Called with _WATCH held.
    """
    if guard.armed:
        guard.fired = True
        _raise_in_thread(guard.thread_id, _WallClockExpired)


def _schedule(guard: _Guard) -> None:
    """Intent:
        Put the guard on the watchdog's heap at its deadline, starting
        the watchdog thread on first use. Called with _WATCH held.
    """
    global _watchdog
    heapq.heappush(_HEAP, (guard.deadline, next(_SEQUENCE), guard))
    if _watchdog is None or not _watchdog.is_alive():
        _watchdog = threading.Thread(target=_watch, name="mathema-deadline",
                                     daemon=True)
        _watchdog.start()
    _WATCH.notify()


def _watch() -> None:
    """Intent:
        The watchdog loop: sleep until the earliest armed deadline,
        then raise the expiry in that guard's thread.
    """
    with _WATCH:
        while True:
            while _HEAP and not _HEAP[0][2].armed:
                heapq.heappop(_HEAP)
            if not _HEAP:
                _WATCH.wait()
                continue
            wait = _HEAP[0][0] - time.monotonic()
            if wait > 0:
                _WATCH.wait(wait)
                continue
            _fire(heapq.heappop(_HEAP)[2])


def _refire_swallowed_expiry(unraisable) -> None:
    """Intent:
        The unraisable hook installed while any watchdog guard is
        armed. An expiry raised inside a finalizer cannot propagate and
        is reported here instead; when it belongs to a thread with an
        armed guard the report is dropped and the expiry is raised
        again 50ms later, in code that can propagate it. Every other
        report goes to the hook that was installed before.
    """
    if isinstance(unraisable.exc_value, _WallClockExpired):
        with _WATCH:
            stack = _STACKS.get(threading.get_ident())
            if stack:
                guard = stack[-1]
                guard.deadline = time.monotonic() + 0.05
                _schedule(guard)
                return
    prior = _hook_prior or sys.__unraisablehook__
    prior(unraisable)


def _arm(seconds) -> _Guard:
    """Intent:
        Arm a watchdog guard on the calling thread, `seconds` from now
        and never past the deadline of a guard it is nested in, and
        make sure the unraisable hook is installed.
    """
    global _hook_users, _hook_prior
    thread_id = threading.get_ident()
    deadline = time.monotonic() + float(seconds)
    with _WATCH:
        stack = _STACKS.setdefault(thread_id, [])
        if stack:
            deadline = min(deadline, stack[-1].deadline)
        guard = _Guard(thread_id, deadline)
        stack.append(guard)
        if sys.unraisablehook is not _refire_swallowed_expiry:
            _hook_prior = sys.unraisablehook
            sys.unraisablehook = _refire_swallowed_expiry
        _hook_users += 1
        _schedule(guard)
    return guard


def _disarm(guard: _Guard) -> None:
    """Intent:
        Stop the guard from firing, release it and every guard still
        nested above it on its thread's stack, and clear any expiry
        still pending in the thread. The last release restores the
        unraisable hook. Safe to call again after an interrupted call.
    """
    global _hook_users, _hook_prior
    with _WATCH:
        guard.armed = False
        if guard.released:
            return
        stack = _STACKS.get(guard.thread_id, [])
        above = stack[stack.index(guard):] if guard in stack else [guard]
        pending = any(g.fired for g in stack)
        for g in above:
            g.armed = False
            if g in stack:
                stack.remove(g)
            if not g.released:
                g.released = True
                _hook_users -= 1
        if pending:
            _raise_in_thread(guard.thread_id, None)
        if not stack:
            _STACKS.pop(guard.thread_id, None)
        if _hook_users <= 0:
            _hook_users = 0
            if sys.unraisablehook is _refire_swallowed_expiry:
                sys.unraisablehook = _hook_prior
            _hook_prior = None


def _fire_overdue(thread_id: int) -> None:
    """Intent:
        Raise the expiry again for the innermost guard still armed on
        the thread if its deadline has passed, so code that handled an
        inner guard's TimeoutError is still stopped by the enclosing
        guard.
    """
    with _WATCH:
        stack = _STACKS.get(thread_id)
        if stack and stack[-1].deadline <= time.monotonic():
            _fire(stack[-1])


def _with_watchdog(func, seconds):
    """Intent:
        `_with_timeout` for a thread that cannot take SIGALRM: a
        watchdog thread raises `_WallClockExpired` in this thread at
        the deadline, and this boundary converts it to TimeoutError.

    Notes:
        The expiry is delivered at the guarded thread's next bytecode
        boundary, so pure-Python work (nearly all of sympy) is cut at
        the deadline, but a single long C-level call (a big-integer
        gcd, `time.sleep`, a blocking read) runs to its end before the
        expiry lands. Outside CPython there is no way to raise in
        another thread, and func runs uncapped.
    """
    if not _watchdog_available():
        return func()
    guard = _arm(seconds)
    try:
        try:
            return func()
        finally:
            _disarm(guard)
    except _WallClockExpired:
        _disarm(guard)
        raise TimeoutError(_EXPIRED) from None
    finally:
        _fire_overdue(guard.thread_id)


def _reset_after_fork() -> None:
    """Intent:
        A forked child has none of the parent's threads: start it with
        no watchdog, no guards and a fresh condition.
    """
    global _WATCH, _watchdog, _hook_users, _hook_prior
    _WATCH = threading.Condition()
    _HEAP.clear()
    _STACKS.clear()
    _watchdog = None
    if _hook_users and sys.unraisablehook is _refire_swallowed_expiry:
        sys.unraisablehook = _hook_prior
    _hook_users = 0
    _hook_prior = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)
