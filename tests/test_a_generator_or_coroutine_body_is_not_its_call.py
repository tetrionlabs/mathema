# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Calling a generator function, a coroutine function or an async
generator function runs none of its body: the call returns a generator
or coroutine object. Derive reads a function's body as what its call
does, so it reads none of these, and a claim about such a call is
decided by running it."""
import asyncio
import inspect
import warnings

import pytest

from mathema import analyze
from mathema.conjecture import check_conjectures, claim


def generator_raise(x: float):
    if x < 0:
        raise ValueError("neg")
    yield x


async def coroutine_raise(x: float):
    if x < 0:
        raise ValueError("neg")
    return x


async def async_generator_raise(x: float):
    if x < 0:
        raise ValueError("neg")
    yield x


def generator_value(x: float) -> float:
    if x < 0:
        return x + 1
    yield x


async def coroutine_value(x: float) -> float:
    return x + 1


def plain_value(x: float) -> float:
    return x + 1


def _row(fn, text: str, route: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        (row,) = check_conjectures(fn, [claim(text, route=route)])
    return row


_RAISING = [generator_raise, coroutine_raise, async_generator_raise]
_VALUED = [generator_value, coroutine_value]


@pytest.mark.parametrize("fn", _RAISING, ids=lambda f: f.__name__)
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_raise_in_a_suspended_body_is_not_proven(fn, route):
    made = fn(-1.0)
    assert inspect.isgenerator(made) or inspect.iscoroutine(made) \
        or inspect.isasyncgen(made)
    if inspect.iscoroutine(made):
        made.close()
    row = _row(fn, "for x in [-5, -1], raises(f(x), ValueError)", route)
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)


@pytest.mark.parametrize("fn", _VALUED, ids=lambda f: f.__name__)
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_value_of_a_suspended_body_is_not_proven(fn, route):
    made = fn(-1.0)
    assert made != 0.0
    if inspect.iscoroutine(made):
        made.close()
    row = _row(fn, "for x in [-5, -1], f(x) == x + 1", route)
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)


def test_the_lift_entry_points_read_no_suspended_body():
    from mathema.symbolic import lift
    from mathema.symbolic._conditioned import lift_conditioned
    assert lift(coroutine_value, analyze(coroutine_value)) is None
    assert lift_conditioned(generator_value, analyze(generator_value),
                            {"x": (-5, -1)}) is None
    assert lift(plain_value, analyze(plain_value)) is not None
    assert asyncio.iscoroutinefunction(coroutine_value)
