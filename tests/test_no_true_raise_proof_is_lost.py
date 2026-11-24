# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A true `raises` claim that derive proved under the earlier reading of
`raise` is still proven under the stricter one. Each case is a small
function, a claim, the points the claim is checked to be true at by
calling the function, and the verdict the earlier reading gave
(`BASE`). Two groups:

- `KEPT` and the rows of `ELSEWHERE` whose verdict at `BASE` is proven:
  the earlier reading proved it, and it is proven.
- `NEVER_PROVEN` and the other rows of `ELSEWHERE`: true, and the earlier
  reading did not prove it. Only its truth is checked.

The kinds of claim: a constant of the claim language in the call (`pi`,
`2 * pi`, `max(1, 2)`, a tuple), a constant in the place of a parameter
nothing reads, a listed missing value on a parameter a mathema guard does
not judge or lets through, a wrapper that keeps a keyword of its own, an
instance that hands its call over, and every `raises` claim the other
test files of the raise reading prove."""
import builtins
import functools
import importlib
import importlib.util
import pathlib
import sys
from typing import Annotated

import pytest

from mathema._math_vocab import MATH_CONSTANTS
from mathema.authoring import (claims, enforce_dimensions, enforce_domain, enforce_range,
                               enforce_structure)
from mathema.conjecture import _SAFE_FUNCS, check_conjectures, claim
from mathema.types import Finite, Shape

#: the commit whose verdicts the tables record
BASE = "d4ba56e8"

_NAN = float("nan")
_INF = float("inf")
_NEG = "for x in [-5, -1], "
_Y = _NEG + "y in {1, None}, "
_XS = (-5.0, -3.3, -1.0, -5, -1)


def _at(*seconds):
    return [{"x": x, "y": y} for x in _XS for y in seconds]


_X = [{"x": x} for x in _XS]
_BOTH = _at(1, None)


def plain(x, y):
    if x < 0:
        raise ValueError("n")
    return x


def one(x):
    if x < 0:
        raise ValueError("n")
    return x


def doubles_second(x, y):
    if x < 0:
        z = y * 2
        raise ValueError(z)
    return x


def adds_to_second(x, y):
    if x < 0:
        raise ValueError(y + 1)
    return x


class _OwnBody:
    def __call__(self, x, y):
        if x < 0:
            raise ValueError("n")
        return x


class _HandsOver:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class _HandsOverWrapped:
    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class _HandsOverByName:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, x, y):
        return self.fn(x, y)


class _Methods:
    @staticmethod
    def static(x, y):
        if x < 0:
            raise ValueError("n")
        return x

    @classmethod
    def of_the_class(cls, x, y):
        if x < 0:
            raise ValueError("n")
        return x


@enforce_dimensions()
def dimensions_of_nothing(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_dimensions()
def dimensions_of_the_first(x: Shape(), y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_structure()
def structure_of_the_first(x: Annotated[float, Finite], y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_structure()
def structure_of_nothing(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"x": "[-10, 10]"})
@claims("absent(f, x) raises(TypeError)")
def policy_on_the_first(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_range()
@claims("for x in [0, 5], f(x, y) >= 0")
def range_of_the_result(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "[0, 2] ∪ {None}"})
def domain_lists_none(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "[0, 2]"})
def domain_says_nothing_of_none(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "{1, None}"})
def domain_is_the_same_set(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"x": "[-10, 10]"})
def _domain_of_the_first(x, y):
    if x < 0:
        raise KeyError("n")
    return x


dimensions_over_a_domain_guard = enforce_dimensions()(_domain_of_the_first)


def _keeps_a_keyword(fn):
    @functools.wraps(fn)
    def keeping(*args, _log=lambda v: v, **kwargs):
        return fn(*args, **kwargs)
    return keeping


keeps_a_keyword = _keeps_a_keyword(one)
keeps_a_keyword_two = _keeps_a_keyword(plain)
cached = functools.lru_cache(maxsize=None)(plain)

#: (id, function, claim, the call, the exception, points, verdict at BASE)
_CONSTANTS = [
    ("pi", plain, _NEG + "raises(f(x, pi), ValueError)", "f(x, pi)"),
    ("e", plain, _NEG + "raises(f(x, e), ValueError)", "f(x, e)"),
    ("inf", plain, _NEG + "raises(f(x, inf), ValueError)", "f(x, inf)"),
    ("nan", plain, _NEG + "raises(f(x, nan), ValueError)", "f(x, nan)"),
    ("-pi", plain, _NEG + "raises(f(x, -pi), ValueError)", "f(x, -pi)"),
    ("2 * pi", plain, _NEG + "raises(f(x, 2 * pi), ValueError)", "f(x, 2 * pi)"),
    ("pi / 2", plain, _NEG + "raises(f(x, pi / 2), ValueError)", "f(x, pi / 2)"),
    ("y=pi", plain, _NEG + "raises(f(x, y=pi), ValueError)", "f(x, y=pi)"),
    ("max(1, 2)", plain, _NEG + "raises(f(x, max(1, 2)), ValueError)", "f(x, max(1, 2))"),
    ("min(1, 2)", plain, _NEG + "raises(f(x, min(1, 2)), ValueError)", "f(x, min(1, 2))"),
    ("abs(-1)", plain, _NEG + "raises(f(x, abs(-1)), ValueError)", "f(x, abs(-1))"),
    ("sqrt(2)", plain, _NEG + "raises(f(x, sqrt(2)), ValueError)", "f(x, sqrt(2))"),
    ("1 < 2", plain, _NEG + "raises(f(x, 1 < 2), ValueError)", "f(x, 1 < 2)"),
    ("True", plain, _NEG + "raises(f(x, True), ValueError)", "f(x, True)"),
    ("a tuple", plain, _NEG + "raises(f(x, (1, 2)), ValueError)", "f(x, (1, 2))"),
    ("a list", plain, _NEG + "raises(f(x, [1, 2]), ValueError)", "f(x, [1, 2])"),
    ("a tuple, cached", cached, _NEG + "raises(f(x, (1, 2)), ValueError)", "f(x, (1, 2))"),
    ("text, cached", cached, _NEG + "raises(f(x, 'a'), ValueError)", "f(x, 'a')"),
    ('2 ** 3', plain, _NEG + "raises(f(x, 2 ** 3), ValueError)", "f(x, 2 ** 3)"),
    ('2 ** -1', plain, _NEG + "raises(f(x, 2 ** -1), ValueError)", "f(x, 2 ** -1)"),
    ('2.5 ** 2', plain, _NEG + "raises(f(x, 2.5 ** 2), ValueError)", "f(x, 2.5 ** 2)"),
    ('10 ** 300', plain, _NEG + "raises(f(x, 10 ** 300), ValueError)", "f(x, 10 ** 300)"),
    ('[1, 2][0]', plain, _NEG + "raises(f(x, [1, 2][0]), ValueError)", "f(x, [1, 2][0])"),
    ('(1, 2)[-1]', plain, _NEG + "raises(f(x, (1, 2)[-1]), ValueError)", "f(x, (1, 2)[-1])"),
    ("'ab'[1]", plain, _NEG + "raises(f(x, 'ab'[1]), ValueError)", "f(x, 'ab'[1])"),
    ('not 1', plain, _NEG + "raises(f(x, not 1), ValueError)", "f(x, not 1)"),
    ('1 and 2', plain, _NEG + "raises(f(x, 1 and 2), ValueError)", "f(x, 1 and 2)"),
    ('0 or 3', plain, _NEG + "raises(f(x, 0 or 3), ValueError)", "f(x, 0 or 3)"),
    ('not (1 < 2)', plain, _NEG + "raises(f(x, not (1 < 2)), ValueError)", "f(x, not (1 < 2))"),
    ('1 if 2 else 3', plain, _NEG + "raises(f(x, 1 if 2 else 3), ValueError)", "f(x, 1 if 2 else 3)"),
    ('1 if 0 else 3', plain, _NEG + "raises(f(x, 1 if 0 else 3), ValueError)", "f(x, 1 if 0 else 3)"),
    ('len([1, 2])', plain, _NEG + "raises(f(x, len([1, 2])), ValueError)", "f(x, len([1, 2]))"),
    ("len('abc')", plain, _NEG + "raises(f(x, len('abc')), ValueError)", "f(x, len('abc'))"),
    ('sum([1, 2])', plain, _NEG + "raises(f(x, sum([1, 2])), ValueError)", "f(x, sum([1, 2]))"),
    ('sorted([2, 1])', plain, _NEG + "raises(f(x, sorted([2, 1])), ValueError)", "f(x, sorted([2, 1]))"),
    ('str(1)', plain, _NEG + "raises(f(x, str(1)), ValueError)", "f(x, str(1))"),
    ("str('a')", plain, _NEG + "raises(f(x, str('a')), ValueError)", "f(x, str('a'))"),
    ("text the raise repeats", doubles_second,
     _NEG + "raises(f(x, 'a'), ValueError)", "f(x, 'a')"),
    ("a tuple the raise repeats", doubles_second,
     _NEG + "raises(f(x, (1, 2)), ValueError)", "f(x, (1, 2))"),
    ("a number the raise doubles", doubles_second,
     _NEG + "raises(f(x, 3), ValueError)", "f(x, 3)"),
    ("a number where the domain binds an unread parameter", plain,
     _Y + "raises(f(x, 3), ValueError)", "f(x, 3)"),
    ("the same by keyword", plain, _Y + "raises(f(x, y=3), ValueError)", "f(x, y=3)"),
    ("None where the domain binds an unread parameter", plain,
     _Y + "raises(f(x, None), ValueError)", "f(x, None)"),
    ("pi where the domain binds an unread parameter", plain,
     _Y + "raises(f(x, pi), ValueError)", "f(x, pi)"),
    ("a number outside the interval of an unread parameter", plain,
     _NEG + "y in [1, 5], raises(f(x, 7), ValueError)", "f(x, 7)"),
    ("text where an interval binds an unread parameter", plain,
     _NEG + "y in [1, 5], raises(f(x, 'a'), ValueError)", "f(x, 'a')"),
]

KEPT = [(name, fn, text, call, "ValueError", _X, "proven")
        for name, fn, text, call in _CONSTANTS] + [
    ("dimension guard with no shape", dimensions_of_nothing,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("dimension guard on the other parameter", dimensions_of_the_first,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("structure guard on the other parameter", structure_of_the_first,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("structure guard with no structure", structure_of_nothing,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("domain guard with a policy on the other parameter", policy_on_the_first,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("range guard", range_of_the_result,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("domain guard that lists None", domain_lists_none,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("domain guard that says nothing of None", domain_says_nothing_of_none,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("domain guard of the same set", domain_is_the_same_set,
     _Y + "raises(f(x, y), KeyError)", "f(x, y)", "KeyError", _BOTH, "proven"),
    ("wrapper that keeps a keyword", keeps_a_keyword,
     _NEG + "raises(f(x), ValueError)", "f(x)", "ValueError", _X, "proven"),
    ("wrapper that keeps a keyword, unread parameter", keeps_a_keyword_two,
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("instance that hands over", _HandsOver(plain),
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("instance that hands over and links the function", _HandsOverWrapped(plain),
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("instance that hands over by name", _HandsOverByName(plain),
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("static method", _Methods.static,
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("class method", _Methods.of_the_class,
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "proven"),
    ("another variable for an unread parameter, by keyword", plain,
     _Y + "raises(f(x, y=x), ValueError)", "f(x, y=x)", "ValueError", _BOTH, "proven"),
    ("another variable for an unread parameter, by position", plain,
     _NEG + "raises(f(x, x), ValueError)", "f(x, x)", "ValueError", _X, "proven"),
    ("a starred list of literals", plain,
     _NEG + "raises(f(x, *[1]), ValueError)", "f(x, *[1])", "ValueError", _X, "proven"),
    ("a starred tuple", plain,
     _NEG + "raises(f(x, *(1,)), ValueError)", "f(x, *(1,))", "ValueError", _X, "proven"),
    ("a starred list holding the variable", plain,
     _NEG + "raises(f(*[x, 1]), ValueError)", "f(*[x, 1])", "ValueError", _X, "proven"),
    ("dimension guard over a domain guard on the other parameter",
     dimensions_over_a_domain_guard, _Y + "raises(f(x, y), KeyError)", "f(x, y)",
     "KeyError", _BOTH, "proven"),
]

NEVER_PROVEN = [
    ("instance with its own body", _OwnBody(),
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "unknown"),
    ("partial of the function", functools.partial(plain),
     _Y + "raises(f(x, y), ValueError)", "f(x, y)", "ValueError", _BOTH, "unknown"),
    ("a literal the raise adds to", adds_to_second,
     _NEG + "raises(f(x, 2), ValueError)", "f(x, 2)", "ValueError", _X, "unknown"),
    ("pi the raise adds to", adds_to_second,
     _NEG + "raises(f(x, pi), ValueError)", "f(x, pi)", "ValueError", _X, "unknown"),
]

#: a `raises` claim another test file of the raise reading proves:
#: (module, function, route, claim or claims, the call, the exception,
#: points, verdict at BASE)
ELSEWHERE = [
    ('test_a_cause_is_an_exception_by_its_real_type', 'cause_is_an_instance', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_cause_is_an_exception_by_its_real_type', 'cause_is_a_subclass', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_listed_missing_value_is_part_of_a_raises_claim', 'raises_below_zero', 'derive',
     'for x in [-5.0, -1.0] : float|missing, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5.0}, {'x': -3.0}, {'x': -3.8}, {'x': -1.0}],
     'proven'),
    ('test_a_listed_missing_value_is_part_of_a_raises_claim', 'raises_below_zero_or_at_nan', 'best',
     'for x in {-1, -2, nan}, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -1}, {'x': -2}, {'x': _NAN}],
     'proven'),
    ('test_a_listed_missing_value_is_part_of_a_raises_claim', 'raises_below_zero', 'derive',
     'for x in {-1, -2}, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -1}, {'x': -2}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'domain_guard_on_the_other_parameter', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), KeyError)',
     'f(x, y)', 'KeyError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'other_guard_under_a_pass_through', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), KeyError)',
     'f(x, y)', 'KeyError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'cached', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'lambda_over_plain', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'only_deletes', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'under_a_lambda', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'one_argument_reversed', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_listed_missing_value_is_unread_only_when_nothing_reads_it', 'keywords_copied', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'percent_format', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'percent_one', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'brace_format', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'type_name', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'policy_none_or_nan', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('test_a_raise_path_bounds_every_value_it_can_hold', 'small_remainder', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3}, {'x': -4}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, 1/2), ValueError)',
     'f(x, 1/2)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, 2*3 + 1), ValueError)',
     'f(x, 2*3 + 1)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, -1.5), ValueError)',
     'f(x, -1.5)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     "for x in [-5, -1], raises(f(x, 'a'), ValueError)",
     "f(x, 'a')", 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'neg_raise', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'subclass', 'best',
     'for x in [-5, -1], raises(f(x), ArithmeticError)',
     'f(x)', 'ArithmeticError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('test_the_raise_reading_review_cases', 'alias', 'best',
     'for x in [-5, -1], raises(f(x), OSError)',
     'f(x)', 'OSError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('test_the_raise_reading_review_cases', 'stopiter', 'best',
     'for x in [-5, -1], raises(f(x), StopIteration)',
     'f(x)', 'StopIteration', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'oserror_one', 'best',
     'for x in [-5, -1], raises(f(x), OSError)',
     'f(x)', 'OSError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'nan_div', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'mod_float', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'pol_literal', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises'),
     'f(x, y)', 'Exception', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'pol_literal', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'pol_lam_plain', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases1', 'ok_case', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'spec_f', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'spec_pct', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'spec_e_int', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3}, {'x': -4}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'pct_s', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'pct_one', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'brace_ok', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'typename', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'none_or_nan', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'str_spec', 'best',
     "for x in {'a'}, raises(f(x), ValueError)",
     'f(x)', 'ValueError', [{'x': 'a'}],
     'proven'),
    ('raise_review_three_cases1', 'floordiv_inf', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'mod_inf', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'big_mid', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3}, {'x': -4}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'neg_then_div', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases2', 'pol_eq_none', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases3', 'two', 'best',
     'for x in {1, 2}, y in [0, 1], raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': 1, 'y': 0}, {'x': 2, 'y': 0.5}, {'x': 1, 'y': 0.3}, {'x': 2, 'y': 1}, {'x': 1, 'y': 0.5}, {'x': 1, 'y': 1}, {'x': 2, 'y': 0}, {'x': 2, 'y': 0.3}],
     'proven'),
    ('raise_review_three_cases3', 'negzero', 'best',
     'for x in {-1.0, -0.0}, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -1.0}, {'x': -0.0}],
     'proven'),
    ('raise_review_three_cases5', 'nested_yield', 'best',
     'for x in [-5, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases5', 'same_obj', 'best',
     'for x in [-5, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases5', 'cached', 'best',
     'for x in [-5, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases5', 'handed', 'best',
     'for x in [-5, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_policy_from_an_unread_guard_is_never_proven', 'guard_first', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises'),
     'f(x, y)', 'Exception', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('test_a_policy_from_an_unread_guard_is_never_proven', 'guard_first', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'f_string_of_an_int', 'derive',
     'for x in [1, 100], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': 1}, {'x': 50}, {'x': 31}, {'x': 100}],
     'proven'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'str_of_an_int', 'derive',
     'for x in [1, 100], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': 1}, {'x': 50}, {'x': 31}, {'x': 100}],
     'proven'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'repr_of_an_int', 'derive',
     'for x in [1, 100], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': 1}, {'x': 50}, {'x': 31}, {'x': 100}],
     'proven'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'arithmetic_before_the_raise', 'derive',
     'for x in [-5, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'raises_a_subclass', 'derive',
     'for x in [-5, -1], raises(f(x), ArithmeticError)',
     'f(x)', 'ArithmeticError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_is_read_only_along_a_path_that_cannot_fail', 'raises_an_alias', 'derive',
     'for x in [-5, -1], raises(f(x), OSError)',
     'f(x)', 'OSError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'fixed_spec', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_message_built_from_text_that_cannot_fail_is_read', 'exponent_spec', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3}, {'x': -4}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, y=3 - 1), ValueError)',
     'f(x, y=3 - 1)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, None), ValueError)',
     'f(x, None)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], raises(f(x, 7 // 2), ValueError)',
     'f(x, 7 // 2)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y=y), ValueError)',
     'f(x, y=y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x=x, y=y), ValueError)',
     'f(x=x, y=y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', 'plain', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(y=y, x=x), ValueError)',
     'f(y=y, x=x)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', '_Holder().method', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raise_proof_reads_the_arguments_the_call_passes', '_Holder().method', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y=y), ValueError)',
     'f(x, y=y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raise_read_through_what_cannot_fail_is_proven_again', 'cause_class', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_read_through_what_cannot_fail_is_proven_again', 'chain_short_circuits', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_read_through_what_cannot_fail_is_proven_again', 'group', 'derive',
     'for x in [-5, -1], raises(f(x), ExceptionGroup)',
     'f(x)', 'ExceptionGroup', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'unknown'),
    ('test_a_raise_read_through_what_cannot_fail_is_proven_again', 'wrapped', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raise_read_through_what_cannot_fail_is_proven_again', 'unused_second', 'derive',
     'for x in [-5, -1], y in {1, None}, raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 1}, {'x': -3.0, 'y': None}, {'x': -3.8, 'y': 1}, {'x': -1, 'y': None}, {'x': -5, 'y': None}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raises_claim_is_derived_only_for_the_call_written', 'r01', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_a_raises_claim_is_derived_only_for_the_call_written', 'r02', 'best',
     'for x in [-5, -1], y in [0, 1], raises(f(x, y), ValueError)',
     'f(x, y)', 'ValueError', [{'x': -5, 'y': 0}, {'x': -3.0, 'y': 0.5}, {'x': -3.8, 'y': 0.3}, {'x': -1, 'y': 1}, {'x': -5, 'y': 0.5}, {'x': -5, 'y': 0.3}, {'x': -5, 'y': 1}, {'x': -3.0, 'y': 0}, {'x': -3.0, 'y': 0.3}, {'x': -3.0, 'y': 1}],
     'proven'),
    ('test_a_raises_proof_holds_only_for_the_values_the_call_passes', 'ground', 'derive',
     'raises(f(50, 0), ValueError)',
     'f(50, 0)', 'ValueError', [{}],
     'proven'),
    ('test_a_wrapper_is_read_only_when_its_definition_is', 'cached_raise', 'derive',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('test_the_raise_reading_review_cases', 'pol_or', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases1', 'mod_floordiv_chain', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3}, {'x': -4}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'alias_name', 'best',
     'for x in [-5, -1], raises(f(x), KeyError)',
     'f(x)', 'KeyError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases1', 'alias_name', 'best',
     'for x in [-5, -1], raises(f(x), ValueErrorAlias)',
     'f(x)', 'ValueErrorAlias', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases1', 'true_isnan_guard', 'best',
     'for x in [-5, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'holds'),
    ('raise_review_three_cases2', 'pol_nan_ne', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'missing(f, x) raises(ValueError)'),
     'f(x, y)', 'ValueError', [{'x': _NAN, 'y': -1}, {'x': _NAN, 'y': 0.0}, {'x': _NAN, 'y': -0.4}, {'x': _NAN, 'y': 1}, {'x': _NAN, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases2', 'pol_absent_or_isnan', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'missing(f, x) raises(ValueError)'),
     'f(x, y)', 'ValueError', [{'x': _NAN, 'y': -1}, {'x': _NAN, 'y': 0.0}, {'x': _NAN, 'y': -0.4}, {'x': _NAN, 'y': 1}, {'x': _NAN, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases2', 'pol_absent_or_isnan', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(ValueError)'),
     'f(x, y)', 'ValueError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases2', 'pol_ctor_meta', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'holds'),
    ('raise_review_three_cases3', 'raise_neg', 'best',
     'for x in [-5, -1] : float|missing, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases3', 'raise_neg_opt', 'best',
     'for x in [-5, -1] : float|absent, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -5}, {'x': -3.0}, {'x': -3.8}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases3', 'inf_raise', 'best',
     'for x in {-inf, -1}, raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -_INF}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases3', 'inf_raise', 'best',
     'for x in [-oo, -1], raises(f(x), ValueError)',
     'f(x)', 'ValueError', [{'x': -_INF}, {'x': -1000000.0}, {'x': -2.5}, {'x': -8.0}, {'x': -1}],
     'proven'),
    ('raise_review_three_cases7', 'pol_lam_plain', 'best',
     ('for x in [0, 1], y in [-1, 1], f(x, y) == x * y', 'absent(f, x) raises(TypeError)'),
     'f(x, y)', 'TypeError', [{'x': None, 'y': -1}, {'x': None, 'y': 0.0}, {'x': None, 'y': -0.4}, {'x': None, 'y': 1}, {'x': None, 'y': 0.123456}],
     'proven'),
    ('raise_review_three_cases8', 'guarded_thin', 'best',
     'for x in [-4.9999999, -1], raises(f(x), TypeError)',
     'f(x)', 'TypeError', [{'x': -4.9999999}, {'x': -2.99999995}, {'x': -3.79999993}, {'x': -1}],
     'proven'),
    ("raise_review_three_cases1", "mod_neg", "best",
      "for x in [-5, -1], raises(f(x), ValueError)", "f(x)", "ValueError", _X, "proven"),
    ("raise_review_three_cases1", "floordiv_small", "best",
      "for x in [-5, -1], raises(f(x), ValueError)", "f(x)", "ValueError", _X, "proven"),
    ("raise_review_three_cases1", "div_least", "best",
      "for x in [-5, -1], raises(f(x), ValueError)", "f(x)", "ValueError", _X, "proven"),
    ("raise_review_three_cases5", "dispatched", "best",
      "for x in [-5, -1], raises(f(x), TypeError)", "f(x)", "TypeError", _X, "proven"),
    ("test_the_raise_reading_review_cases", "pol_kw", "best",
      ("for x in [0, 1], y in [-1, 1], f(x, y) == x * y", "absent(f, x) raises(TypeError)"),
      "f(x, y)", "TypeError",
      [{"x": None, "y": y} for y in (-1, -0.5, 0.0, 0.123456, 1)], "proven"),
    ("test_a_raise_is_read_only_along_a_path_that_cannot_fail",
      "policy_keyword_argument", "best",
      ("for x in [0, 1], y in [-1, 1], f(x, y) == x * y", "absent(f, x) raises(TypeError)"),
      "f(x, y)", "TypeError",
      [{"x": None, "y": y} for y in (-1, -0.5, 0.0, 0.123456, 1)], "proven"),
    ("raise_review_three_cases2", "pol_second_sub", "best",
      ("for x in [0, 1], y in [-1, 1], f(x, y) == x * y",
       "absent(f, x) raises(ArithmeticError)"),
      "f(x, y)", "ArithmeticError",
      [{"x": None, "y": y} for y in (-1, -0.5, 0.0, 0.123456, 1)], "proven"),
]

_STRENGTH = {"proven": 2, "holds": 1}


def _module(name):
    if not name.startswith("raise_review_three_"):
        return importlib.import_module(name)
    if name not in sys.modules:
        path = pathlib.Path(__file__).parent / "raise_review_three" \
            / f"{name[len('raise_review_three_'):]}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _elsewhere(entry):
    module_name, name, route, texts, call, exception, points, base = entry
    module = _module(module_name)
    texts = (texts,) if isinstance(texts, str) else texts
    return (f"{module_name}:{name}:{texts[-1]}", eval(name, vars(module)), texts, route,
            call, exception, points, base, vars(module))


def _own(entry):
    name, fn, text, call, exception, points, base = entry
    return (name, fn, (text,), "derive", call, exception, points, base, {})


def _params(cases):
    out = []
    for case in cases:
        marks = [pytest.mark.skipif(case[5] == "ExceptionGroup"
                                    and not hasattr(builtins, "ExceptionGroup"),
                                    reason="Python 3.11 or later")]
        out.append(pytest.param(*case[1:], id=case[0], marks=marks))
    return out


_ALL_KEPT = [_own(c) for c in KEPT] + [_elsewhere(c) for c in ELSEWHERE if c[-1] == "proven"]
_ALL_NEVER = [_own(c) for c in NEVER_PROVEN] \
    + [_elsewhere(c) for c in ELSEWHERE if c[-1] != "proven"]
_ARGS = "fn,texts,route,call,exception,points,base,names"


def _raised(fn, call, point):
    try:
        eval(call, {"__builtins__": {}, **_SAFE_FUNCS, **MATH_CONSTANTS, "f": fn}, dict(point))
    except BaseException as error:  # noqa: BLE001
        return error
    return None


@pytest.mark.parametrize(_ARGS, _params(_ALL_KEPT + _ALL_NEVER))
def test_the_claim_is_true_at_each_point(fn, texts, route, call, exception, points,
                                         base, names):
    expected = eval(exception, {**vars(builtins), **names})
    assert len(points) >= 1
    for point in points:
        error = _raised(fn, call, point)
        assert isinstance(error, expected), (call, point, error)


@pytest.mark.parametrize(_ARGS, _params(_ALL_KEPT))
def test_a_true_claim_proven_before_is_still_proven(fn, texts, route, call, exception,
                                                    points, base, names):
    assert base == "proven"
    made = [claim(t, route="derive") if route == "derive" else claim(t) for t in texts]
    row = check_conjectures(fn, made)[-1]
    assert _STRENGTH.get(row.verdict, 0) >= _STRENGTH[base], \
        (row.verdict, row.route, row.sketch, row.note)


#: a true value claim on a wrapper that only catches, proven at BASE:
#: (module, function, claim, points, verdict at BASE)
VALUE_CLAIMS = [
    ("raise_review_three_cases2", "pol_wrapped",
     "for x in [0, 1], y in [-1, 1], f(x, y) == x * y",
     [(0.0, -1.0), (0.5, 0.25), (1.0, 1.0), (1, -1), (0.25, 0.75)], "proven"),
    ("test_a_value_claim_is_proven_through_a_wrapper_that_only_catches",
     "_catches(product)", "for x in [0, 1], y in [-1, 1], f(x, y) == x * y",
     [(0.0, -1.0), (0.5, 0.25), (1.0, 1.0), (1, -1), (0.25, 0.75)], "proven"),
]


@pytest.mark.parametrize("module,name,text,points,base", VALUE_CLAIMS,
                         ids=[f"{c[0]}:{c[1]}" for c in VALUE_CLAIMS])
def test_a_true_value_claim_proven_before_is_still_proven(module, name, text, points, base):
    fn = eval(name, vars(_module(module)))
    assert all(fn(x, y) == x * y for x, y in points)
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert _STRENGTH.get(row.verdict, 0) >= _STRENGTH[base], \
        (row.verdict, row.route, row.sketch, row.note)
