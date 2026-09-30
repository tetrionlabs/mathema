# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_domain()` reads a function's policy claims: a `raises` row
rejects the missing or absent input at entry with a `MissingValueError`
naming the parameter and the member; a `drops` or `propagates` row is
checked at exit, by counting the output's no-value slots; `converts` and
`introduces` enforce nothing. Opt-in, like every enforcement."""
import math
from typing import Optional

import pytest

import mathema
from mathema import MissingValueError, claims_decorator, enforce_domain


@enforce_domain()
@claims_decorator("absent(f, x) raises(TypeError)")
def root(x: Optional[float]) -> float:
    return math.sqrt(x)


@enforce_domain()
@claims_decorator("missing(f, xs, null) raises(ValueError)")
def total(xs: list) -> float:
    return sum(v for v in xs if v is not None)


@enforce_domain()
@claims_decorator("missing(f, x) propagates")
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@enforce_domain()
@claims_decorator("missing(f, x) drops")
def scaled(x: float) -> float:
    return 2.0 * x


@enforce_domain()
@claims_decorator("missing(f, x) converts")
def to_none(x: float) -> Optional[float]:
    return 2.0 * x


def test_a_raising_policy_rejects_the_input_at_entry():
    with pytest.raises(MissingValueError) as err:
        root(None)
    assert str(err.value) == ("root(): x = None: raised by enforce_domain before f "
                              "ran; the stated policy is absent(f, x) raises(TypeError)")
    assert root(4.0) == 2.0


def test_a_member_policy_rejects_only_its_member():
    with pytest.raises(MissingValueError) as err:
        total([1.0, None])
    assert str(err.value) == ("total(): xs = [1.0, null] holds a null slot: raised by "
                              "enforce_domain before f ran; the stated policy is "
                              "missing(f, xs, null) raises(ValueError)")
    assert math.isnan(total([1.0, float("nan")]))


def test_propagation_is_checked_at_exit():
    with pytest.raises(MissingValueError) as err:
        clamp01(float("nan"))
    assert str(err.value) == ("clamp01(): at x = nan f returned 1.0, dropping the "
                              "hole, but its policy says propagates (missing(f, x) "
                              "propagates)")
    assert clamp01(0.5) == 0.5


def test_a_drop_is_checked_at_exit():
    with pytest.raises(MissingValueError):
        scaled(float("nan"))


def test_converts_enforces_nothing():
    assert math.isnan(to_none(float("nan")))


def test_a_missing_value_error_is_a_domain_error():
    assert issubclass(MissingValueError, mathema.DomainError)
