# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Pure wrappers around writing and pure functions, and a class-based
decorator."""
import functools

_LOG = []


def _passthrough(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        return fn(*a, **k)
    return wrapper


class _Deco:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *a):
        _LOG.append(a)
        return self.fn(*a)


@_passthrough
def w_wrapped_writer(x: float) -> float:
    _LOG.append(x)
    return x


@_passthrough
def p_wrapped_pure(x: float) -> float:
    return 2.0 * x


@_Deco
def w_class_decorated(x: float) -> float:
    return x


@functools.cache
def w_cache_writer(x: float) -> float:
    _LOG.append(x)
    return x
