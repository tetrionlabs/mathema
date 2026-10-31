# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A wall-clock cap on a worker thread leaves no expiry signal behind
it: after one fires and is cancelled, a traced run on the main thread
still finishes. On CPython 3.11 an expiry cancelled by clearing the
thread's pending exception leaves the interpreter's pending-exception
signal raised with nothing to clear it, and opcode tracing then spins."""
import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent("""
    import sys, threading, time
    from mathema import _timeout

    def worker():
        try:
            _timeout._with_watchdog(
                lambda: [time.sleep(0.001) for _ in range(10 ** 6)], 0.1)
        except TimeoutError:
            pass

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    def target(n):
        s = 0
        for i in range(n):
            s += i
        return s

    def local(frame, event, arg):
        return local

    def tracer(frame, event, arg):
        if frame.f_code is target.__code__:
            frame.f_trace_opcodes = True
            return local
        return None

    sys.settrace(tracer)
    result = target(1000)
    sys.settrace(None)
    print(result)
""")


def test_a_traced_run_after_a_worker_cap_fires_finishes():
    done = subprocess.run([sys.executable, "-c", _SCRIPT],
                          capture_output=True, text=True, timeout=60)
    assert done.stdout.strip() == "499500", done.stderr
