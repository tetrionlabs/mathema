# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A constant written in a `raises` claim's call is read only where it
cannot change what the call does. A list under a cache does not hash, a
guard judges the value in the place of the parameter it covers, a
constant in the place of a parameter the raise depends on is not the
domain, a call of the claim language that raises is not a value, and a
wrapper that keeps a keyword does not hand that keyword on. Each claim
here is false, shown by calling the function, and is not proven."""
import functools
import math
from typing import Annotated

import pytest

from mathema._math_vocab import MATH_CONSTANTS
from mathema.authoring import claims, enforce_domain, enforce_structure
from mathema.conjecture import _SAFE_FUNCS, check_conjectures, claim
from mathema.types import Finite

_NEG = "for x in [-5, -1], "
_Y = _NEG + "y in {1, None}, "


def plain(x, y):
    if x < 0:
        raise ValueError("n")
    return x


def one(x):
    if x < 0:
        raise ValueError("n")
    return x


def raises_when_logged(x, _log=None):
    if x < 0 and _log == 1:
        raise ValueError("n")
    return x


@enforce_structure()
def structure_of_the_second(x, y: Annotated[float, Finite]):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"x": "[-10, 10]"})
@claims("absent(f, y) raises(TypeError)")
def policy_on_the_second(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "{1, 2}"})
def domain_of_two_numbers(x, y):
    if x < 0:
        raise KeyError("n")
    return x


def _keeps_a_keyword(fn):
    @functools.wraps(fn)
    def keeping(*args, _log=None, **kwargs):
        return fn(*args, **kwargs)
    return keeping


def _needs_a_keyword(fn):
    @functools.wraps(fn)
    def needing(*args, _log, **kwargs):
        return fn(*args, **kwargs)
    return needing


cached = functools.lru_cache(maxsize=None)(plain)
keeps_the_keyword_passed = _keeps_a_keyword(raises_when_logged)
needs_a_keyword = _needs_a_keyword(one)


def _outcome(fn, call, point):
    try:
        eval(call, {"__builtins__": {}, **_SAFE_FUNCS, **MATH_CONSTANTS, "f": fn}, dict(point))
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__
    return "returns"


@pytest.mark.parametrize("fn,text,call,point,outcome", [
    (cached, _NEG + "raises(f(x, [1, 2]), ValueError)", "f(x, [1, 2])",
     {"x": -2.0}, "TypeError"),
    (cached, _NEG + "raises(f(x, (1, [2])), ValueError)", "f(x, (1, [2]))",
     {"x": -2.0}, "TypeError"),
    (cached, _Y + "raises(f(x, [1, 2]), ValueError)", "f(x, [1, 2])",
     {"x": -2.0}, "TypeError"),
    (structure_of_the_second, _NEG + "raises(f(x, nan), KeyError)", "f(x, nan)",
     {"x": -2.0}, "ValueError"),
    (structure_of_the_second, _NEG + "raises(f(x, 2 * inf), KeyError)", "f(x, 2 * inf)",
     {"x": -2.0}, "ValueError"),
    (structure_of_the_second, _NEG + "y in [1, 2], raises(f(x, nan), KeyError)", "f(x, nan)",
     {"x": -2.0}, "ValueError"),
    (policy_on_the_second, _Y + "raises(f(x, y), KeyError)", "f(x, y)",
     {"x": -2.0, "y": None}, "TypeError"),
    (domain_of_two_numbers, _Y + "raises(f(x, y), KeyError)", "f(x, y)",
     {"x": -2.0, "y": None}, "DomainError"),
    (domain_of_two_numbers, _NEG + "y in {1, 3}, raises(f(x, y), KeyError)", "f(x, y)",
     {"x": -2.0, "y": 3}, "DomainError"),
    (one, _NEG + "raises(f(pi), ValueError)", "f(pi)", {}, "returns"),
    (one, _NEG + "raises(f(max(1, 2)), ValueError)", "f(max(1, 2))", {}, "returns"),
    (plain, _NEG + "raises(f(x, exp(1000)), ValueError)", "f(x, exp(1000))",
     {"x": -2.0}, "OverflowError"),
    (plain, _NEG + "raises(f(x, max(1)), ValueError)", "f(x, max(1))",
     {"x": -2.0}, "TypeError"),
    (plain, _NEG + "raises(f(x, (1, 1 / 0)), ValueError)", "f(x, (1, 1 / 0))",
     {"x": -2.0}, "ZeroDivisionError"),
    (keeps_the_keyword_passed, _NEG + "raises(f(x, _log=1), ValueError)", "f(x, _log=1)",
     {"x": -2.0}, "returns"),
    (needs_a_keyword, _NEG + "raises(f(x), ValueError)", "f(x)", {"x": -2.0}, "TypeError"),
], ids=["list under a cache", "tuple holding a list under a cache",
        "list for an unread parameter under a cache", "nan under a structure guard",
        "infinity under a structure guard", "nan where the domain binds a guarded parameter",
        "None under a policy", "None under a domain of two numbers",
        "a number outside the guard's set", "pi for the parameter the raise depends on",
        "a call for the parameter the raise depends on", "a call that overflows",
        "max of one number", "a tuple holding a division by zero",
        "a keyword the wrapper keeps", "a wrapper that needs its keyword"])
def test_a_false_claim_with_a_constant_in_the_call_is_not_proven(fn, text, call, point,
                                                                 outcome):
    assert _outcome(fn, call, point) == outcome
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def test_the_constants_of_the_claim_language_are_the_ones_read():
    assert MATH_CONSTANTS["pi"] == math.pi and math.isnan(MATH_CONSTANTS["nan"])
    assert _SAFE_FUNCS["max"] is max and _SAFE_FUNCS["abs"] is abs


@pytest.mark.parametrize("argument,raised", [
    ("2 ** (1 // 0)", "ZeroDivisionError"), ("0 ** -1", "ZeroDivisionError"),
    ("2.0 ** 10000", "OverflowError"), ("[1, 2][5]", "IndexError"),
    ("(1, 2)['a']", "TypeError"), ("*[1 / 0]", "ZeroDivisionError"),
    ("not 1 / 0", "ZeroDivisionError"), ("1 and 1 / 0", "ZeroDivisionError"),
    ("1 if 1 / 0 else 2", "ZeroDivisionError"), ("len(3)", "TypeError"),
    ("sum(['a'])", "TypeError"),
    ("sorted([1, 'a'])", "TypeError"), ("str(1 / 0)", "ZeroDivisionError"),
])
def test_a_form_that_is_read_is_not_proven_where_it_can_raise(argument, raised):
    call = f"f(x, {argument})"
    assert _outcome(plain, call, {"x": -2.0}) == raised
    (row,) = check_conjectures(
        plain, [claim(_NEG + f"raises({call}, ValueError)", route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("argument,form", [
    ("{1: 2}", "a dict display"), ("{1, 2}", "a set display"),
    ("[1, 2][0:1]", "a slice"), ("**{}", "an unpacked mapping"),
])
def test_a_form_that_is_not_read_is_named(argument, form):
    (row,) = check_conjectures(
        plain, [claim(_NEG + f"raises(f(x, {argument}), ValueError)", route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)
    said = f"{row.sketch} {row.note}"
    assert "is not read" not in said or form in said, said


def doubles_second(x, y):
    if x < 0:
        z = y * 2
        raise ValueError(z)
    return x


@pytest.mark.parametrize("argument,raised", [
    ("None", "TypeError"), ("1.5 < 2 < None", "TypeError"), ("{1: 2}", "TypeError"),
], ids=["None", "a comparison with None", "a dict"])
def test_a_literal_the_raise_cannot_compute_with_is_not_proven(argument, raised):
    call = f"f(x, {argument})"
    assert _outcome(doubles_second, call, {"x": -2.0}) == raised
    (row,) = check_conjectures(
        doubles_second, [claim(_NEG + f"raises({call}, ValueError)", route="derive")])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("argument", ["'a'", "(1, 2)", "[1]", "3"])
def test_the_raise_is_read_at_the_literal_the_call_passes(argument):
    call = f"f(x, {argument})"
    assert _outcome(doubles_second, call, {"x": -2.0}) == "ValueError"
    (row,) = check_conjectures(
        doubles_second, [claim(_NEG + f"raises({call}, ValueError)", route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
