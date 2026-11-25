# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Raise-reading cases: instance wrappers."""
import functools

NEG = "for x in [-5, -1], "
D = {"x": (-5, -1)}


def _p1(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def _p2(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def _p3(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


class Shadow:
    fn = property(lambda self: (lambda x: 0.0))

    def __init__(self, fn):
        self.__dict__["fn"] = fn
        functools.update_wrapper(self, fn)
        self.__name__ = "shadow_" + fn.__name__

    def __call__(self, x):
        return self.fn(x)


class GetAttr:
    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)
        self.__name__ = "getattr_" + fn.__name__

    def __getattribute__(self, name):
        if name == "fn":
            return lambda x: 0.0
        return object.__getattribute__(self, name)

    def __call__(self, x):
        return self.fn(x)


class Returns0:
    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)
        self.__name__ = "ret0_" + fn.__name__

    def __call__(self, x):
        return 0.0


CASES = [
    (Shadow(_p1), NEG + "raises(f(x), TypeError)", ("f(x)", "TypeError", D)),
    (GetAttr(_p2), NEG + "raises(f(x), TypeError)", ("f(x)", "TypeError", D)),
    (Returns0(_p3), NEG + "raises(f(x), TypeError)", ("f(x)", "TypeError", D)),
]
