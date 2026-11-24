# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions that raise on part of their domain: plain, behind
wrappers, behind guards, with causes and with messages that are
themselves expressions."""
import functools
import math
from typing import Annotated
from unittest import mock

from mathema.authoring import enforce_domain, enforce_structure
from mathema.types import Finite


def plain(x, y=None):
    if x < 0:
        raise ValueError("n")
    return x


def pass_through(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


def negating(fn):
    @functools.wraps(fn)
    def wrapper(x):
        return fn(-x)
    return wrapper


def catching(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError:
            return 0
    return wrapper


def catch_arithmetic(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ArithmeticError:
            return 0
    return wrapper


@pass_through
def wrapped(x):
    if x < 0:
        raise ValueError("n")
    return x


@pass_through
@pass_through
def wrapped_twice(x):
    if x < 0:
        raise ValueError("n")
    return x


@functools.lru_cache(maxsize=None)
def cached(x):
    if x < 0:
        raise ValueError("n")
    return x


@negating
def negated(x):
    if x < 0:
        raise ValueError("n")
    return x


@catching
def swallowed(x):
    if x < 0:
        raise ValueError("n")
    return x


@catch_arithmetic
def overflow_caught(x):
    return math.exp(x * 1000)


MOCK_CAUSE = mock.Mock(spec=KeyError)


def cause_mock(x):
    if x < 0:
        raise ValueError("n") from MOCK_CAUSE
    return x


def cause_instance(x):
    if x < 0:
        raise ValueError("n") from KeyError("k")
    return x


def cause_int(x):
    if x < 0:
        raise ValueError("n") from 1
    return x


def chain_negated(x):
    if x < 0:
        raise ValueError(0 < -x < "a")
    return x


def chain_short_circuits(x):
    if x < 0:
        raise ValueError(x > 0 > "a")
    return x


def chain_with_zero(x):
    if x <= 0:
        raise ValueError(0 <= x < "a")
    return x


@enforce_domain({"y": "[0, 2] \\ {None}"})
def guard_refuses_none(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "[0, 2] \\ {nan}"})
def guard_refuses_nan(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_structure()
def structure_finite(x: Annotated[float, Finite], y):
    if x < 0:
        raise KeyError("n")
    return x


def reads_second_in_branch(x, y):
    if x < 0:
        if y > 0:
            raise ValueError("n")
        raise ValueError("m")
    return x


def ignores_second(x, y):
    if x < 0:
        raise ValueError("n")
    return x


@enforce_structure()
def structure_value(x: Annotated[float, Finite]):
    return x + 1


def halve(x: float) -> float:
    return x / 2


def name_of(fn):
    return fn.__name__
