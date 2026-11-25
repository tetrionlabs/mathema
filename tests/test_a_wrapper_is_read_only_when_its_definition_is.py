# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A decorator may bind a wrapper under the function's name, and calling
the name runs the wrapper: what derive reads must be what the wrapper
does. The function's own body is read when the decorator returned the
function itself, and for a wrapper whose definition is read (the
`functools.lru_cache` and `functools.cache` wrappers, which call the
function and return or raise what it does). Any other wrapper that
links the function as `__wrapped__` (`functools.wraps`) leaves derive
reading nothing, with a reason naming the wrapper, and the claim is
decided by running it."""
import functools

import pytest

from mathema.conjecture import check_conjectures, claim

_REGISTERED: list = []


def swallow(fn):
    @functools.wraps(fn)
    def swallowing(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError:
            return 0.0
    return swallowing


def doubled(fn):
    @functools.wraps(fn)
    def doubling(*args, **kwargs):
        return 2 * fn(*args, **kwargs)
    return doubling


def register(fn):
    _REGISTERED.append(fn)
    return fn


@swallow
def swallowed_raise(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


@doubled
def doubled_value(x: float) -> float:
    return x + 1


@register
def registered_value(x: float) -> float:
    return x + 1


@functools.lru_cache(maxsize=None)
def cached_value(x: float) -> float:
    return x + 1


@functools.cache
def cached_raise(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


class Holder:
    @staticmethod
    def static_value(x: float) -> float:
        return x + 1


def _row(fn, text: str, route: str = "best"):
    (row,) = check_conjectures(fn, [claim(text, route=route)])
    return row


@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_raise_a_wrapper_catches_is_not_proven(route):
    assert swallowed_raise(-2.0) == 0.0
    row = _row(swallowed_raise, "for x in [-5, -1], raises(f(x), ValueError)", route)
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)
    if route == "best":
        assert row.verdict == "falsified", (row.verdict, row.route, row.sketch)


@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_value_a_wrapper_changes_is_not_proven(route):
    assert doubled_value(1.0) == 4.0
    row = _row(doubled_value, "for x in [0, 5], f(x) == x + 1", route)
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)
    if route == "best":
        assert row.verdict == "falsified", (row.verdict, row.route, row.sketch)


def test_the_refusal_names_the_wrapper():
    row = _row(doubled_value, "for x in [0, 5], f(x) == x + 1", "derive")
    assert "doubling" in (row.note or "") + (row.sketch or ""), (row.note, row.sketch)


@pytest.mark.parametrize("fn", [registered_value, cached_value, Holder.static_value],
                         ids=lambda f: getattr(f, "__name__", "fn"))
def test_a_function_bound_as_itself_or_under_a_read_wrapper_is_proven(fn):
    row = _row(fn, "for x in [0, 5], f(x) == x + 1", "derive")
    assert row.verdict == "proven", (row.verdict, row.route, row.sketch, row.note)


def test_a_raise_under_a_cache_wrapper_is_proven():
    row = _row(cached_raise, "for x in [-5, -1], raises(f(x), ValueError)", "derive")
    assert row.verdict == "proven", (row.verdict, row.route, row.sketch, row.note)
