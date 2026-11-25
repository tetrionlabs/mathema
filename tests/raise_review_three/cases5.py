# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Raise-reading cases: wrappers and generator shapes."""
import functools

from mathema.authoring import enforce_domain

NEG = "for x in [-5, -1], "
D = {"x": (-5, -1)}


def r(fn, exc="TypeError", text=None):
    return (fn, text or NEG + f"raises(f(x), {exc})", ("f(x)", exc, D))


@enforce_domain({"x": (0, 10)})
def guarded(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


@enforce_domain({"x": (-4.5, 10)})
def guarded_rare(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def dead_yield(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x
    if False:
        yield


def nested_yield(x: float) -> float:
    if x < 0:
        raise TypeError("neg")

    def inner():
        yield x
    return x


def genexp(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return sum(v for v in (x,))


def same(fn):
    return fn


@same
def same_obj(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def changes_args(fn):
    @functools.wraps(fn)
    def w(x):
        return fn(-x)
    return w


@changes_args
def flipped(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


@functools.lru_cache(maxsize=None)
def cached(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


class Swallow:
    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)

    def __call__(self, x):
        return self.fn(x)


class Shadow:
    """An instance whose `fn` attribute read goes through a class
    property, not the instance dict."""
    fn = property(lambda self: (lambda x: 0.0))

    def __init__(self, fn):
        self.__dict__["fn"] = fn
        functools.update_wrapper(self, fn)

    def __call__(self, x):
        return self.fn(x)


def _plain(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


handed = Swallow(_plain)
shadowed = Shadow(_plain)
partial_fn = functools.partial(_plain)


@functools.singledispatch
def dispatched(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def sets_wrapped_self(fn):
    def w(x):
        try:
            return fn(x)
        except TypeError:
            return 0.0
    w.__wrapped__ = fn
    w.__code__ = fn.__code__.replace()  # w now runs fn's own code
    return w


CASES = [
    r(guarded), r(guarded, "ValueError"), r(guarded_rare),
    r(dead_yield), r(nested_yield), r(genexp), r(same_obj), r(flipped), r(cached),
    r(handed), r(shadowed), r(partial_fn), r(dispatched),
]
