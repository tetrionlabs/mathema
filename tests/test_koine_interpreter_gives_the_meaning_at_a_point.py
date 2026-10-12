# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reference interpreter: values, the three non-value classes by
stratum, refusals, and the states in which it has nothing to say."""
import math
import time

import pytest

from mathema.koine import interpret
from mathema.koine.interpret import (
    DOMAIN,
    MAX_ITERATIONS,
    OVERFLOW,
    SINGULAR,
    InterpretError,
    NoValue,
    Refusal,
    Value,
)
from tests._koine_docs import (
    LOCAL_AND_CALLS,
    RECORD,
    RECORD_BODY,
    SEQUENCE,
    at,
    doc,
    golden,
    growth,
    growth_restated,
)


def ret(expr: str, **kw):
    return doc(f"statement::return({expr}, {at()})", **kw)


def test_growth():
    assert interpret(growth(), {"x": 2.0, "r": 0.5}) == Value(3.0)
    assert interpret(growth(), [2.0, 0.5]) == Value(3.0)
    assert interpret(growth(), [2.0, -2.0]) == Refusal("raise", "ValueError")
    assert interpret(growth_restated(), [2.0, -2.0]) == Refusal("raise", "RateError")


def test_goldens():
    ema = golden("ema_first_py")
    assert interpret(ema, [[1.0, 2.0, 3.0], 0.5]) == Value(2.25)
    assert interpret(ema, [[1.0], -0.5]) == \
        Refusal("raise", "ValueError", "alpha must be nonnegative")
    tax = golden("piecewise_py")
    assert interpret(tax, [-1.0, 3.0]) == Value(0)
    assert interpret(tax, [0.25, 3.0]) == Value(0.75)
    dot = golden("dot_py")
    assert interpret(dot, [[1.0, 2.0], [3.0, 4.0]]) == Value(11.0)
    assert interpret(golden("mean_py"), [[1.0, 2.0, 6.0]]) == Value(3.0)
    assert interpret(golden("quotient_py"), [-7, 2]) == Value(-4)


def test_a_record_is_read_by_field():
    rec = doc(RECORD_BODY, params=RECORD)
    assert interpret(rec, [{"rate": 0.1, "years": 2.0}, 100.0]).value == pytest.approx(121.0)


def test_non_values_by_stratum():
    assert interpret(ret("operator::binary::division::real(x, r)"), [1.0, 0.0]) == \
        NoValue(SINGULAR, "operator::binary::division::real")
    assert interpret(ret("operator::binary::remainder::euclidean(x, r)"), [1, 0]).cls == SINGULAR
    assert interpret(ret("function::root::square(x)"), [-1.0, 0]).cls == DOMAIN
    assert interpret(ret("function::logarithm::natural(x)"), [0.0, 0]).cls == DOMAIN
    assert interpret(ret("function::special::factorial(x)"), [2.5, 0]).cls == DOMAIN
    assert interpret(ret("operator::binary::power(x, r)"), [-8.0, 0.5]).cls == DOMAIN
    assert interpret(ret("operator::binary::power(x, r)"), [0, -1]).cls == SINGULAR
    assert interpret(ret("function::exponential::natural(x)"), [1000.0, 0]).cls == OVERFLOW
    assert interpret(ret("operator::binary::multiplication(x, r)"), [1e300, 1e300]).cls == OVERFLOW


@pytest.mark.parametrize("op, a, b, want", [
    ("division::floor", -7, 2, -4), ("division::truncation", -7, 2, -3),
    ("division::euclidean", 7, -2, -3), ("remainder::floor", -7, 2, 1),
    ("remainder::truncation", -7, 2, -1), ("remainder::euclidean", -7, -2, 1),
    ("division::floor", 1.0, 0.1, 9.0), ("division::real", 7, 2, 3.5),
])
def test_the_families(op, a, b, want):
    assert interpret(ret(f"operator::binary::{op}(x, r)"), [a, b]) == Value(want)


@pytest.mark.parametrize("fn, x, want", [
    ("rounding::ties_even", 2.5, 2), ("rounding::ties_away", 2.5, 3),
    ("rounding::ties_up", -2.5, -2), ("rounding::truncation", -2.7, -2),
    ("magnitude::sign", -3.0, -1), ("root::cube", -8.0, -2.0),
])
def test_functions(fn, x, want):
    got = interpret(ret(f"function::{fn}(x)"), [x, 0])
    assert got.value == pytest.approx(want)


def test_logic_short_circuits_past_a_non_value():
    d = ret("value::conditional(operator::logic::or(operator::comparison::equal(r, 0),"
            " operator::comparison::greater(operator::binary::division::real(1, r), 0)), 1, 2)")
    assert interpret(d, [0.0, 0.0]) == Value(1)
    assert interpret(d, [0.0, -2.0]) == Value(2)


def test_calls_local_and_by_key():
    d = doc(LOCAL_AND_CALLS)
    calls = {"py:src/shapes.py#twice": lambda v: 2 * v}
    # a, b = r, x then swapped: sq(3) + twice(4) + sqrt(|4|) + 1
    assert interpret(d, [4.0, 3.0], calls).value == pytest.approx(9.0 + 8.0 + 2.0 + 1)
    with pytest.raises(InterpretError, match="no callable resolves"):
        interpret(d, [4.0, 3.0])
    by_key = ret('call::function("py:m.g", x)')

    def g(v):
        raise KeyError("nope")
    assert interpret(by_key, [1, 0], {"py:m.g": g}) == Refusal("raise", "KeyError", "'nope'")


def test_nan_compares_false_except_not_equal():
    assert interpret(ret("operator::comparison::less(x, r)"), [math.nan, 1.0]) == Value(False)
    assert interpret(ret("operator::comparison::not_equal(x, r)"),
                     [math.nan, math.nan]) == Value(True)


@pytest.mark.parametrize("d, point, message", [
    (doc(f"statement::bind(g, 1, {at()})"), [1, 2], "ended without a return"),
    (ret("value::index(xs, 5)", params=SEQUENCE), [[1.0], 0.5], "outside"),
    (ret("value::conditional(x, 1, 2)"), [1.0, 0], "boolean was expected"),
    (ret("x", params="parameter(x, kind::scalar, representation::f32)"), [1.0], "not modelled"),
    (ret("x"), [1.0], "point has 1 values for 2"),
    (ret("operator::binary::addition(x, r)"), [math.inf, 1.0], "non-finite operand"),
])
def test_not_runnable_is_an_error_not_an_outcome(d, point, message):
    with pytest.raises(InterpretError, match=message):
        interpret(d, point)


def test_a_loop_past_the_iteration_budget_has_nothing_to_say():
    counting = doc(f"statement::bind(t, 0, {at()}), "
                   f"statement::loop::range(i, 0, x, 1, [statement::update(t, "
                   f"operator::binary::addition, 1, {at()})], {at()}), "
                   f"statement::return(t, {at()})")
    assert interpret(counting, [100.0, 0.0]) == Value(100)
    started = time.monotonic()
    for n in (MAX_ITERATIONS + 1, 1e9, 2.0 ** 53):
        with pytest.raises(InterpretError, match="iterations"):
            interpret(counting, [n, 0.0])
    assert time.monotonic() - started < 1.0
