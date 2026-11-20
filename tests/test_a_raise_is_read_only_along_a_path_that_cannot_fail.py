# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `raises(f(x), E)` claim is proven only when everything Python runs
on the way to the `raise` cannot raise something else first: each
statement and branch test before it, the evaluation of the exception's
arguments, the name that is called and the constructor of the class it
names. A keyword argument a builtin exception refuses, a builtin
constructor that checks its arguments, a module-level `str` that is not
the builtin, the text of an integer too long to convert, a division or
a square root before the raise, and a guard test that divides all leave
the claim to the probe, which runs the function. The class raised is
compared with the claimed class as Python compares them, by subclass,
not by name."""
import builtins
import math
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

_CLAIM = "for x in [-5, -1], raises(f(x), {})"


def _derive(fn, exception: str, domain: str = "[-5, -1]"):
    (row,) = check_conjectures(
        fn, [claim(f"for x in {domain}, raises(f(x), {exception})", route="derive")])
    return row


def _best(fn, exception: str, domain: str = "[-5, -1]"):
    (row,) = check_conjectures(fn, [claim(f"for x in {domain}, raises(f(x), {exception})")])
    return row


# ---- a keyword argument ----------------------------------------------------

def keyword_argument(x: float) -> float:
    if x < 0:
        raise ValueError(msg="negative")
    return x


def test_a_keyword_argument_to_a_builtin_exception_is_not_proven_to_raise_it():
    with pytest.raises(TypeError):
        keyword_argument(-2.0)
    row = _derive(keyword_argument, "ValueError")
    assert row.verdict != "proven", (row.verdict, row.sketch)
    best = _best(keyword_argument, "ValueError")
    assert best.verdict == "falsified", (best.verdict, best.route, best.note)


# ---- builtin constructors that check their arguments -----------------------

def unicode_decode_error(x: float) -> float:
    if x < 0:
        raise UnicodeDecodeError("bad")
    return x


def unicode_encode_error(x: float) -> float:
    if x < 0:
        raise UnicodeEncodeError("bad")
    return x


def unicode_translate_error(x: float) -> float:
    if x < 0:
        raise UnicodeTranslateError("bad")
    return x


def bare_unicode_decode_error(x: float) -> float:
    if x < 0:
        raise UnicodeDecodeError
    return x


def exception_group_of_one_argument(x: float) -> float:
    if x < 0:
        raise ExceptionGroup("bad")  # noqa: F821
    return x


def exception_group_with_no_exceptions(x: float) -> float:
    if x < 0:
        raise ExceptionGroup("m", [])  # noqa: F821
    return x


def base_exception_group(x: float) -> float:
    if x < 0:
        raise BaseExceptionGroup("bad")  # noqa: F821
    return x


def os_error_of_two_arguments(x: float) -> float:
    if x < 0:
        raise OSError(2, "missing")
    return x


_CHECKING = [
    (unicode_decode_error, "UnicodeDecodeError"),
    (unicode_encode_error, "UnicodeEncodeError"),
    (unicode_translate_error, "UnicodeTranslateError"),
    (bare_unicode_decode_error, "UnicodeDecodeError"),
    (exception_group_of_one_argument, "ExceptionGroup"),
    (exception_group_with_no_exceptions, "ExceptionGroup"),
    (base_exception_group, "BaseExceptionGroup"),
]


@pytest.mark.skipif(not hasattr(builtins, "ExceptionGroup"), reason="Python 3.11 or later")
@pytest.mark.parametrize("fn,exception", _CHECKING, ids=[f.__name__ for f, _ in _CHECKING])
def test_a_builtin_constructor_that_checks_its_arguments_is_not_proven_to_raise(
        fn, exception):
    with pytest.raises(BaseException) as raised:
        fn(-2.0)
    assert type(raised.value) is not getattr(builtins, exception)
    row = _derive(fn, exception)
    assert row.verdict != "proven", (row.verdict, row.sketch)


def test_an_os_error_of_two_arguments_is_not_read_as_raising_os_error_itself():
    with pytest.raises(FileNotFoundError):
        os_error_of_two_arguments(-2.0)
    row = _derive(os_error_of_two_arguments, "FileNotFoundError")
    assert row.verdict != "disproven" and row.verdict != "falsified", (
        row.verdict, row.sketch)
    assert "not the claimed" not in (row.sketch or ""), row.sketch


def test_every_builtin_constructor_form_derive_reads_builds_that_class():
    from mathema.symbolic._raise_reading import BUILTIN_CONSTRUCTORS

    class Unprintable:
        def __str__(self):
            raise KeyError("str")

        def __repr__(self):
            raise KeyError("repr")

        def __eq__(self, other):
            raise KeyError("eq")

        __hash__ = None

    arguments = [None, 1.5, "text", 10 ** 5000, Unprintable(), object()]
    for name, most in BUILTIN_CONSTRUCTORS.items():
        cls = getattr(builtins, name, None)
        if cls is None:
            continue
        counts = range(0, (len(arguments) if most is None else most) + 1)
        for count in counts:
            for start in range(len(arguments)):
                args = (arguments[start:] + arguments[:start])[:count]
                made = cls(*args)
                assert type(made) is cls, (name, args, type(made))
                with pytest.raises(cls) as raised:
                    raise made
                assert type(raised.value) is cls, (name, args)


# ---- a module-level str ----------------------------------------------------

_SHADOWING_MODULE = """
def str(v):
    raise KeyError(v)


