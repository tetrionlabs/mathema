# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the function under test writes to `sys.stdout` and `sys.stderr`
while mathema calls it, kept off the terminal.

Inside `kept_off_terminal()` both streams are routed to the null
device for the calling thread (and the context it runs in) only: the
function can still write, flush, reach the stream's `buffer` or its
file descriptor, and nothing it writes reaches the person running
mathema. Every other thread, and the caller once the block ends, writes
to the streams as before. Output written straight to a file descriptor
the process inherited (`os.write(1, ...)`, a subprocess) is not
routed.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import sys
import threading

#: the stream the current context writes to in place of the real one,
#: None outside `kept_off_terminal`
_SINK: contextvars.ContextVar = contextvars.ContextVar("mathema_callee_sink",
                                                       default=None)
_LOCK = threading.Lock()
_STATE: dict = {"depth": 0, "saved": None, "null": None}


class _Routed:
    """A stand-in for `sys.stdout` or `sys.stderr` that writes to the
    current context's sink when one is set, else to the stream it
    replaced; every attribute is the target's own."""

    def __init__(self, stream) -> None:
        self._stream = stream

    def _target(self):
        sink = _SINK.get()
        return self._stream if sink is None else sink

    def write(self, text):
        return self._target().write(text)

    def flush(self):
        return self._target().flush()

    def __getattr__(self, name):
        return getattr(self._target(), name)


def _null():
    """Intent:
        The null device opened for writing text, opened once per
        process and kept open.
    """
    if _STATE["null"] is None:
        _STATE["null"] = open(os.devnull, "w", encoding="utf-8")
    return _STATE["null"]


def _routed(stream):
    """`stream` behind a `_Routed`, unless it is None (no stream to
    write to) or already routed."""
    if stream is None or isinstance(stream, _Routed):
        return stream
    return _Routed(stream)


@contextlib.contextmanager
def kept_off_terminal():
    """Intent:
        A context in which what the current thread writes to
        `sys.stdout` and `sys.stderr` goes to the null device. Nested
        and concurrent uses share one routing of the streams, put in
        place by the first to enter and taken down by the last to
        leave.
    """
    with _LOCK:
        if _STATE["depth"] == 0:
            _STATE["saved"] = (sys.stdout, sys.stderr)
            sys.stdout, sys.stderr = _routed(sys.stdout), _routed(sys.stderr)
        _STATE["depth"] += 1
        sink = _null()
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)
        with _LOCK:
            _STATE["depth"] -= 1
            if _STATE["depth"] == 0:
                out, err = _STATE["saved"]
                _STATE["saved"] = None
                if isinstance(sys.stdout, _Routed):
                    sys.stdout = out
                if isinstance(sys.stderr, _Routed):
                    sys.stderr = err
