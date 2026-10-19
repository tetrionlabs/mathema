# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) refuses a
construct whose value is a number's text (an f-string, `%` formatting,
`.format(...)`, `str()`, `repr()`) where that text can reach the
returned value or a branch. Text that only becomes the message of an
exception raised by a `raise` statement, or of an `assert`, has no
further impact on the value: the exception is compared by its name, and
an assert message is read only when the assert fails. A correct body
guarding its input with such a raise or assert is proven exactly, not
within float64, and a guard that fires inside the domain falsifies by
execution as before. Text that reaches a return, a value used later, a
call other than the exception constructor, or that is turned back into
a number, stays refused; so does a raise in a body that could catch its
own exception (a `try` or `with` statement).

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import pytest

from mathema._exact_body import exact_twin, unfaithful
from mathema.conjecture import check_conjectures, claim


class Negative(ValueError):
    def __init__(self, *, text: str):
        super().__init__(text)


def _spin():
    i = 0
    while i < 3:
        i += 1


def raises_fstring(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError(f"negative: {x}")
    return x * 0.5


def raises_percent(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError("negative: %r" % x)
    return x * 0.5


def raises_format(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError("negative: {}".format(x))
    return x * 0.5


def raises_str(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError(str(x))
    return x * 0.5


def raises_repr(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError("negative", repr(x))
    return x * 0.5


def raises_keyword(x: float) -> float:
    _spin()
    if x < 0:
        raise Negative(text=f"negative: {x}")
    return x * 0.5


def asserts_fstring(x: float) -> float:
    _spin()
    assert x >= 0, f"negative: {x}"
    return x * 0.5


def returns_rounded_text(x: float) -> float:
    _spin()
    return float(f"{x:.2f}")


def returns_text_length(x: float) -> int:
    _spin()
    y = str(x)
    return len(y)


def raises_a_number_made_of_text(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError(float(f"{x:.2f}"))
    return x * 0.5


def _make_error(text: str) -> ValueError:
    return ValueError(text)


def raises_through_a_function(x: float) -> float:
    _spin()
    if x < 0:
        raise _make_error(f"negative: {x}")
    return x * 0.5


def raises_inside_a_try(x: float) -> float:
    _spin()
    try:
        if x < 0:
            raise ValueError(f"negative: {x}")
    except ValueError:
        return x * 100.0
    return x * 0.5


def raises_text_joined(x: float) -> float:
    _spin()
    if x < 0:
        raise ValueError("negative: " + f"{x}")
    return x * 0.5


#: a text construct whose only reach is an exception's message
ALLOWED = [raises_fstring, raises_percent, raises_format, raises_str,
           raises_repr, raises_keyword, asserts_fstring]

#: text that reaches the value, or whose reach the scan cannot tell
REFUSED = [returns_rounded_text, returns_text_length,
           raises_a_number_made_of_text, raises_through_a_function,
           raises_inside_a_try, raises_text_joined]

_HALF = "for x in {1, 2, 3}, f(x) == x / 2"


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn", ALLOWED, ids=lambda f: f.__name__)
def test_a_guard_whose_message_formats_the_number_is_proven_exactly(fn):
    p = _check(fn, _HALF)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.sweep_inexact" not in p.meta, p.meta
    assert "mathema.exact_witness" not in p.meta, p.meta


@pytest.mark.parametrize("fn", ALLOWED, ids=lambda f: f.__name__)
def test_the_scan_finds_nothing_to_refuse_in_such_a_body(fn):
    assert unfaithful(fn) == [], fn.__name__
    twin = exact_twin(fn)
    assert twin is not None, fn.__name__


@pytest.mark.parametrize("fn", ALLOWED, ids=lambda f: f.__name__)
def test_the_twin_raises_where_the_computation_raises(fn):
    from fractions import Fraction

    from mathema._exact_body import NotExact
    twin = exact_twin(fn)
    assert twin(3) == Fraction(3, 2)
    with pytest.raises(ValueError if fn is not asserts_fstring
                       else AssertionError):
        twin(-1)
    if fn is not asserts_fstring:
        # `x < 0` on a value the computation held as a float is a
        # decision the reading declines
        with pytest.raises(NotExact):
            twin(Fraction(-1))


@pytest.mark.parametrize("fn", [raises_fstring, raises_percent, raises_format,
                                asserts_fstring],
                         ids=lambda f: f.__name__)
def test_a_guard_that_fires_inside_the_domain_still_falsifies(fn):
    p = _check(fn, "for x in {-1, 1}, f(x) == x / 2")
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.route, p.note)
    assert p.counterexample is not None and "x = -1" in p.counterexample, \
        p.counterexample
    expected = "AssertionError" if fn is asserts_fstring else "ValueError"
    assert f"the function raised {expected}" in p.sketch, p.sketch
    assert "mathema.exact_witness" not in p.meta, p.meta


@pytest.mark.parametrize("fn", REFUSED, ids=lambda f: f.__name__)
def test_text_that_can_reach_the_value_is_still_refused(fn):
    found = unfaithful(fn)
    assert found, fn.__name__
    assert exact_twin(fn) is None, fn.__name__


@pytest.mark.parametrize("fn,law", [
    (returns_rounded_text, "for x in {1, 2, 3}, f(x) == x"),
    (returns_text_length, "for x in {0.5, 1.5, 2.5}, f(x) == 3"),
    (raises_a_number_made_of_text, _HALF),
    (raises_through_a_function, _HALF),
    (raises_inside_a_try, _HALF),
    (raises_text_joined, _HALF),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_correct_body_with_refused_text_is_proven_within_float64(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert p.meta["mathema.sweep_inexact"]["points"] == 3, p.meta
