# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function wrapped by a decorator written as a class (an object with
`__call__`) is adjudicated as the wrapped function only when the
instance's `__call__` is read and hands its arguments to the wrapped
function and returns the result unchanged; any other instance that
wraps a function is declined with a reason, never adjudicated as the
inner function and never an exception."""
import functools

import pytest

import mathema


class Logged:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args)


class Shifted:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args) + 1


class Updated:
    def __init__(self, fn):
        functools.update_wrapper(self, fn)
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args)


class Doubler:
    def __call__(self, x: float) -> float:
        return 2 * x


@Logged
def logged_double(x: float) -> float:
    return 2 * x


@Shifted
def shifted_double(x: float) -> float:
    return 2 * x


@Updated
def updated_double(x: float) -> float:
    return 2 * x


NONNEG = "for x in [0, 1], f(x) >= 0"


@pytest.mark.needs_full_proof_budget
def test_a_pass_through_class_decorator_is_adjudicated_as_the_wrapped_function():
    (p,) = mathema.check_conjectures(logged_double, [mathema.claim(NONNEG)])
    assert p.verdict == "proven"


def test_a_pass_through_class_decorator_is_falsified_as_the_wrapped_function_is():
    (p,) = mathema.check_conjectures(
        logged_double, [mathema.claim("for x in [1, 2], f(x) < 0")])
    assert p.verdict == "falsified"


def test_a_decorator_that_changes_the_result_is_declined_with_a_reason():
    (p,) = mathema.check_conjectures(shifted_double, [mathema.claim(NONNEG)])
    assert p.verdict == "skipped"
    assert "__call__" in p.note
    assert "not read through" in p.note
    assert p.statement


@pytest.mark.needs_full_proof_budget
def test_a_class_decorator_that_sets_wrapped_is_adjudicated_as_the_wrapped_function():
    (p,) = mathema.check_conjectures(updated_double, [mathema.claim(NONNEG)])
    assert p.verdict == "proven"


def test_a_callable_object_with_its_own_body_is_still_adjudicated():
    (p,) = mathema.check_conjectures(Doubler(), [mathema.claim(NONNEG)])
    assert p.verdict == "holds"
