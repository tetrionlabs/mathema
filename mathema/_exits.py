# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `SystemExit` from the function under test, read as the raise it is.

`SystemExit` derives from `BaseException`, not `Exception`, so every
handler that records a raise from the function under test would let it
pass and it would end the caller's process with the function's exit
code. `call` and `exiting_as_raise` turn it into `ExitRaised`, which is
both a `SystemExit` (a `raises(..., SystemExit)` claim matches it, and
it keeps the exit code) and an `Exception` (every handler records it
like any other raise). Any other `BaseException` (`KeyboardInterrupt`,
the wall-clock alarm) passes through unchanged.
"""
from __future__ import annotations


class ExitRaised(SystemExit, Exception):
    """A `SystemExit` the function under test raised, carrying its exit
    code as `code`. Its class name reads `SystemExit`, so a witness
    names the exception the function raised."""


ExitRaised.__name__ = "SystemExit"
ExitRaised.__qualname__ = "SystemExit"


def as_raise(exc: SystemExit) -> ExitRaised:
    """Intent:
        `exc` as an `ExitRaised` with the same exit code, chained to it
        and carrying its traceback; an `ExitRaised` is returned as it
        is.
    """
    if isinstance(exc, ExitRaised):
        return exc
    out = ExitRaised(exc.code)
    out.__cause__ = exc
    return out.with_traceback(exc.__traceback__)


def call(fn, *args, **kwargs):
    """Intent:
        `fn(*args, **kwargs)`, with a `SystemExit` it raises turned
        into `ExitRaised`.

    Raises:
        ExitRaised: `fn` raised `SystemExit`.
    """
    try:
        return fn(*args, **kwargs)
    except ExitRaised:
        raise
    except SystemExit as exc:
        raise as_raise(exc) from exc


def exception_name(exc: BaseException) -> str:
    """Intent:
        The name a record shows for a raise: the exception's class
        name, followed for a `SystemExit` by its exit code
        (`SystemExit (exit code 2)`).
    """
    name = type(exc).__name__
    if isinstance(exc, SystemExit):
        return f"{name} (exit code {exc.code!r})"
    return name


class _ExitsAsRaise:
    """A callable that runs its function through `call`; attributes and
    the signature are the function's own."""

    def __init__(self, fn):
        self.__wrapped__ = fn

    def __call__(self, *args, **kwargs):
        return call(self.__wrapped__, *args, **kwargs)

    def __getattr__(self, name):
        if name == "__wrapped__":
            raise AttributeError(name)
        return getattr(self.__wrapped__, name)

    def __repr__(self) -> str:
        return repr(self.__wrapped__)


def exiting_as_raise(fn):
    """Intent:
        A callable that behaves as `fn`, except that a `SystemExit` it
        raises arrives as `ExitRaised`; one this already returned is
        passed back unchanged.
    """
    if isinstance(fn, _ExitsAsRaise) or not callable(fn):
        return fn
    return _ExitsAsRaise(fn)
