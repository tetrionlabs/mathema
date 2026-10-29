# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A decimal context held as an object (a module's `Context(prec=10)`,
one passed as a default argument or as `context=`) computes at its own
precision, outside the context a point runs in. Its own methods
(`ctx.divide`, `ctx.sqrt`) round at that precision, which bounds the
point; a Decimal method run beside such a context may compute in it,
and the point's rounding is then unbounded. Either way a true claim is
never falsified on the rounding, and a miss past it still is. The
contexts live in this module, apart from the bodies that compute in the
current context only."""
import decimal
import functools
from decimal import Decimal

import pytest

from mathema.conjecture import check_conjectures, claim

_PREC10 = decimal.Context(prec=10)


def module_context(x: int):
    return _PREC10.divide(Decimal(x), Decimal(3)) * 3


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_division_in_a_modules_context_is_not_counted(route):
    # 1/3 in 10 digits, times 3: 0.9999999999 below 1, so f(x) < x
    # holds only on the rounding
    (p,) = check_conjectures(module_context,
                             [claim("for x in {1, 4}, f(x) < x", route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.note)


def root_in_context(x: int):
    return Decimal(x).sqrt(context=_PREC10) ** 2


def context_by_default(x: int, ctx=_PREC10):
    return ctx.divide(Decimal(x), Decimal(3)) * 3


@pytest.mark.parametrize("fn,law", [
    # 1/3 in 10 digits, times 3: 0.9999999999 against 1, a miss rounding
    # to 10 digits accounts for; it is no witness
    (module_context, "for x in {1, 4}, f(x) == x"),
    (context_by_default, "for x in {1, 4}, f(x) == x"),
    (context_by_default, "for x in {1, 4}, f(x) < x"),
    # sqrt(n) in 10 digits, squared: n up to rounding at 10 digits
    (root_in_context, "for x in {2, 3}, f(x) == x"),
])
@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_context_objects_own_arithmetic_rounds_at_its_precision(
        fn, law, route):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample)


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_context_objects_result_far_from_the_claim_falsifies(route):
    # 0.9999999999 or 3.999999999 against 100: past any rounding
    (p,) = check_conjectures(module_context,
                             [claim("for x in {1, 4}, f(x) == 100",
                                    route=route)])
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


_CTX4 = decimal.Context(prec=4)


def root_squared_ctx(x: int):
    # sqrt rounded to 4 digits in a module's context, squared in the
    # current one: sqrt(2) is 1.414, squared 1.999396
    return Decimal(x).sqrt(context=_CTX4) ** 2


_COUNTED: list = []


def counted_sqrt(x: int):
    # the first call at each x computes in 4 digits, the next in 28
    _COUNTED.append(x)
    ctx = decimal.Context(prec=4 if _COUNTED.count(x) % 2 == 1 else 28)
    return ctx.sqrt(Decimal(x)) ** 2


@pytest.mark.parametrize("fn", [root_squared_ctx, counted_sqrt])
@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_true_claim_rounded_in_a_context_not_watched_is_not_falsified(
        fn, route):
    # sqrt(n) ** 2 == n is true; the code's 1.999396 at x = 2 is the
    # rounding of a context the call reaches, not a witness
    (p,) = check_conjectures(fn, [claim("for x in {2, 3}, f(x) == x",
                                        route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample)


HIGH = decimal.Context(prec=50)


def rounded_to_cents(x: float):
    # HIGH sits in this module unused; quantize is given no context
    return (Decimal(str(x)) + 1).quantize(Decimal("0.01"))


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_context_the_call_is_not_given_bounds_nothing(route):
    # x + 1 to cents against x: 1.00 against 0.0 at x = 0, a miss no
    # context the method computes in can account for
    (p,) = check_conjectures(rounded_to_cents,
                             [claim("for x in [0, 10], f(x) == x",
                                    route=route)])
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


def root_given_positionally(x: int):
    return Decimal.sqrt(Decimal(x), _CTX4) ** 2


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
def test_a_context_given_positionally_or_unbound_is_read(route):
    # sqrt in 4 digits through the class's own method, the context passed
    # by position: sqrt(n) ** 2 == n is true, 1.999396 is its rounding
    (p,) = check_conjectures(root_given_positionally,
                             [claim("for x in {2, 3}, f(x) == x",
                                    route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample)


_SQRT4 = functools.partial(Decimal.sqrt, context=_CTX4)


def alias_positional(x: int):
    c = _CTX4
    return Decimal(x).sqrt(c) ** 2


def spread_kwargs(x: int):
    kw = {"context": _CTX4}
    return Decimal(x).sqrt(**kw) ** 2


def via_partial(x: int):
    return _SQRT4(Decimal(x)) ** 2


def via_getattr_positional(x: int):
    name = "sq" + "rt"
    return getattr(Decimal(x), name)(_CTX4) ** 2


def multi_line(x: int):
    return Decimal(x).sqrt(
        context=_CTX4,
    ) ** 2


def via_map(x: int):
    return list(map(Decimal.sqrt, [Decimal(x)], [_CTX4]))[0] ** 2


@pytest.mark.parametrize("fn", [alias_positional, spread_kwargs, via_partial,
                                via_getattr_positional, multi_line, via_map],
                         ids=lambda f: f.__name__)
@pytest.mark.parametrize("route", ["best", "probe"])
def test_a_context_handed_over_any_way_is_read(fn, route):
    # each takes sqrt(x) in 4 digits and squares it, by an alias, a
    # spread, a partial, a looked-up method, a call over several lines or
    # map: sqrt(n) ** 2 == n is true, and 2.999824 at x = 3 is rounding
    (p,) = check_conjectures(fn, [claim("for x in {2, 3}, f(x) == x",
                                        route=route)])
    assert p.verdict == "unknown", (p.verdict, p.route, p.counterexample)
