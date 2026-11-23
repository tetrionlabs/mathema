# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A listed missing value on a parameter the body never names leaves a
raises proof standing only when nothing between the claim's call and the
body reads that parameter. A mathema guard covering it refuses the value
before the body runs, so the claim is falsified by the guard's own
exception; any wrapper whose definition is not read as leaving the
parameter alone keeps the claim unproven. A wrapper that hands its
arguments on unchanged (a lambda, `*args[::-1]` over one argument,
`**{**kwargs}`), a cache, a domain guard on another parameter, and a body
that only deletes the parameter all leave it unread."""
import functools
from typing import Annotated

import pytest

from mathema.authoring import enforce_dimensions, enforce_domain, enforce_structure
from mathema.conjecture import check_conjectures, claim
from mathema.types import Finite, Vec

_NEG = "for x in [-5, -1], "
_Y = _NEG + "y in {1, None}, "


@enforce_domain({"y": "[0, 2] \\ {None}"})
def domain_guard_excludes_none(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"y": "[0, 2] \\ {nan}"})
def domain_guard_excludes_nan(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"x": "[-10, 10]"})
def domain_guard_on_the_other_parameter(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_dimensions()
def dimension_guard(x, y: Vec("n")):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_structure()
def structure_guard(x, y: Annotated[float, Finite]):
    if x < 0:
        raise KeyError("n")
    return x


def _checks_second(fn):
    @functools.wraps(fn)
    def checking(x, y):
        y + 1
        return fn(x, y)
    return checking


@_checks_second
def user_wrapper_reads_it(x, y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_domain({"x": "[0, 10]"})
def domain_guard_refuses_the_whole_domain(x):
    if x < 0:
        raise KeyError("n")
    return x


def plain(x, y):
    if x < 0:
        raise ValueError("n")
    return x


def only_deletes(x, y):
    if x < 0:
        raise ValueError("n")
    del y
    return x


def deletes_twice(x, y):
    del y
    del y  # noqa: F821
    if x < 0:
        raise ValueError("n")
    return x


def deletes_then_reads(x, y):
    del y
    if x < 0:
        raise ValueError(y)  # noqa: F821
    return x


def _lambda_hands_on(fn):
    return functools.wraps(fn)(lambda *args, **kwargs: fn(*args, **kwargs))


def _lambda_negates(fn):
    return functools.wraps(fn)(lambda *args, **kwargs: fn(*[-a for a in args], **kwargs))


def _reverses(fn):
    @functools.wraps(fn)
    def reversing(*args, **kwargs):
        return fn(*args[::-1], **kwargs)
    return reversing


def _copies_keywords(fn):
    @functools.wraps(fn)
    def copying(*args, **kwargs):
        return fn(*args, **{**kwargs})
    return copying


def _one(x):
    if x < 0:
        raise ValueError("n")
    return x


def _first_decides(x, y):
    if x < 0:
        raise ValueError("n")
    return x


def _hands_on(fn):
    @functools.wraps(fn)
    def handing_on(*args, **kwargs):
        return fn(*args, **kwargs)
    return handing_on


guard_under_a_pass_through = _hands_on(domain_guard_excludes_none)
other_guard_under_a_pass_through = _hands_on(domain_guard_on_the_other_parameter)
dimension_guard_over_a_domain_guard = enforce_dimensions()(domain_guard_on_the_other_parameter)
cached = functools.lru_cache(maxsize=None)(plain)
lambda_over_plain = _lambda_hands_on(plain)
under_a_lambda = _lambda_hands_on(_one)
under_a_negating_lambda = _lambda_negates(_one)
one_argument_reversed = _reverses(_one)
two_arguments_reversed = _reverses(_first_decides)
keywords_copied = _copies_keywords(_one)


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    return row


def _raised(fn, *args):
    try:
        fn(*args)
    except BaseException as error:
        return type(error).__name__
    return None


@pytest.mark.parametrize("fn,text,value,raised", [
    (domain_guard_excludes_none, _Y + "raises(f(x, y), KeyError)", None, "DomainError"),
    (domain_guard_excludes_nan, _NEG + "y in {1, nan}, raises(f(x, y), KeyError)",
     float("nan"), "DomainError"),
    (user_wrapper_reads_it, _Y + "raises(f(x, y), KeyError)", None, "TypeError"),
    (guard_under_a_pass_through, _Y + "raises(f(x, y), KeyError)", None, "DomainError"),
], ids=["domain guard, None", "domain guard, nan", "user wrapper",
        "domain guard under a pass-through"])
def test_a_guard_that_refuses_the_listed_missing_value_falsifies_the_claim(
        fn, text, value, raised):
    assert _raised(fn, -2.0, value) == raised
    row = _row(fn, text)
    assert row.verdict == "falsified", (row.verdict, row.sketch, row.note)
    said = f"{row.sketch} {row.note} {getattr(row, 'counterexample', '')}"
    assert raised in said, said


@pytest.mark.parametrize("fn", [dimension_guard, structure_guard,
                                dimension_guard_over_a_domain_guard],
                         ids=["dimension guard", "structure guard",
                              "dimension guard over a domain guard"])
def test_another_guard_on_the_unnamed_parameter_is_not_read_past(fn):
    if fn is not dimension_guard_over_a_domain_guard:
        assert _raised(fn, -2.0, None) not in (None, "KeyError")
    row = _row(fn, _Y + "raises(f(x, y), KeyError)")
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,raised", [
    (domain_guard_on_the_other_parameter, "KeyError"),
    (other_guard_under_a_pass_through, "KeyError"),
    (cached, "ValueError"),
    (lambda_over_plain, "ValueError"),
], ids=["domain guard on the other parameter", "the same under a pass-through", "cache",
        "lambda"])
def test_a_wrapper_read_as_leaving_the_parameter_alone_keeps_the_proof(fn, raised):
    assert _raised(fn, -2.0, None) == raised
    row = _row(fn, _Y + f"raises(f(x, y), {raised})")
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


def test_a_guard_that_refuses_the_whole_domain_is_what_the_call_does():
    assert _raised(domain_guard_refuses_the_whole_domain, -2.0) == "DomainError"
    row = _row(domain_guard_refuses_the_whole_domain, _NEG + "raises(f(x), KeyError)")
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text", [
    (only_deletes, _Y + "raises(f(x, y), ValueError)"),
    (under_a_lambda, _NEG + "raises(f(x), ValueError)"),
    (one_argument_reversed, _NEG + "raises(f(x), ValueError)"),
    (keywords_copied, _NEG + "raises(f(x), ValueError)"),
], ids=["only deleted", "lambda", "one argument reversed", "keywords copied"])
def test_a_call_that_reaches_the_body_unchanged_is_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text", [
    (deletes_twice, _Y + "raises(f(x, y), ValueError)"),
    (deletes_then_reads, _Y + "raises(f(x, y), ValueError)"),
    (under_a_negating_lambda, _NEG + "raises(f(x), ValueError)"),
    (two_arguments_reversed, _NEG + "y in [1, 5], raises(f(x, y), ValueError)"),
], ids=["deleted twice", "deleted then read", "negating lambda", "two arguments reversed"])
def test_a_call_that_reaches_the_body_changed_is_not_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)