def repr(v):
    raise KeyError(v)


def through_str(x: float) -> float:
    if x < 0:
        raise ValueError(str(x))
    return x


def through_repr(x: float) -> float:
    if x < 0:
        raise ValueError(repr(x))
    return x
"""


@pytest.mark.parametrize("name", ["through_str", "through_repr"])
def test_a_module_level_str_that_is_not_the_builtin_is_not_proven(
        tmp_path, monkeypatch, name):
    import importlib
    import sys
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "shadows_str.py").write_text(_SHADOWING_MODULE)
    sys.modules.pop("shadows_str", None)
    try:
        fn = getattr(importlib.import_module("shadows_str"), name)
        with pytest.raises(KeyError):
            fn(-2.0)
        row = _derive(fn, "ValueError")
        assert row.verdict != "proven", (row.verdict, row.sketch)
    finally:
        sys.modules.pop("shadows_str", None)


# ---- the text of an integer --------------------------------------------------

def f_string_of_an_int(x: int) -> int:
    if x > 0:
        raise TypeError(f"{x}")
    return x


def str_of_an_int(x: int) -> int:
    if x > 0:
        raise TypeError(str(x))
    return x


def repr_of_an_int(x: int) -> int:
    if x > 0:
        raise TypeError(repr(x))
    return x


_TEXT_OF_INT = [f_string_of_an_int, str_of_an_int, repr_of_an_int]


@pytest.mark.parametrize("fn", _TEXT_OF_INT, ids=[f.__name__ for f in _TEXT_OF_INT])
def test_the_text_of_an_unbounded_int_is_not_proven_to_build(fn):
    with pytest.raises(ValueError):
        fn(10 ** 5000)
    row = _derive(fn, "TypeError", domain="[1, oo)")
    assert row.verdict != "proven", (row.verdict, row.sketch)


@pytest.mark.parametrize("fn", _TEXT_OF_INT, ids=[f.__name__ for f in _TEXT_OF_INT])
def test_the_text_of_an_int_from_a_bounded_domain_is_proven_to_build(fn):
    row = _derive(fn, "TypeError", domain="[1, 100]")
    assert row.verdict == "proven", (row.verdict, row.sketch)


# ---- a statement or a test before the raise --------------------------------

def divides_before_the_raise(x: float) -> float:
    if x < 0:
        y = 1 / (x + 1)  # noqa: F841
        raise TypeError("negative")
    return x


def square_root_before_the_raise(x: float) -> float:
    if x < 0:
        y = math.sqrt(x)  # noqa: F841
        raise TypeError("negative")
    return x


def divides_before_the_guard(x: float) -> float:
    y = 1 / (x + 1)  # noqa: F841
    if x < 0:
        raise TypeError("negative")
    return x


def guard_that_divides(x: float) -> float:
    if (x + 1) / (x + 1) > 0:
        raise TypeError("negative")
    return x


_BEFORE = [divides_before_the_raise, square_root_before_the_raise,
           divides_before_the_guard, guard_that_divides]


@pytest.mark.parametrize("fn", _BEFORE, ids=[f.__name__ for f in _BEFORE])
def test_a_statement_before_the_raise_that_may_fail_is_not_proven(fn):
    with pytest.raises((ZeroDivisionError, ValueError)):
        fn(-1.0) if fn is not square_root_before_the_raise else fn(-2.0)
    row = _derive(fn, "TypeError")
    assert row.verdict != "proven", (row.verdict, row.sketch)
    best = _best(fn, "TypeError")
    assert best.verdict != "proven", (best.verdict, best.route, best.sketch)


def arithmetic_before_the_raise(x: float) -> float:
    if x < 0:
        y = x * 2 + 1  # noqa: F841
        raise TypeError("negative")
    return x


def test_arithmetic_that_cannot_fail_before_the_raise_is_proven():
    row = _derive(arithmetic_before_the_raise, "TypeError")
    assert row.verdict == "proven", (row.verdict, row.sketch)


# ---- a raise whose argument never returns ----------------------------------

def _spin(x):
    while True:
        pass


def argument_never_returns(x: float) -> float:
    if x < 0:
        raise ValueError(_spin(x))
    return x


def argument_exits_the_process(x: float) -> float:
    import os
    if x < 0:
        raise ValueError(os._exit(3))
    return x


@pytest.mark.parametrize("fn", [argument_never_returns, argument_exits_the_process],
                         ids=["never_returns", "exits_the_process"])
def test_a_claim_naming_no_exception_is_not_proven_when_the_argument_may_not_return(fn):
    from mathema import analyze
    from mathema.domain import Interval
    from mathema.symbolic import try_prove_raises
    proof = try_prove_raises(fn, analyze(fn), "f(x)", None,
                             domain={"x": Interval(-5.0, -1.0)})
    assert proof.status != "proven", (proof.status, proof.sketch)


# ---- the class is compared as Python compares it ---------------------------

def raises_a_subclass(x: float) -> float:
    if x < 0:
        raise ZeroDivisionError("z")
    return x


def raises_an_alias(x: float) -> float:
    if x < 0:
        raise IOError("z")  # noqa: UP024
    return x


@pytest.mark.parametrize("fn,claimed", [(raises_a_subclass, "ArithmeticError"),
                                        (raises_an_alias, "OSError")],
                         ids=["subclass", "alias"])
def test_a_raised_subclass_or_alias_of_the_claimed_class_is_proven(fn, claimed):
    row = _derive(fn, claimed)
    assert row.verdict == "proven", (row.verdict, row.sketch)


def test_a_raised_class_that_is_not_a_subclass_is_not_proven():
    row = _derive(raises_a_subclass, "LookupError")
    assert row.verdict != "proven", (row.verdict, row.sketch)
    assert "raises ZeroDivisionError, not the claimed LookupError" in (
        (row.sketch or "") + (row.note or "")), (row.sketch, row.note)


# ---- a guard read for a missing-value policy -------------------------------

def policy_divides_before_the_raise(x: Optional[float], y: float) -> float:
    if x is None:
        z = 1 / y  # noqa: F841
        raise TypeError("x is required")
    return x * y


def policy_divides_before_the_guard(x: Optional[float], y: float) -> float:
    z = 1 / y  # noqa: F841
    if x is None:
        raise TypeError("x is required")
    return x * y


def policy_local_class(x: Optional[float], y: float) -> float:
    class TypeError(Exception):  # noqa: A001
        pass
    if x is None:
        raise TypeError("x is required")
    return x * y


def policy_keyword_argument(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError(msg="x is required")
    return x * y


_POLICY = [policy_divides_before_the_raise, policy_divides_before_the_guard,
           policy_local_class, policy_keyword_argument]


def _policy_row(fn):
    rows = check_conjectures(fn, [claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
                                  claim("absent(f, x) raises(TypeError)")])
    return rows[-1]


@pytest.mark.parametrize("fn", _POLICY, ids=[f.__name__ for f in _POLICY])
def test_a_policy_is_not_proven_from_a_guard_whose_path_may_raise_something_else(fn):
    with pytest.raises(BaseException) as raised:
        fn(None, 0.0)
    assert fn is policy_keyword_argument or type(raised.value) is not builtins.TypeError
    row = _policy_row(fn)
    assert row.verdict != "proven", (row.verdict, row.route, row.note)
